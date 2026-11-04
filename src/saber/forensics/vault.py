"""Immutable source copies, indexed derivatives and bounded query access."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saber.forensics.parsers import TEXT_LIMIT, records, utc
from saber.lab.events import redact

MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_VAULT_BYTES = 512 * 1024 * 1024
MAX_ROWS = 200000
FORMATS = ("csv", "apache", "iis", "text")
GROUPS = {"host", "image", "process_guid", "pid", "ip", "event_id", "status"}


def display(value: Any) -> Any:
    """Best-effort display masking; originals stay private in the evidence vault."""
    if isinstance(value, dict):
        return {k: display(v) for k, v in redact(value).items()}
    if isinstance(value, list):
        return [display(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)\b(Bearer|Basic)\s+\S+", r"\1 [REDACTED]", value)
        value = re.sub(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", value)
        value = re.sub(
            r"""(?i)((?:password|token|api[_-]?key|secret)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s&,;]+)""",
            r"\1[REDACTED]",
            value,
        )
    return redact(value)


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    mode: str = Field(default="search", pattern=r"^(search|timeline|stats|process)$")
    text: str = Field(default="", max_length=200)
    host: str = Field(default="", max_length=200)
    process_guid: str = Field(default="", max_length=200)
    pid: str = Field(default="", max_length=40)
    ip: str = Field(default="", max_length=100)
    since: str | None = Field(default=None, max_length=64)
    until: str | None = Field(default=None, max_length=64)
    group_by: str = Field(
        default="image", pattern=r"^(host|image|process_guid|pid|ip|event_id|status)$"
    )
    after: int = Field(default=0, ge=0, le=1600000)
    limit: int = Field(default=10, ge=1, le=20)


class Vault:
    def __init__(self, root: Path) -> None:
        self.root = root / "forensics"
        if self.root.is_symlink():
            raise ValueError("Evidence directory cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        dbpath = self.root / "index.sqlite3"
        if dbpath.is_symlink():
            raise ValueError("Evidence database cannot be a symlink")
        self.db = sqlite3.connect(dbpath, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA max_page_count=98304")  # 384 MiB derivative DB at 4 KiB/page
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, ordinal INTEGER NOT NULL,
                offset INTEGER NOT NULL, length INTEGER NOT NULL, sha256 TEXT NOT NULL,
                ts TEXT, host TEXT, image TEXT, process_guid TEXT, pid TEXT, ip TEXT,
                event_id TEXT, status TEXT, fields TEXT NOT NULL, text TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS record_source ON records(source, id);
            CREATE INDEX IF NOT EXISTS record_time ON records(source, ts, id);
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, owner TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS seen (session TEXT, evidence INTEGER,
                PRIMARY KEY(session, evidence));
            CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, owner TEXT, data TEXT);
        """)

    def __enter__(self) -> Vault:
        return self

    def __exit__(self, *args: Any) -> None:
        self.db.close()

    def sources(self) -> list[dict[str, Any]]:
        return [
            json.loads(r[0])
            for r in self.db.execute("SELECT manifest FROM sources ORDER BY rowid LIMIT 100")
        ]

    def source(self, source_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT manifest FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown evidence source")
        return dict(json.loads(row[0]))

    def original(self, source_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", source_id):
            raise ValueError("Invalid source ID")
        path = self.root / (source_id + ".original")
        if path.is_symlink():
            raise ValueError("Original cannot be a symlink")
        return path

    def verify(self, source_id: str) -> dict[str, Any]:
        manifest = self.source(source_id)
        with self.original(source_id).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return {
            "source_id": source_id,
            "sha256": digest,
            "integrity_verified": digest == manifest["sha256"],
        }

    def import_file(
        self, path: Path, fmt: str, label: str, offset: str | None = None
    ) -> dict[str, Any]:
        if fmt not in FORMATS or not label or len(label) > 120:
            raise ValueError("Specify a supported format and label (1..120 characters)")
        if offset is not None:
            utc("2000-01-01T00:00:00", offset)
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("Use a regular file up to 128 MiB")
        source_id = uuid.uuid4().hex
        initial_stat = path.stat()
        destination = self.original(source_id)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute("SELECT count(*) FROM sources").fetchone()[0] >= 100:
                raise ValueError("Source limit reached; use a separate investigation directory")
            used = sum(p.stat().st_size for p in self.root.iterdir() if p.is_file())
            if used + path.stat().st_size * 3 > MAX_VAULT_BYTES:
                raise ValueError("Evidence vault budget exceeded (512 MiB)")
            digest, size = hashlib.sha256(), 0
            with path.open("rb") as source, destination.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        raise ValueError("Source grew beyond the import limit")
                    digest.update(chunk)
                    target.write(chunk)
            count = 0
            warnings: Counter[str] = Counter()
            indexed_complete = True
            with destination.open("rb") as original:
                try:
                    for record in records(destination, fmt, offset):
                        if count == MAX_ROWS:
                            indexed_complete = False
                            warnings["row_limit"] += 1
                            break
                        original.seek(record["offset"])
                        raw = original.read(record["length"])
                        content = raw.decode("utf-8-sig")
                        fields = record["fields"]
                        fields["text_truncated"] = len(content) > TEXT_LIMIT
                        if fields.get("parse_error"):
                            warnings["unparsed_records"] += 1
                        if not fields.get("ts"):
                            warnings["unknown_timestamp"] += 1
                        if fields["text_truncated"]:
                            warnings["search_text_truncated"] += 1
                        count += 1
                        self.db.execute(
                            "INSERT INTO records(source,ordinal,offset,length,sha256,ts,host,image,process_guid,pid,ip,event_id,status,fields,text) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                source_id,
                                count,
                                record["offset"],
                                record["length"],
                                hashlib.sha256(raw).hexdigest(),
                                *[
                                    fields.get(k, "")
                                    for k in (
                                        "ts",
                                        "host",
                                        "image",
                                        "process_guid",
                                        "pid",
                                        "ip",
                                        "event_id",
                                        "status",
                                    )
                                ],
                                json.dumps(fields),
                                content[:TEXT_LIMIT],
                            ),
                        )
                except (UnicodeError, csv.Error, ValueError):
                    indexed_complete = False
                    warnings["parse_stopped"] += 1
            manifest: dict[str, Any] = {
                "id": source_id,
                "label": label,
                "format": fmt,
                "sha256": digest.hexdigest(),
                "bytes": size,
                "records": count,
                "indexed_complete": indexed_complete,
                "warnings": dict(warnings),
                "assumed_offset": offset,
                "original_preserved": True,
                "encoding": "utf-8",
                "parser_version": 1,
                "imported_at": datetime.now(UTC).isoformat(),
                "origin_name": path.name[:120],
            }
            final_stat = path.stat()
            if (initial_stat.st_mtime_ns, initial_stat.st_size) != (
                final_stat.st_mtime_ns,
                final_stat.st_size,
            ):
                manifest["warnings"]["source_changed_during_copy"] = 1
            self.db.execute("INSERT INTO sources VALUES (?,?)", (source_id, json.dumps(manifest)))
            self.db.commit()
            return manifest
        except BaseException:
            self.db.rollback()
            destination.unlink(missing_ok=True)  # only our new copy; never touch the supplied file
            raise

    def query(self, query: Query, sources: list[str]) -> dict[str, Any]:
        if query.mode == "process" and (
            not query.host
            or not (query.process_guid or (query.pid and query.since and query.until))
        ):
            raise ValueError(
                "Process pivot needs host + process_guid, or host + pid + since + until; PID reuse remains possible"
            )
        where = ["source IN (" + ",".join("?" for _ in sources) + ")"]
        params: list[Any] = list(sources)
        for field in ("host", "process_guid", "pid", "ip"):
            value = getattr(query, field)
            if value:
                where.append(field + "=?")
                params.append(value)
        if query.text:
            where.append(
                "instr(lower(text), lower(?)) > 0"
            )  # literal, never attacker-supplied regex
            params.append(query.text)
        for field, op in (("since", ">="), ("until", "<=")):
            value = getattr(query, field)
            if value:
                stamp = utc(value)
                if stamp is None:
                    raise ValueError("Time filters require an explicit timezone")
                where.append("ts " + op + " ?")
                params.append(stamp)
        if query.since and query.until and str(utc(query.since)) > str(utc(query.until)):
            raise ValueError("since must not exceed until")
        if query.mode == "timeline":
            where.append("ts IS NOT NULL")
        clause = " AND ".join(where)
        deadline = time.monotonic() + 3
        self.db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        try:
            if query.mode == "stats":
                rows = self.db.execute(
                    f"SELECT {query.group_by} AS value,count(*) AS count FROM records WHERE {clause} GROUP BY {query.group_by} ORDER BY count DESC,value LIMIT ?",
                    (*params, query.limit),
                ).fetchall()
                return {
                    "groups": [
                        {
                            "value": display(str(r["value"]))[:256],
                            "count": r["count"],
                            **({"value_truncated": True} if len(str(r["value"])) > 256 else {}),
                        }
                        for r in rows
                    ],
                    "group_by": query.group_by,
                    "scope": "indexed matching records; top groups only",
                    "evidence": [],
                }
            # Timeline cursors are ranks within this immutable source selection and filter.
            order = "ts,id" if query.mode == "timeline" else "id"
            rows = self.db.execute(
                f"SELECT * FROM records WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                (*params, query.limit + 1, query.after),
            ).fetchall()
            evidence: list[dict[str, Any]] = []
            preview_bytes = 0
            for row in rows[: query.limit]:
                item = self.evidence(row)
                item_bytes = len(json.dumps(item).encode())
                if evidence and preview_bytes + item_bytes > 16000:
                    break
                evidence.append(item)
                preview_bytes += item_bytes
            return {
                "evidence": evidence,
                "next_after": query.after + len(evidence) if len(rows) > len(evidence) else None,
                "page_complete": len(rows) <= len(evidence),
                "preview_budget_bytes": 16000,
                "scope": "indexed records only",
                "unknown_times_excluded": query.mode == "timeline"
                or bool(query.since or query.until),
            }
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                raise ValueError(
                    "Query time budget reached; narrow the source or filters"
                ) from None
            raise
        finally:
            self.db.set_progress_handler(None, 0)

    def evidence(self, row: sqlite3.Row) -> dict[str, Any]:
        with self.original(row["source"]).open("rb") as stream:
            stream.seek(row["offset"])
            raw = stream.read(row["length"])
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("Evidence integrity mismatch; stop and verify the original")
        fields = json.loads(row["fields"])
        return {
            "id": row["id"],
            "source_id": row["source"],
            "record": row["ordinal"],
            "offset": row["offset"],
            "length": row["length"],
            "sha256": row["sha256"],
            "record_integrity_verified": True,
            "fields": {
                k: (v[:256] if isinstance(v, str) else v) for k, v in display(fields).items()
            },
            "fields_preview_truncated": any(
                isinstance(v, str) and len(v) > 256 for v in fields.values()
            ),
            "preview": display(row["text"])[:600],
            "preview_is_original": False,
        }
