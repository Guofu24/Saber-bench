import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saber.lab.collector import create_collector
from saber.lab.events import SensorEvent
from saber.lab.ledger import Ledger, now
from saber.lab.logship import normalize, scan


def test_windows_evidence_queue_requires_capabilities_and_verified_rollback(tmp_path):
    ledger = Ledger(tmp_path)
    creds = {
        "windows_sources": ["soc-dc"],
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
            "data": {
                "event_id": 4625,
                "channel": "Security",
                "fields": {"TargetUserName": "saber-red"},
            },
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
    # Ephemeral log content for the redaction test, never a login credential.
    synthetic_marker = uuid.uuid4().hex
    record = json.dumps(
        {
            "ts": 1700000000.25,
            "uid": "C123",
            "id.orig_h": "172.28.80.20",
            "id.resp_h": "172.28.80.40",
            "password": synthetic_marker,
        }
    ).encode()
    path = logs / "conn.log"
    path.write_bytes(record[:20])
    assert scan(ledger, logs, "network", "zeek") == 0
    path.write_bytes(record + b"\n")
    assert scan(ledger, logs, "network", "zeek") == 1
    assert scan(ledger, logs, "network", "zeek") == 0
    assert ledger.events()[0]["data"]["password"] == "[REDACTED]"
    assert synthetic_marker not in json.dumps(ledger.events())
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


def test_windows_collector_executes_against_explicit_fixture_readers():
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell runtime unavailable for the Windows collector contract")
    root = Path(__file__).resolve().parents[2]
    # Pass a fresh marker to the fixture; no fixed password-like literal in source.
    synthetic_marker = uuid.uuid4().hex
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(Path(__file__).with_name("windows_collector_fixture.ps1")),
            "-CollectorScript",
            str(root / "infra/soc/windows/Collect-Events.ps1"),
            "-SyntheticMarker",
            synthetic_marker,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, "Collector fixture failed; this is not guest runtime acceptance"
    events = [SensorEvent.model_validate(e) for e in json.loads(result.stdout)]
    assert len(events) == 3
    security = next(e for e in events if e.data.get("event_id") == 4625)
    assert security.data["fields"]["TargetUserName"] == "saber-red"
    assert security.data["fields"]["Password"] == "[REDACTED]"
    assert synthetic_marker not in result.stdout
    assert events[-1].data["part_of_domain"] is True
