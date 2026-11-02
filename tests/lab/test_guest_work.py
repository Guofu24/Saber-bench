import uuid

from fastapi.testclient import TestClient

from saber.lab.collector import create_collector
from saber.lab.ledger import Ledger


def test_actor_windows_work_is_scoped_durable_and_receipt_cannot_change(tmp_path):
    credentials = {
        "sources": {},
        "read_token": "read",
        "relay_token": "relay",
        "actor_capabilities": {
            "client": {"actor": "client-1", "team": "client", "role": "employee"},
            "red": {"actor": "red-1", "team": "red", "role": "access"},
            "hunter": {"actor": "blue-1", "team": "blue", "role": "hunter"},
        },
        "windows_nodes": [
            {"name": "soc-ws-1", "role": "workstation"},
            {"name": "soc-dc", "role": "dc"},
        ],
    }
    ledger = Ledger(tmp_path)
    client = TestClient(create_collector(ledger, credentials))
    job = {"id": str(uuid.uuid4()), "node": "soc-ws-1", "tool": "windows_work"}
    auth = {"Authorization": "Bearer client"}
    assert (
        client.post("/guest/work", headers={"Authorization": "Bearer red"}, json=job).status_code
        == 403
    )
    assert (
        client.post("/guest/work", headers=auth, json=job | {"node": "soc-dc"}).status_code == 403
    )
    assert client.post("/guest/work", headers=auth, json=job).json()["state"] == "QUEUED"
    assert client.post("/guest/work", headers=auth, json=job).json()["id"] == job["id"]
    assert (
        client.post("/guest/work", headers=auth, json=job | {"id": str(uuid.uuid4())}).status_code
        == 409
    )
    assert (
        client.get("/guest/work/" + job["id"], headers={"Authorization": "Bearer red"}).status_code
        == 404
    )
    relay = {"Authorization": "Bearer relay"}
    assert (
        client.post("/relay/work/" + job["id"] + "/claim", headers=relay, json={}).json()["state"]
        == "DISPATCHED"
    )
    ledger.close()
    reopened = Ledger(tmp_path)
    client = TestClient(create_collector(reopened, credentials))
    assert client.get("/relay/work", headers=relay).json()["jobs"][0]["id"] == job["id"]
    receipt = {
        "id": job["id"],
        "node": "soc-ws-1",
        "state": "SUCCEEDED",
        "result": {"file_sha256": "a" * 64, "bytes": 40},
    }
    assert (
        client.post(
            "/relay/work-receipts", headers=relay, json=receipt | {"node": "soc-dc"}
        ).status_code
        == 409
    )
    assert client.post("/relay/work-receipts", headers=relay, json=receipt).status_code == 200
    assert client.post("/relay/work-receipts", headers=relay, json=receipt).status_code == 200
    assert (
        client.post(
            "/relay/work-receipts", headers=relay, json=receipt | {"state": "FAILED"}
        ).status_code
        == 409
    )
    assert client.get("/guest/work/" + job["id"], headers=auth).json()["result"]["bytes"] == 40
    assert not client.get("/relay/work", headers=relay).json()["jobs"]
    blue = {"Authorization": "Bearer hunter"}
    assert (
        client.post(
            "/guest/work",
            headers=blue,
            json=job | {"id": str(uuid.uuid4()), "tool": "windows_collect_evidence"},
        ).status_code
        == 403
    )
    reopened.close()
