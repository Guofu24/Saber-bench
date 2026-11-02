import json
import uuid

from fastapi.testclient import TestClient

from saber.lab.collector import create_collector
from saber.lab.ledger import Ledger, now
from saber.lab.logship import normalize, scan


def test_windows_evidence_queue_requires_capabilities_and_verified_rollback(tmp_path):
    ledger = Ledger(tmp_path)
    creds = {
        "sources": {"soc-dc": "sensor", "red": "red-sensor"},
        "read_token": "read",
        "response_token": "respond",
        "relay_token": "relay",
    }
    with TestClient(create_collector(ledger, creds)) as client:
        event = {
            "id": str(uuid.uuid4()),
            "ts": now(),
            "host": "soc-dc",
            "kind": "windows.event",
            "sensor": "windows-eventlog-v1",
            "data": {"event_id": 4625, "fields": {"TargetUserName": "saber-red"}},
        }
        assert (
            client.post(
                "/ingest", headers={"Authorization": "Bearer red-sensor"}, json={"events": [event]}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/ingest", headers={"Authorization": "Bearer sensor"}, json={"events": [event]}
            ).status_code
            == 200
        )
        action = {"case_id": "case-" + event["id"], "action": "contain_domain_user"}
        assert (
            client.post(
                "/guest/actions", headers={"Authorization": "Bearer read"}, json=action
            ).status_code
            == 403
        )
        response = client.post(
            "/guest/actions", headers={"Authorization": "Bearer respond"}, json=action
        )
        job = response.json()
        assert job["state"] == "QUEUED"
        assert (
            client.post(
                "/guest/actions", headers={"Authorization": "Bearer respond"}, json=action
            ).json()["id"]
            == job["id"]
        )
        receipt = {
            "id": job["id"],
            "state": "SUCCEEDED",
            "disabled_observed": True,
            "restore_task_registered": True,
        }
        assert (
            client.post(
                "/guest/receipts", headers={"Authorization": "Bearer relay"}, json=receipt
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/guest/actions/{job['id']}/claim",
                headers={"Authorization": "Bearer relay"},
                json={},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/guest/receipts",
                headers={"Authorization": "Bearer relay"},
                json=receipt | {"restore_task_registered": False},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/guest/receipts", headers={"Authorization": "Bearer relay"}, json=receipt
            ).status_code
            == 200
        )
        assert ledger.get(action["case_id"])["status"] == "MITIGATED"
    ledger.close()


def test_stable_equal_timestamp_pagination_filters_before_limit(tmp_path):
    ledger = Ledger(tmp_path)
    stamp = now()
    ids = []
    for i in range(15):
        event = {
            "id": str(uuid.uuid4()),
            "ts": stamp,
            "host": "app",
            "kind": "file.read" if i % 2 else "file.write",
            "sensor": "test",
            "data": {},
        }
        ledger.append(event)
        if i % 2:
            ids.append(event["id"])
    found, cursor = [], None
    while True:
        rows = ledger.events(before=stamp, kind="file.read", cursor=cursor, limit=2)
        if not rows:
            break
        found.extend(e["id"] for e in rows)
        cursor = (rows[-1]["ts"], rows[-1]["id"])
    assert sorted(found) == sorted(ids)
    ledger.close()


def test_zeek_partial_lines_restart_and_raw_audit_provenance(tmp_path):
    ledger = Ledger(tmp_path / "data")
    logs = tmp_path / "logs"
    logs.mkdir()
    record = json.dumps(
        {
            "ts": 1700000000.25,
            "uid": "C123",
            "id.orig_h": "172.28.80.20",
            "id.resp_h": "172.28.80.40",
            "password": "do-not-store",
        }
    ).encode()
    path = logs / "conn.log"
    path.write_bytes(record[:20])
    assert scan(ledger, logs, "network", "zeek") == 0
    path.write_bytes(record + b"\n")
    assert scan(ledger, logs, "network", "zeek") == 1
    assert scan(ledger, logs, "network", "zeek") == 0
    assert ledger.events()[0]["data"]["password"] == "[REDACTED]"
    ledger.close()
    reopened = Ledger(tmp_path / "data")
    assert scan(reopened, logs, "network", "zeek") == 0
    parsed = normalize(
        b'type=EXECVE msg=audit(1700000000.250:42): argc=1 a0="whoami"\n',
        "linux-audit",
        "audit",
        "audit",
    )
    assert parsed["sensor"] == "audit-log-v1" and parsed["data"]["serial"] == "42"
    reopened.close()
