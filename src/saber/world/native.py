"""Measured process/file/DNS/network activity for fixed lab workloads.

The operator controls this executor; actors only submit existing validated lab
actions. This is NOT an OS sandbox or a host-wide EDR sensor. It can run inside
the existing sandbox/VM profiles; no shell, external targets or keys are exposed.
"""

from __future__ import annotations

import json
import logging
import os
import socketserver
import struct
import subprocess
import sys
import threading
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from saber.world.models import Action
from saber.world.native_worker import DNS_QUESTION
from saber.world.store import Store, utc_now

FIELDS = {
    "name",
    "answer",
    "server",
    "transport",
    "bytes",
    "local",
    "remote",
    "method",
    "path",
    "status",
    "duration_ms",
    "sha256",
    "command_line",
    "ppid",
    "exit_code",
    "error",
}


def read_events(
    store: Store,
    *,
    through_tick: int,
    actor_id: str | None = None,
    before: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    sql = "SELECT id, data FROM native_events WHERE tick<=?"
    args: list[Any] = [through_tick]
    if actor_id is not None:
        sql += " AND actor_id=?"
        args.append(actor_id)
    if before is not None:
        sql += " AND id<?"
        args.append(before)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(100, limit)))
    with store.lock:
        return [
            json.loads(r["data"]) | {"id": r["id"]}
            for r in reversed(list(store.db.execute(sql, args)))
        ]


class NativeExecutor:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.log = RotatingFileHandler(
            store.root / "native.jsonl", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )

        class DNS(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                packet, sock = self.request
                if len(packet) != 12 + len(DNS_QUESTION) or packet[2:] != (
                    struct.pack("!HHHHH", 0x0100, 1, 0, 0, 0) + DNS_QUESTION
                ):
                    return
                response = (
                    packet[:2]
                    + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0)
                    + DNS_QUESTION
                    + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x00\x00\x04\x7f\x00\x00\x01"
                )
                sock.sendto(response, self.client_address)

        self.dns = socketserver.UDPServer(("127.0.0.1", 0), DNS)
        self.thread = threading.Thread(
            target=self.dns.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self.thread.start()

    def _save(
        self,
        actor_id: str,
        tick: int,
        capture: str,
        pid: int,
        event_id: int | None,
        rows: list[dict[str, Any]],
    ) -> None:
        public = []
        with self.store.transaction():
            for raw in rows:
                row = {
                    "actor_id": actor_id,
                    "tick": tick,
                    "capture_id": capture,
                    "pid": pid,
                    "event_id": event_id,
                    "ts": raw["ts"],
                    "kind": raw["kind"],
                    "sensor": "saber-native-v1",
                    "data": {k: v for k, v in raw.items() if k in FIELDS},
                }
                cursor = self.store.db.execute(
                    "INSERT INTO native_events(tick,actor_id,data) VALUES (?,?,?)",
                    (tick, actor_id, json.dumps(row)),
                )
                public.append(row | {"id": cursor.lastrowid})
        for row in public:
            self.log.emit(
                logging.LogRecord("saber.native", logging.INFO, "", 0, json.dumps(row), (), None)
            )

        # The viewer reads a separate per-actor window, so busy teams cannot
        # crowd this actor out. Full retained history remains in SQLite.
        folder = self.store.root / "native-office"
        folder.mkdir(exist_ok=True)
        if folder.is_symlink() or folder.resolve() != folder.absolute():
            raise ValueError("Native export directory must not be redirected")
        path = folder / f"{actor_id}.json"
        temporary = folder / f"{actor_id}.tmp"
        if path.is_symlink() or temporary.is_symlink():
            raise ValueError("Native export must not be a link")
        page = {
            "schema_version": 1,
            "world_id": self.store.get("meta", "world_id"),
            "actor_id": actor_id,
            "through_tick": tick,
            "limit": 100,
            "sensor": "saber-native-v1",
            "events": read_events(self.store, through_tick=tick, actor_id=actor_id),
        }
        temporary.write_text(json.dumps(page), encoding="utf-8")
        temporary.replace(path)

    def act(
        self, actor_id: str, tick: int, http_port: int, token: str, action: Action
    ) -> dict[str, Any]:
        # actor_id comes from the validated roster, never from a requested path.
        directory = self.store.root / "workloads" / actor_id
        directory.mkdir(parents=True, exist_ok=True)
        if (
            directory.is_symlink()
            or directory.resolve() != directory.absolute()
            or not directory.resolve().is_relative_to(self.store.root)
        ):
            raise ValueError("Workload directory must stay inside this world")
        worker = Path(__file__).with_name("native_worker.py").resolve()
        argv = [sys.executable, "-I", "-B", str(worker)]
        # Explicit minimal environment. Provider keys and tokens never appear in
        # the child's environment, argv, telemetry or public artifact.
        env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "TEMP", "TMP") if k in os.environ}
        capture = uuid.uuid4().hex
        started = utc_now()
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=directory,
            env=env,
        )
        rows: list[dict[str, Any]] = [
            {
                "kind": "process.start",
                "ts": started,
                "ppid": os.getpid(),
                "command_line": subprocess.list2cmdline(argv),
            }
        ]
        result: dict[str, Any] = {}
        error = None
        try:
            payload = {
                "dns_port": self.dns.server_address[1],
                "http_port": http_port,
                "token": token,
                "action": action.model_dump(),
            }
            output, _ = process.communicate(json.dumps(payload).encode() + b"\n", timeout=20)
            reply = json.loads(output)
            rows.extend(reply["events"])
            result = reply["result"]
            error = reply["error"]
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            error = "TimeoutExpired"
        except (ValueError, KeyError, OSError) as exc:
            error = type(exc).__name__
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            rows.append(
                {
                    "kind": "process.exit",
                    "ts": utc_now(),
                    "exit_code": process.returncode,
                    "error": error,
                }
            )
            eid = result.get("event_id")
            self._save(actor_id, tick, capture, process.pid, eid, rows)
        if error or process.returncode:
            # Never retry: a failed receipt/transport may follow an applied action.
            raise RuntimeError(
                "Native workload failed; inspect native telemetry. Action was not retried."
            )
        return result

    def close(self) -> None:
        self.dns.shutdown()
        self.thread.join(timeout=5)
        self.dns.server_close()
        self.log.close()
