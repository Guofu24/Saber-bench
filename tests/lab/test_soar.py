"""Real loopback responses, plus contract servers for optional external orchestrators."""

import json
import uuid

import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from saber.lab.deployment import principal
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger
from saber.lab.soar import SoarRunner, SoarSettings, create_soar

from .test_services import auth, served


def headers(token):
    return {"Authorization": "Bearer " + token}


def incident(lab):
    _, creds, _, _, _, app, collector = lab
    http, soc = TestClient(app), TestClient(collector)
    http.post("/login", headers=auth(lab, "red-access"))
    http.post("/login", headers=auth(lab, "client-1"))
    assert (
        http.get("/documents/" + principal("client-1"), headers=auth(lab, "red-access")).status_code
        == 200
    )
    soc.post(
        "/ingest", json={"events": lab[2].events()}, headers=headers(creds["app"]["ingest_token"])
    )
    return soc.get("/cases", headers=headers(creds["controller"]["read_token"])).json()["cases"][0]


def test_real_playbook_enforcement_dedup_and_operator_reconciliation(lab, tmp_path, monkeypatch):
    case = incident(lab)
    creds = lab[1]
    store = Ledger(tmp_path / "soar")
    emitter = Emitter(store, "soar-test", "", creds["soar"]["ingest_token"])
    with served(lab[5]) as app_url, served(lab[6]) as collector:
        lab[4].collector = collector
        runner = SoarRunner(store, creds["soar"], SoarSettings(), collector, app_url, emitter)
        api = TestClient(create_soar(runner))
        ir = headers(creds["blue"]["actor_capabilities"]["blue-ir"])
        hunter = headers(creds["blue"]["actor_capabilities"]["blue-hunter"])
        job = {"id": str(uuid.uuid4()), "case_id": case["id"], "playbook": "contain_session"}
        assert api.post("/jobs", json=job, headers=hunter).status_code == 403
        assert api.post("/jobs", json=job, headers=ir).json()["state"] == "QUEUED"
        assert runner.process_one()
        assert api.get("/jobs/" + job["id"], headers=ir).json()["state"] == "VERIFYING"
        while lab[4].flush():
            pass
        runner.process_one()
        receipt = api.get("/jobs/" + job["id"], headers=ir).json()
        assert receipt["state"] == "SUCCEEDED" and receipt["verified"]
        http = TestClient(lab[5])
        assert (
            http.get(
                "/documents/" + principal("client-1"), headers=auth(lab, "red-access")
            ).status_code
            == 403
        )
        assert (
            http.get(
                "/documents/" + principal("client-1"), headers=auth(lab, "client-1")
            ).status_code
            == 200
        )
        assert api.post("/jobs", json=job, headers=ir).json() == receipt
        assert runner.execute_bound(job["id"]) == receipt["effect_result"]
        assert len([e for e in lab[2].events() if e["kind"] == "response.contain"]) == 1
        # Lose the reply after the real release. Restart must never repeat that effect.
        from saber.lab import soar as module

        original = module.request

        def lost_reply(url, **kwargs):
            value = original(url, **kwargs)
            if url.endswith("/respond"):
                raise ConnectionError("Lost response after execution")
            return value

        monkeypatch.setattr(module, "request", lost_reply)
        uncertain = job | {"id": str(uuid.uuid4()), "playbook": "release_session"}
        api.post("/jobs", json=uncertain, headers=ir)
        runner.process_one()
        again = SoarRunner(store, creds["soar"], SoarSettings(), collector, app_url, emitter)
        assert not again.process_one()
        assert store.get("soar-job:" + uncertain["id"])["state"] == "INDETERMINATE"
        assert len([e for e in lab[2].events() if e["kind"] == "response.release"]) == 1
        body = {"reason": "Inspected service: principal is released; no pending effect remains."}
        route = "/jobs/" + uncertain["id"] + "/reconcile"
        assert api.post(route, json=body, headers=ir).status_code == 403
        resolved = api.post(
            route, json=body, headers=headers(creds["soar"]["operator_token"])
        ).json()
        assert resolved["resolution"] and resolved["state"] == "INDETERMINATE"
        with pytest.raises(ValueError):
            again.execute_bound(uncertain["id"])
    store.close()


@pytest.mark.parametrize("backend", ["shuffle", "webhook"])
def test_external_completion_requires_real_bound_effect_and_private_receipt(lab, tmp_path, backend):
    case = incident(lab)
    creds = lab[1]["soar"] | {"external_token": "fixture-external"}
    vendor, seen = FastAPI(), {}
    workflow, execution = str(uuid.uuid4()), str(uuid.uuid4())

    @vendor.post("/api/v1/workflows/{workflow_id}/execute")
    def launch(workflow_id: str, body: dict, authorization: str = Header(default="")):
        assert workflow_id == workflow and authorization == "Bearer fixture-external"
        seen.update(json.loads(body["execution_argument"]))
        return {
            "success": True,
            "execution_id": execution,
            "authorization": "private-execution-capability",
        }

    @vendor.post("/api/v1/streams/results")
    def result(body: dict):
        assert body == {"execution_id": execution, "authorization": "private-execution-capability"}
        return {"execution_id": execution, "status": "FINISHED"}

    @vendor.post("/jobs")
    def webhook_launch(body: dict, authorization: str = Header(default="")):
        assert authorization == "Bearer fixture-external"
        seen.update(body)
        return {"job_id": body["job_id"]}

    @vendor.get("/jobs/{job_id}")
    def webhook_result(job_id: str):
        return {"job_id": job_id, "state": "SUCCEEDED"}

    store = Ledger(tmp_path / "soar")
    with served(vendor) as external, served(lab[5]) as app_url, served(lab[6]) as collector:
        lab[4].collector = collector
        settings = SoarSettings(
            backend=backend,
            endpoint=external,
            external_network="isolated-test",
            workflows={"contain_session": workflow},
        )
        runner = SoarRunner(
            store, creds, settings, collector, app_url, Emitter(store, "soar-test", "", "")
        )
        api = TestClient(create_soar(runner))
        actor = headers(lab[1]["blue"]["actor_capabilities"]["blue-ir"])
        job = {"id": str(uuid.uuid4()), "case_id": case["id"], "playbook": "contain_session"}
        api.post("/jobs", headers=actor, json=job)
        runner.process_one()
        pending = api.get("/jobs/" + job["id"], headers=actor).json()
        assert pending["state"] == "VERIFYING" and not pending.get("verified")
        assert "private-execution-capability" not in json.dumps(pending)
        assert "fixture-external" not in json.dumps(seen) and creds[
            "callback_token"
        ] not in json.dumps(seen)
        callback = "/callbacks/" + job["id"] + "/execute"
        assert api.post(callback, headers=actor).status_code == 403
        assert api.post(callback, headers=headers(creds["callback_token"])).status_code == 200
        while lab[4].flush():
            pass
        runner.process_one()
        assert api.get("/jobs/" + job["id"], headers=actor).json()["state"] == "SUCCEEDED"
    store.close()
