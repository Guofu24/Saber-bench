"""Lossless, acknowledged-evidence archival before pruning the hot raw store."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from saber.lab.ledger import Ledger


def archive(ledger: Ledger, days: int) -> dict[str, Any] | None:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="milliseconds")
    # File data is fsynced and verified before SQLite removal. In-flight evidence
    # is retained, even beyond the hot retention window when downstream is down.
    with ledger.lock:
        rows = ledger.db.execute(
            "SELECT id,data,sha256 FROM events WHERE delivered=1 AND ts<? ORDER BY ts,id LIMIT 1000",
            (cutoff,),
        ).fetchall()
        if not rows:
            return None
        folder = ledger.root / "archives"
        folder.mkdir(exist_ok=True)
        path = folder / (uuid.uuid4().hex + ".jsonl.gz")
        raw = b"".join(
            json.dumps({"event": json.loads(r[1]), "sha256": r[2]}, sort_keys=True).encode() + b"\n"
            for r in rows
        )
        packed = gzip.compress(raw)
        used = sum(
            p.stat().st_size for p in ledger.root.rglob("*") if p.is_file() and not p.is_symlink()
        )
        if used + len(packed) >= ledger.budget:
            raise OSError("Archive exceeds disk budget; export storage first")
        with path.open("xb") as stream:
            stream.write(packed)
            stream.flush()
            os.fsync(stream.fileno())
        if gzip.decompress(path.read_bytes()) != raw:
            raise OSError("Archive verification failed; hot evidence retained")
        receipt = {
            "file": path.name,
            "sha256": hashlib.sha256(packed).hexdigest(),
            "events": len(rows),
            "before": cutoff,
        }
        with ledger.db:
            ledger.db.executemany(
                "INSERT OR IGNORE INTO archived_events VALUES (?,?,?)",
                [(r[0], path.name, r[2]) for r in rows],
            )
            ledger.db.executemany(
                "DELETE FROM events WHERE id=? AND delivered=1", [(r[0],) for r in rows]
            )
            ledger.put("archive:" + path.name, receipt)
        return receipt


def evidence(ledger: Ledger, event_id: str) -> dict[str, Any] | None:
    """Look up an archived event without scanning arbitrary files or trusting unverified bytes."""
    with ledger.lock:
        row = ledger.db.execute(
            "SELECT file,sha256 FROM archived_events WHERE id=?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        filename, expected = row
        receipt = ledger.get("archive:" + filename)
    if not receipt or not re.fullmatch(r"[a-f0-9]{32}\.jsonl\.gz", filename):
        raise ValueError("Missing archive receipt")
    path = ledger.root / "archives" / filename
    if path.resolve() != path.absolute() or path.stat().st_size > 32_000_000:
        raise ValueError("Invalid archive path or size")
    packed = path.read_bytes()
    if hashlib.sha256(packed).hexdigest() != receipt["sha256"]:
        raise ValueError("Archive hash mismatch")
    import io

    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
        raw = stream.read(32_000_001)
    if len(raw) > 32_000_000:
        raise ValueError("Archive expansion exceeds limit")
    for line in raw.splitlines():
        proof: dict[str, Any] = json.loads(line)
        if proof["event"]["id"] == event_id:
            canonical = json.dumps(
                proof["event"], sort_keys=True, ensure_ascii=True, separators=(",", ":")
            ).encode()
            if proof["sha256"] != expected or hashlib.sha256(canonical).hexdigest() != expected:
                raise ValueError("Archived evidence hash mismatch")
            return proof
    raise ValueError("Archived evidence missing from its indexed file")
