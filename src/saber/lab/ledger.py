"""Durable raw evidence, idempotency receipts, delivery outbox and cases."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Ledger:
    def __init__(self, root: Path, budget_mb: int = 4096) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root, self.budget = root.resolve(), budget_mb * 1024 * 1024
        self.lock = threading.RLock()
        self.db = sqlite3.connect(root / "lab.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, ts TEXT NOT NULL, host TEXT NOT NULL,
            kind TEXT NOT NULL, data TEXT NOT NULL, sha256 TEXT NOT NULL, delivered INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS event_time ON events(ts,id);
        CREATE TABLE IF NOT EXISTS state(k TEXT PRIMARY KEY,v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, digest TEXT NOT NULL, result TEXT);
        CREATE TABLE IF NOT EXISTS archived_events(id TEXT PRIMARY KEY, file TEXT NOT NULL, sha256 TEXT NOT NULL);
        """)
        self.db.commit()

    def get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            row = self.db.execute("SELECT v FROM state WHERE k=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def put(self, key: str, value: Any) -> None:
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO state VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (key, json.dumps(value)),
            )

    def append(self, event: dict[str, Any]) -> bool:
        raw = json.dumps(event, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        with self.lock, self.db:
            old = self.db.execute(
                "SELECT sha256 FROM events WHERE id=? UNION ALL SELECT sha256 FROM archived_events WHERE id=? LIMIT 1",
                (event["id"], event["id"]),
            ).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("Evidence ID reused with different content")
                return False
            if (
                sum(
                    p.stat().st_size
                    for p in self.root.rglob("*")
                    if p.is_file() and not p.is_symlink()
                )
                >= self.budget
            ):
                raise OSError("Evidence disk budget reached; export/expand storage before resuming")
            self.db.execute(
                "INSERT INTO events(id,ts,host,kind,data,sha256) VALUES (?,?,?,?,?,?)",
                (event["id"], event["ts"], event["host"], event["kind"], raw, digest),
            )
            return True

    def events(
        self,
        *,
        before: str | None = None,
        after: str | None = None,
        host: str | None = None,
        kind: str | None = None,
        cursor: tuple[str, str] | None = None,
        limit: int = 100,
        pending: bool = False,
        filters: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT data FROM events WHERE 1=1"
        args: list[Any] = []
        if before:
            sql += " AND ts<=?"
            args.append(before)
        if after:
            sql += " AND ts>=?"
            args.append(after)
        if filters:
            from saber.lab.query import sql_predicates

            expression, parameters = sql_predicates(filters)
            sql += " AND " + expression
            args.extend(parameters)
        if host:
            sql += " AND host=?"
            args.append(host)
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if cursor:
            sql += " AND (ts<? OR (ts=? AND id<?))"
            args.extend([cursor[0], cursor[0], cursor[1]])
        if pending:
            sql += " AND delivered=0"
        direction = "ASC" if pending else "DESC"
        sql += f" ORDER BY ts {direction},id {direction} LIMIT ?"
        args.append(max(1, min(limit, 1000)))
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute(sql, args)]

    def job(self, job_id: str, payload: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock, self.db:
            old = self.db.execute("SELECT digest,result FROM jobs WHERE id=?", (job_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("Job ID cannot be reused with changed arguments")
                return False, json.loads(old[1]) if old[1] else None
            self.db.execute("INSERT INTO jobs VALUES (?,?,NULL)", (job_id, digest))
            return True, None

    def finish(self, job_id: str, result: dict[str, Any]) -> None:
        with self.lock, self.db:
            self.db.execute("UPDATE jobs SET result=? WHERE id=?", (json.dumps(result), job_id))

    def close(self) -> None:
        self.db.close()
