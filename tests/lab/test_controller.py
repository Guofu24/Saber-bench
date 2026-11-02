import json
import os
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from saber.lab.controller import Controller
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger
from saber.lab.worker import create_worker

from .test_services import served


def test_controller_reconciles_completed_job_without_repeating_side_effect(
    lab, tmp_path, monkeypatch
):
    spec, creds, _, _, _, app, collector = lab
    worker_store = Ledger(tmp_path / "worker")
    emitter = Emitter(worker_store, "client-test", "", creds["client"]["ingest_token"])
    with served(app) as app_url, served(collector) as collector_url:
        worker = create_worker(
            worker_store, creds["client"], "client", app_url, collector_url, emitter, browser=False
        )
        with served(worker) as worker_url:
            controller = Controller(
                spec,
                tmp_path / "control",
                creds["controller"],
                {"client": worker_url},
                collector_url,
            )
            actor = next(a for a in spec.actors if a.team == "client")
            from saber.lab import controller as module

            real = module.request

            def lost_response(url, **kwargs):
                value = real(url, **kwargs)
                if url.endswith("/execute"):
                    raise ConnectionError("response lost after actual execution")
                return value

            monkeypatch.setattr(module, "request", lost_response)
            controller.actor_step(actor, 1)
            assert controller.store.get("lab-pending", actor.id)
            launches = [e for e in worker_store.events() if e["kind"] == "process.launch"]
            assert len(launches) == 1
            controller.actor_step(actor, 2)
            assert controller.store.get("lab-pending", actor.id) is None
            assert controller.store.get("lab-memory", actor.id)["turn"] == 1
            assert len([e for e in worker_store.events() if e["kind"] == "process.launch"]) == 1
            controller.publish()
            snapshot = json.loads((tmp_path / "control/office.json").read_text())
            assert snapshot["execution_mode"] == "range"
            assert next(a for a in snapshot["actors"] if a["id"] == actor.id)["executor"]["pid"] > 0
            page = json.loads((tmp_path / "control/range-office/client-1.json").read_text())
            assert page["entries"][0]["result"]["pid"] > 0
            assert page["entries"][0]["job_id"] == launches[0]["data"]["job_id"]
            controller.close()
    worker_store.close()


def test_three_team_scheduler_uses_real_executors_and_observed_evidence(lab, tmp_path):
    spec, creds, _, collector_store, app_emitter, app, collector = lab
    spec.actors = [
        a for a in spec.actors if a.id in ("client-1", "red-access", "blue-ir", "blue-content")
    ]
    spec.tick_seconds = 0.1
    ledgers, emitters = [], [app_emitter]
    with ExitStack() as stack:
        app_url = stack.enter_context(served(app))
        collector_url = stack.enter_context(served(collector))
        app_emitter.collector = collector_url
        app_emitter.start()
        urls = {}
        for team in ("client", "red", "blue"):
            store = Ledger(tmp_path / team)
            ledgers.append(store)
            emitter = Emitter(store, team + "-test", collector_url, creds[team]["ingest_token"])
            emitter.start()
            emitters.append(emitter)
            worker = create_worker(
                store, creds[team], team, app_url, collector_url, emitter, browser=False
            )
            urls[team] = stack.enter_context(served(worker))
        controller = Controller(
            spec, tmp_path / "control", creds["controller"], urls, collector_url
        )
        try:
            controller.run(ticks=7)
            for emitter in emitters:
                while emitter.flush():
                    pass
            assert all(
                controller.store.get("lab-memory", a.id, {}).get("turn", 0) > 0 for a in spec.actors
            )
            assert any(
                e["kind"] == "file.read" and e["data"]["owner"] != e["data"]["principal"]
                for e in collector_store.events(limit=1000)
            )
            assert controller.store.get("lab", "metrics")["actions_scripted"] > 10
            assert not any(controller.store.items("lab-pending").values())
            controller.publish(stopped=True)
            page = json.loads((tmp_path / "control/range-office/client-1.json").read_text())
            assert any(e["evidence_complete"] for e in page["entries"])
            assert any(
                p["event"]["kind"] == "process.launch" and p["hash_verified"]
                for e in page["entries"]
                for p in e["evidence"]
            )
        finally:
            controller.close()
            for emitter in emitters:
                emitter.close()
            for store in ledgers:
                store.close()


