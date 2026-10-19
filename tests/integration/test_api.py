"""API surface tests via FastAPI TestClient (offline, no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from saber.api import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["subtasks_total"] == 175
    assert body["subtasks_implemented"] >= 12
    assert len(body["catalog_digest"]) == 64


def test_list_subtasks_filtered(client: TestClient) -> None:
    r = client.get("/api/v1/subtasks", params={"environment": "vm"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 18
    assert all(s["environment"] == "vm" for s in body["subtasks"])


def test_manifest_has_no_truth(client: TestClient) -> None:
    r = client.get("/api/v1/subtasks/T1112.001/manifest", params={"variant": "tp", "seed": 1})
    assert r.status_code == 200
    text = r.text
    for forbidden in (
        "sealed_truth",
        "scenario_id",
        '"verdict": "TP"',
        '"verdict": "FP"',
        "is_malicious",
    ):
        assert forbidden not in text, forbidden
    body = r.json()
    assert body["manifest"]["subtask_id"] == "T1112.001"
    assert body["manifest"]["provenance_tags"] == ["DEV_FIXTURE"]


def test_manifest_unimplemented_404(client: TestClient) -> None:
    r = client.get("/api/v1/subtasks/T9999.999/manifest")
    assert r.status_code in (404, 422)


def test_events_endpoint_runs_gateway(client: TestClient) -> None:
    r = client.post("/api/v1/subtasks/T1112.001/events", json={"limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert "events" in body and "as_of" in body
    # Future window is denied by the gateway with a typed error envelope.
    bad = client.post("/api/v1/subtasks/T1112.001/events", json={"time_to": "2099-01-01T00:00:00Z"})
    assert bad.status_code == 403
    assert bad.json()["code"] == "time_leak_denied"


def test_report_endpoint(client: TestClient) -> None:
    r = client.get("/api/v1/subtasks/T0173.001/report", params={"seeds": "1,42"})
    assert r.status_code == 200
    body = r.json()
    assert body["oracle_full_credit"] is True
    assert body["labels"] == ["DEV_SIMULATION_ONLY"]
