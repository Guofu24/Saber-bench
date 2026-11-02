"""Real loopback services and child processes, with synthetic files only."""

import json
import socket
import threading
import time
import uuid
from contextlib import contextmanager

import pytest
import uvicorn
from fastapi.testclient import TestClient

from saber.lab.application import create_application
from saber.lab.collector import create_collector
from saber.lab.deployment import initialize_secrets, principal
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger
from saber.lab.models import preset_spec
from saber.lab.worker import create_worker


@contextmanager
def served(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive()


@pytest.fixture
def lab(tmp_path):
    spec = preset_spec("linux-small")
    initialize_secrets(tmp_path, spec)
    creds = {p.stem: json.loads(p.read_text()) for p in (tmp_path / ".secrets").glob("*.json")}
    app_store, collector_store = Ledger(tmp_path / "app"), Ledger(tmp_path / "collector")
    emit = Emitter(app_store, "app-test", "", creds["app"]["ingest_token"])
    app = create_application(app_store, creds["app"], emit)
    collector = create_collector(collector_store, creds["collector"])
    yield spec, creds, app_store, collector_store, emit, app, collector
    app_store.close()
    collector_store.close()


def auth(lab, actor):
    return {"Authorization": "Bearer " + lab[1]["app"]["accounts"][principal(actor)]["token"]}


def test_real_file_access_detection_containment_and_rollback(lab):
    _, creds, app_store, collector_store, emit, app, collector = lab
    client, soc = TestClient(app), TestClient(collector)
    owner = principal("client-1")
    client.post("/login", headers=auth(lab, "client-1"))
    client.put(
        "/documents", headers=auth(lab, "client-1"), json={"text": "SYNTHETIC BUSINESS FILE"}
    )
    assert (app_store.root / "documents" / f"{owner}.txt").read_text() == "SYNTHETIC BUSINESS FILE"
    client.post("/login", headers=auth(lab, "red-access"))
    attack = client.get("/documents/" + owner, headers=auth(lab, "red-access"))
    assert attack.status_code == 200 and attack.json()["text"] == "SYNTHETIC BUSINESS FILE"
    events = app_store.events()
    ingestion = soc.post(
        "/ingest",
        json={"events": events},
        headers={"Authorization": "Bearer " + creds["app"]["ingest_token"]},
    )
    assert ingestion.status_code == 200
    read_auth = {"Authorization": "Bearer " + creds["collector"]["read_token"]}
    case = soc.get("/cases", headers=read_auth).json()["cases"][0]
    assert case["evidence_ids"] == [attack.json()["evidence_id"]]
    body = {
        "action": "contain",
        "principal": principal("red-access"),
        "evidence_id": case["evidence_ids"][0],
    }
    assert client.post("/respond", json=body, headers=auth(lab, "red-access")).status_code == 403
    response = client.post("/respond", json=body, headers=auth(lab, "blue-ir"))
    assert response.json()["verified"]
    # Independently exercise the application after response, not just its reported flag.
    assert client.get("/documents/" + owner, headers=auth(lab, "red-access")).status_code == 403
    assert client.get("/documents/" + owner, headers=auth(lab, "client-1")).status_code == 200
    body["action"] = "release"
    assert client.post("/respond", json=body, headers=auth(lab, "blue-ir")).json()["verified"]
    assert client.get("/documents/" + owner, headers=auth(lab, "red-access")).status_code == 200
    body["action"] = "patch"
    client.post("/respond", json=body, headers=auth(lab, "blue-content"))
    assert client.get("/documents/" + owner, headers=auth(lab, "red-access")).status_code == 403
    assert client.get("/documents/" + owner, headers=auth(lab, "client-1")).status_code == 200
    assert (
        soc.post(
            "/search", json={}, headers={"Authorization": "Bearer " + creds["red"]["ingest_token"]}
        ).status_code
        == 403
    )
    forged = {**events[0], "host": "blue-stolen"}
    assert (
        soc.post(
            "/ingest",
            json={"events": [forged]},
            headers={"Authorization": "Bearer " + creds["red"]["ingest_token"]},
        ).status_code
        == 403
    )


def test_child_process_and_durable_deduplication(lab, tmp_path):
    _, creds, _, _, _, app, collector = lab
    store = Ledger(tmp_path / "worker")
    emitter = Emitter(store, "red-test", "", creds["red"]["ingest_token"])
    with served(app) as app_url, served(collector) as collector_url:
        worker = TestClient(
            create_worker(
                store, creds["red"], "red", app_url, collector_url, emitter, browser=False
            )
        )
        headers = {"Authorization": "Bearer " + creds["red"]["rpc_token"]}
        job = {"id": str(uuid.uuid4()), "actor": "red-access", "tool": "login"}
        first = worker.post("/execute", json=job, headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["status"] == 200 and first.json()["pid"] > 0
        assert worker.post("/execute", json=job, headers=headers).json() == first.json()
        assert len(store.events()) == 2
        assert (
            worker.post("/execute", json={**job, "tool": "browse"}, headers=headers).status_code
            == 409
        )
        assert (
            worker.post(
                "/execute",
                json={**job, "id": str(uuid.uuid4()), "tool": "contain"},
                headers=headers,
            ).status_code
            == 403
        )
        assert (
            worker.post(
                "/execute",
                json={**job, "id": str(uuid.uuid4()), "actor": "blue-ir"},
                headers=headers,
            ).status_code
            == 403
        )
        assert "token" not in json.dumps(store.events())
    store.close()


def test_transport_failure_retains_outbox_and_replay_is_idempotent(lab):
    _, creds, store, collected, emit, _, collector = lab
    emit.emit("file.observed", {"path": "business.txt", "api_key": "secret"})
    emit.collector = "http://127.0.0.1:1"
    with pytest.raises(ConnectionError):
        emit.flush()
    assert len(store.events(pending=True)) == 1
    with served(collector) as url:
        emit.collector = url
        assert emit.flush() == 1
        assert emit.flush() == 0
    assert len(collected.events()) == 1
    assert collected.events()[0]["data"]["api_key"] == "[REDACTED]"
