import gzip
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from saber.lab.collector import create_collector
from saber.lab.ledger import Ledger
from saber.lab.retention import archive, evidence


def test_archive_is_verified_and_never_prunes_undelivered_events(tmp_path):
    ledger = Ledger(tmp_path)
    stamp = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    ids = [str(uuid.uuid4()) for _ in range(2)]
    for eid in ids:
        ledger.append(
            {"id": eid, "ts": stamp, "host": "app", "kind": "file.write", "data": {"bytes": 7}}
        )
    with ledger.db:
        ledger.db.execute("UPDATE events SET delivered=1 WHERE id=?", (ids[0],))
    receipt = archive(ledger, 7)
    assert receipt["events"] == 1
    raw = gzip.decompress((tmp_path / "archives" / receipt["file"]).read_bytes())
    archived = json.loads(raw)
    assert archived["event"]["id"] == ids[0]
    assert ledger.events()[0]["id"] == ids[1]
    assert archive(ledger, 7) is None
    assert evidence(ledger, ids[0]) == archived
    client = TestClient(create_collector(ledger, {"sources": {}, "read_token": "reader"}))
    assert (
        client.get("/evidence/" + ids[0], headers={"Authorization": "Bearer reader"}).json()
        == archived
    )
    assert ledger.append(archived["event"]) is False
    with pytest.raises(ValueError):
        ledger.append(archived["event"] | {"kind": "file.changed"})
    (tmp_path / "archives" / receipt["file"]).write_bytes(b"corrupted")
    assert (
        client.get("/evidence/" + ids[0], headers={"Authorization": "Bearer reader"}).status_code
        == 503
    )
    ledger.close()
