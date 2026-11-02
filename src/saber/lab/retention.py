"""Lossless, acknowledged-evidence archival before pruning the hot raw store."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
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
                "DELETE FROM events WHERE id=? AND delivered=1", [(r[0],) for r in rows]
            )
            ledger.put("archive:" + path.name, receipt)
        return receipt
