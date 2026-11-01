"""Transactional state, bounded telemetry and evaluator-only effect ledger.

This database belongs to the control plane. Agents receive filtered HTTP views only.
Archiving keeps complete event/effect pairs together; a disk cap stops new activity
instead of silently deleting evidence or filling the host disk.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "world.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS state (space TEXT, name TEXT, value TEXT,
                PRIMARY KEY(space,name));
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER NOT NULL,
                ts TEXT NOT NULL, principal TEXT NOT NULL, tool TEXT NOT NULL,
                target TEXT NOT NULL, status INTEGER NOT NULL, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS effects (
                event_id INTEGER PRIMARY KEY, data TEXT NOT NULL);
        """)
        self.db.commit()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.lock:
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def get(self, space: str, name: str, default: Any = None) -> Any:
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM state WHERE space=? AND name=?", (space, name)
            ).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, space: str, name: str, value: Any) -> None:
        self.db.execute(
            "INSERT INTO state VALUES (?,?,?) ON CONFLICT(space,name) DO UPDATE SET value=excluded.value",
            (space, name, json.dumps(value, ensure_ascii=False, allow_nan=False)),
        )

    def items(self, space: str) -> dict[str, Any]:
        with self.lock:
            return {
                r[0]: json.loads(r[1])
                for r in self.db.execute(
                    "SELECT name,value FROM state WHERE space=? ORDER BY name", (space,)
                )
            }

    def event(
        self,
        tick: int,
        principal: str,
        tool: str,
        target: str,
        status: int,
        detail: dict[str, Any],
        effect: dict[str, Any],
    ) -> int:
        cur = self.db.execute(
            "INSERT INTO events(tick,ts,principal,tool,target,status,detail) VALUES (?,?,?,?,?,?,?)",
            (tick, utc_now(), principal, tool, target, status, json.dumps(detail)),
        )
        eid = int(cur.lastrowid or 0)
        self.db.execute("INSERT INTO effects VALUES (?,?)", (eid, json.dumps(effect)))
        return eid

    def events(
        self, *, after: int = 0, through_tick: int, limit: int = 200, principal: str | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM events WHERE id>? AND tick<=?"
        args: list[Any] = [after, through_tick]
        if principal is not None:
            sql += " AND principal=?"
            args.append(principal)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(max(1, min(limit, 2000)))
        with self.lock:
            rows = list(self.db.execute(sql, args))
        world_id = self.get("meta", "world_id")
        return [
            dict(r) | {"detail": json.loads(r["detail"]), "world_id": world_id}
            for r in reversed(rows)
        ]

    def evidence(self, ids: list[int], through_tick: int) -> list[dict[str, Any]]:
        rows = []
        for eid in ids[:50]:
            r = self.db.execute(
                "SELECT * FROM events WHERE id=? AND tick<=?", (eid, through_tick)
            ).fetchone()
            if r:
                rows.append(dict(r) | {"detail": json.loads(r["detail"])})
        return rows

    def checkpoint(self) -> None:
        with self.lock:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def disk_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())

    def archive(self, retention: int, max_archive_bytes: int) -> None:
        with self.transaction():
            count = int(self.db.execute("SELECT count(*) FROM events").fetchone()[0])
            if count <= retention:
                return
            rows = list(
                self.db.execute(
                    "SELECT e.*,f.data AS effect FROM events e JOIN effects f ON f.event_id=e.id ORDER BY e.id LIMIT ?",
                    (count - retention,),
                )
            )
            folder = self.root / "sealed-archives"
            folder.mkdir(exist_ok=True)
            name = f"events-{rows[0]['id']}-{rows[-1]['id']}.jsonl.gz"
            path = folder / name
            payload = "".join(json.dumps(dict(r)) + "\n" for r in rows).encode()
            blob = gzip.compress(payload, mtime=0)
            used = sum(p.stat().st_size for p in folder.glob("*.gz") if p != path)
            if used + len(blob) > max_archive_bytes:
                raise OSError(
                    "Evidence archive budget reached; increase the configured cap or export archives."
                )
            temp = path.with_suffix(".tmp")
            temp.write_bytes(blob)
            temp.replace(path)
            self.put(
                "archives", name, {"sha256": hashlib.sha256(blob).hexdigest(), "events": len(rows)}
            )
            self.db.execute("DELETE FROM effects WHERE event_id<=?", (rows[-1]["id"],))
            self.db.execute("DELETE FROM events WHERE id<=?", (rows[-1]["id"],))

    def close(self) -> None:
        self.checkpoint()
        self.db.close()
