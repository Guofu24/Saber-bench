import hashlib
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from saber.lab.analysis_tools import execute
from saber.lab.capabilities import SPECIALIST, allowed
from saber.lab.collector import create_collector
from saber.lab.deployment import initialize_secrets
from saber.lab.ledger import Ledger, now
from saber.lab.models import preset_spec
from saber.lab.query import Predicate, normalized

from .test_services import served


def record(kind="windows.event", **data):
    return {
        "id": str(uuid.uuid4()),
        "ts": now(),
        "host": "soc-dc",
        "kind": kind,
        "sensor": "fixture",
        "data": data,
    }


def test_hunt_filters_run_before_limit_and_preserve_zeek_dotted_fields(tmp_path):
    ledger = Ledger(tmp_path)
    target = record(
        fields={"CommandLine": "cmd.exe /c whoami", "ProcessId": "42", "TargetUserName": "Analyst"}
    )
    ledger.append(target)
    for _ in range(1100):
        ledger.append(record(fields={"CommandLine": "powershell.exe -NoProfile"}))
    query = [
        Predicate(field="command_line", operator="contains", value="CMD.EXE"),
        Predicate(field="process_id", value="42"),
    ]
    assert [e["id"] for e in ledger.events(filters=query, limit=1)] == [target["id"]]
    assert (
        normalized(record(**{"id.orig_h": "10.1.2.3", "id.resp_h": "10.1.2.4"}))["destination_ip"]
        == "10.1.2.4"
    )
    with pytest.raises(ValueError):
        Predicate(field="data'); DROP TABLE events;--", value="x")
    ledger.close()


def test_private_handoffs_and_lead_only_assignments(tmp_path):
    spec = preset_spec("linux-small")
    initialize_secrets(tmp_path, spec)
    credentials = json.loads((tmp_path / ".secrets/collector.json").read_text())
    tokens = {
        identity["actor"]: token for token, identity in credentials["actor_capabilities"].items()
    }
    ledger = Ledger(tmp_path / "data")
    case_id = "case-" + str(uuid.uuid4())
    ledger.put(case_id, {"id": case_id, "responses": []})
    client = TestClient(create_collector(ledger, credentials))

    def auth(actor):
        return {"Authorization": "Bearer " + tokens[actor]}

    assert (
        client.post(
            "/team/messages", headers=auth("red-access"), json={"text": "Observed document IDs"}
        ).status_code
        == 200
    )
    assert client.get("/team/messages", headers=auth("red-recon")).json()["messages"]
    assert not client.get("/team/messages", headers=auth("blue-ir")).json()["messages"]
    body = {"case_id": case_id, "assignee": "blue-dfir"}
    assert client.post("/cases/assign", headers=auth("red-access"), json=body).status_code == 403
    assert client.post("/cases/assign", headers=auth("blue-hunter"), json=body).status_code == 403
    assert (
        client.post("/cases/assign", headers=auth("blue-lead"), json=body).json()["case"][
            "assignee"
        ]
        == "blue-dfir"
    )
    ledger.close()


def test_dfir_exports_provenance_and_fails_on_tampered_raw_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ledger = Ledger(tmp_path / "data")
    event = record("file.read", principal="synthetic-user", owner="different-user")
    ledger.append(event)
    case_id = "case-" + event["id"]
    ledger.put(case_id, {"id": case_id, "evidence_ids": [event["id"]], "responses": []})
    with served(
        create_collector(ledger, {"sources": {}, "read_token": "fixture-read"})
    ) as endpoint:
        job = {
            "tool": "export_case",
            "args": {"case_id": case_id},
            "collector": endpoint,
            "read_token": "fixture-read",
        }
        result = execute(job)
        assert result["analysis"]["verified_records"] == 1
        raw = (tmp_path / "case-evidence.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == result["analysis"]["exports"][0]["sha256"]
        assert json.loads(raw)["records"][0]["event"] == event
        with ledger.db:
            ledger.db.execute("UPDATE events SET sha256=? WHERE id=?", ("0" * 64, event["id"]))
        with pytest.raises(ValueError, match="integrity"):
            execute(job)
    ledger.close()


def test_specialties_have_real_separate_tool_sets_and_no_role_escalation():
    assert len(SPECIALIST) == 12
    assert "export_case" in allowed("blue", "dfir")
    assert "network_hunt" in allowed("blue", "network")
    assert "contain" not in allowed("blue", "hunter")
    assert "assign_case" not in allowed("blue", "ir")
    assert "contain" not in allowed("red", "access")