@pytest.mark.integration
def test_real_chrome_browser_job_has_screenshot_and_process_receipt(lab, tmp_path):
    chrome = os.environ.get("SABER_TEST_CHROME")
    if not chrome:
        pytest.skip("Set SABER_TEST_CHROME to an existing browser for this integration check")
    pytest.importorskip("playwright.sync_api")
    _, creds, _, _, _, app, collector = lab
    store = Ledger(tmp_path / "browser-worker")
    emitter = Emitter(store, "client-browser", "", creds["client"]["ingest_token"])
    with served(app) as app_url, served(collector) as collector_url:
        worker = create_worker(
            store,
            creds["client"],
            "client",
            app_url,
            collector_url,
            emitter,
            browser_executable=chrome,
        )
        import uuid

        response = TestClient(worker).post(
            "/execute",
            headers={"Authorization": "Bearer " + creds["client"]["rpc_token"]},
            json={"id": str(uuid.uuid4()), "actor": "client-1", "tool": "browse", "args": {}},
        )
        result = response.json()
        assert response.status_code == 200 and result["exit_code"] == 0 and result["status"] == 200
        assert result["pid"] > 0
        assert any(a["name"] == "browser.png" and a["bytes"] > 1000 for a in result["artifacts"])
        assert (store.root / "workspace/client-1/browser.png").read_bytes().startswith(b"\x89PNG")
        artifact = next(a for a in result["artifacts"] if a["name"] == "browser.png")
        client = TestClient(worker)
        path = "/screens/client-1/" + artifact["sha256"]
        assert client.get(path).status_code == 403
        auth = {"Authorization": "Bearer " + creds["client"]["rpc_token"]}
        assert client.get(path, headers=auth).json()["sha256"] == artifact["sha256"]
        assert client.get("/screens/client-1/" + "0" * 64, headers=auth).status_code == 409
    store.close()


def test_busy_executor_does_not_advance_actor_and_uncertain_guest_stays_paused(
    lab, tmp_path, monkeypatch
):
    spec, creds, *_ = lab
    controller = Controller(
        spec, tmp_path / "busy", creds["controller"], {"client": "http://unused"}, "http://unused"
    )
    from saber.lab import controller as module

    calls = []

    def busy(url, **kwargs):
        calls.append((url, kwargs.get("body", {}).get("tool")))
        return 429, {"detail": "busy"}

    monkeypatch.setattr(module, "request", busy)
    actor = next(a for a in spec.actors if a.team == "client")
    try:
        controller.actor_step(actor, 1)
        assert controller.store.get("lab-memory", actor.id) is None
        assert controller.store.get("lab", "metrics") is None
        assert controller.store.get("lab-pending", actor.id) is None
        assert calls == [("http://unused/execute", "login")]
        with controller.store.transaction():
            controller.store.put(
                "lab-memory",
                actor.id,
                {"turn": 1, "result": {"guest_work": {"state": "INDETERMINATE", "id": "a" * 32}}},
            )
        controller.actor_step(actor, 2)
        assert calls[-1] == ("http://unused/execute", "windows_job_status")
        assert controller.store.get("lab-memory", actor.id)["turn"] == 1
        content = next(a for a in spec.actors if a.role == "content")
        obs = {
            "turn": 1,
            "result": {},
            "cases": [{"id": "case-domain", "rule": "lab-domain-failed-logon"}],
        }
        tool, _, _ = controller.choose(content, obs)
        assert tool == "evaluate_rule"
    finally:
        controller.close()
