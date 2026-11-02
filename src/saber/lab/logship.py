"""Checkpointed readers for real Zeek JSON and Linux audit records (not synthetic sensors)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import signal
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.lab.events import Emitter, SensorEvent, redact
from saber.lab.ledger import Ledger, now


def normalize(line: bytes, host: str, source: str, kind: str) -> dict[str, Any]:
    if source == "zeek":
        data = json.loads(line)
        ts = datetime.fromtimestamp(float(data["ts"]), UTC).isoformat(timespec="milliseconds")
        event_kind = "network." + kind
    else:
        raw = line.decode("utf-8", errors="replace").strip()
        stamp = re.search(r"msg=audit\((\d+(?:\.\d+)?):(\d+)\)", raw)
        if not stamp:
            raise ValueError("Invalid kernel audit record")
        ts = datetime.fromtimestamp(float(stamp[1]), UTC).isoformat(timespec="milliseconds")
        data = {"raw": raw, "serial": stamp[2]}
        event_kind = "linux.audit"
    return SensorEvent(
        id=hashlib.sha256(host.encode() + source.encode() + kind.encode() + line).hexdigest()[:32],
        ts=ts,
        host=host,
        kind=event_kind,
        sensor=source + "-log-v1",
        data=redact(data),
    ).model_dump()


def scan(ledger: Ledger, folder: Path, host: str, source: str) -> int:
    count = 0
    paths = folder.rglob("*.log") if source == "zeek" else folder.glob("audit.log*")
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file() or path.suffix == ".gz":
            continue
        kind = path.name.split(".")[0]
        if source == "zeek" and kind not in (
            "conn",
            "dns",
            "http",
            "ssl",
            "files",
            "notice",
            "capture_loss",
        ):
            continue
        stat = path.stat()
        identity = f"{stat.st_dev}/{stat.st_ino}"
        key = "log-offset:" + identity
        offset = ledger.get(key, 0)
        if offset > stat.st_size:
            # Copy-truncate rotation: reread retained bytes; deterministic IDs deduplicate.
            offset = 0
        with path.open("rb") as stream:
            stream.seek(offset)
            for _ in range(1000):
                line = stream.readline(65537)
                if not line:
                    break
                if not line.endswith(b"\n"):
                    if len(line) > 65536:
                        raise ValueError("Sensor line too large; checkpoint retained")
                    break
                event = normalize(line, host, source, kind)
                ledger.append(event)
                ledger.put(key, stream.tell())
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["zeek", "audit"], required=True)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--collector", required=True)
    parser.add_argument("--host", default="network")
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text())
    ledger = Ledger(args.data)
    emitter = Emitter(ledger, args.host, args.collector, credentials["ingest_token"])
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    emitter.start()
    try:
        while not stop.is_set():
            scan(ledger, args.logs, args.host, args.source)
            ledger.put("last_scan", now())
            stop.wait(2)
    finally:
        emitter.close()
        ledger.close()


if __name__ == "__main__":
    main()
