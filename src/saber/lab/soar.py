"""Durable, evidence-bound playbooks with builtin, webhook and Shuffle orchestration."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from contextlib import suppress
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from saber.lab.capabilities import allowed
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger, now
from saber.lab.transport import request

PLAYBOOKS = {
    "triage": None,
    "contain_session": "contain",
    "release_session": "release",
    "enforce_acl": "patch",
    "revert_acl": "unpatch",
}


class WorkflowFailed(ValueError):
    """Vendor acknowledged a terminal failure; preserve any effect receipt."""


class SoarSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    backend: Literal["builtin", "webhook", "shuffle"] = "builtin"
    endpoint: str = ""
    external_network: str = Field(default="", pattern=r"^$|^[a-z][a-z0-9_-]{0,62}$")
    callback_base: str = "http://soar:8080"
    workflows: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, ge=30, le=1800)

    @model_validator(mode="after")
    def scoped(self) -> SoarSettings:
        for url in [self.callback_base, *([self.endpoint] if self.backend != "builtin" else [])]:
            p = urlsplit(url)
            if (
                p.scheme not in ("http", "https")
                or not p.hostname
                or p.username
                or p.password
                or p.query
                or p.fragment
                or p.path not in ("", "/")
            ):
                raise ValueError("SOAR requires explicit credential-free service origins")
        if self.backend != "builtin" and not self.external_network:
            raise ValueError("External SOAR requires an explicit isolated integration network")
        if any(
            k not in PLAYBOOKS or not re.fullmatch(r"[a-f0-9-]{32,36}", v)
            for k, v in self.workflows.items()
        ):
            raise ValueError("Invalid allowlisted workflow mapping")
        return self


class PlaybookJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    case_id: str = Field(pattern=r"^case-[a-f0-9-]{32,36}$")
    playbook: Literal["triage", "contain_session", "release_session", "enforce_acl", "revert_acl"]


class Reconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=20, max_length=1000)


def checked_proof(collector: str, token: str, eid: str) -> dict[str, Any]:
    code, proof = request(collector + "/evidence/" + eid, token=token)
    if code != 200:
        raise ConnectionError("Evidence not yet available")
    raw = json.dumps(
        proof["event"], sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode()
    if hashlib.sha256(raw).hexdigest() != proof["sha256"]:
        raise ValueError("SOAR evidence hash mismatch")
    return dict(proof)


class SoarRunner:
    def __init__(
        self,
        ledger: Ledger,
        credentials: dict[str, Any],
        settings: SoarSettings,
        collector: str,
        app_url: str,
        emitter: Emitter,
    ) -> None:
        self.ledger, self.credentials, self.settings = ledger, credentials, settings
        self.collector, self.app_url, self.emitter = collector, app_url, emitter
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="saber-soar")
        self.gate = threading.Lock()
        with ledger.lock:
            for row in ledger.db.execute(
                "SELECT k,v FROM state WHERE k LIKE 'soar-job:%'"
            ).fetchall():
                job = json.loads(row[1])
                if job["state"] == "DISPATCHING" or job.get("effect_state") == "STARTED":
                    job.update(
                        state="INDETERMINATE",
                        error="Interrupted dispatch/effect; no automatic retry",
                    )
                    ledger.put(row[0], job)

    def loop(self) -> None:
        while not self.stop.is_set():
            with suppress(OSError, ValueError, ConnectionError):
                self.process_one()
            self.stop.wait(1)

    def execute_bound(self, job_id: str) -> dict[str, Any]:
        with self.ledger.lock:
            job = self.ledger.get("soar-job:" + job_id)
            if job and job.get("effect_result"):
                return dict(job["effect_result"])
            if (
                not job
                or job.get("resolution")
                or job["state"] not in ("DISPATCHING", "RUNNING", "VERIFYING")
            ):
                raise ValueError("Job is not authorized for execution")
            if job.get("effect_state"):
                raise ValueError("Effect may already have executed; inspect receipt")
            job["effect_state"] = "STARTED"
            self.ledger.put("soar-job:" + job_id, job)
        action = PLAYBOOKS[job["request"]["playbook"]]
        if action is None:
            proofs = [
                checked_proof(self.collector, self.credentials["read_token"], eid)
                for eid in job["case"]["evidence_ids"][:20]
            ]
            result = {
                "status": 200,
                "verified": True,
                "evidence_ids": [p["event"]["id"] for p in proofs],
                "scope": "verified evidence collection; no incident verdict",
            }
        else:
            code, result = request(
                self.app_url + "/respond",
                token=self.credentials["app_token"],
                body={
                    "action": action,
                    "principal": job["case"]["principal"],
                    "evidence_id": job["case"]["evidence_ids"][0],
                    "ttl_seconds": 60,
                },
            )
            if code != 200 or result.get("verified") is not True:
                raise ConnectionError("Response was not acknowledged; outcome requires inspection")
        with self.ledger.lock:
            current = self.ledger.get("soar-job:" + job_id)
            current.update(effect_state="COMPLETED", effect_result=result)
            self.ledger.put("soar-job:" + job_id, current)
        return dict(result)

    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        settings = self.settings
        if settings.backend == "builtin":
            self.execute_bound(job["id"])
            return {"native": True}
        payload = {
            "job_id": job["id"],
            "playbook": job["request"]["playbook"],
            "case_id": job["case"]["id"],
            "evidence_ids": job["case"]["evidence_ids"],
            "callback_url": settings.callback_base.rstrip("/")
            + "/callbacks/"
            + job["id"]
            + "/execute",
        }
        if settings.backend == "shuffle":
            workflow = settings.workflows.get(job["request"]["playbook"])
            if not workflow:
                raise ValueError("No operator-approved Shuffle workflow mapping")
            code, result = request(
                settings.endpoint.rstrip("/") + "/api/v1/workflows/" + workflow + "/execute",
                token=self.credentials.get("external_token", ""),
                body={"execution_argument": json.dumps(payload)},
            )
            if (
                code != 200
                or result.get("success") is not True
                or not result.get("execution_id")
                or not result.get("authorization")
            ):
                raise ConnectionError("Shuffle did not return an execution receipt")
            return {
                "execution_id": result["execution_id"],
                "authorization": result["authorization"],
            }
        code, result = request(
            settings.endpoint.rstrip("/") + "/jobs",
            token=self.credentials.get("external_token", ""),
            body=payload,
        )
        if code not in (200, 202) or result.get("job_id") != job["id"]:
            raise ConnectionError("Webhook did not acknowledge the exact job ID")
        return {"job_id": job["id"]}

    def external_finished(self, job: dict[str, Any]) -> bool:
        if self.settings.backend == "builtin":
            return True
        receipt = self.ledger.get("soar-private:" + job["id"])
        endpoint = self.settings.endpoint.rstrip("/")
        if self.settings.backend == "shuffle":
            code, result = request(endpoint + "/api/v1/streams/results", body=receipt)
            if result.get("execution_id") != receipt["execution_id"]:
                raise ConnectionError("Mismatched Shuffle receipt")
            state = result.get("status")
            finished = state == "FINISHED"
        else:
            code, result = request(
                endpoint + "/jobs/" + job["id"], token=self.credentials.get("external_token", "")
            )
            if result.get("job_id") != job["id"]:
                raise ConnectionError("Mismatched webhook receipt")
            state, finished = result.get("state"), result.get("state") == "SUCCEEDED"
        if code != 200:
            raise ConnectionError("SOAR result temporarily unavailable")
        if state in ("FAILED", "ABORTED", "ERROR"):
            raise WorkflowFailed("External workflow failed")
        return bool(finished)

    def verify(self, job: dict[str, Any]) -> bool:
        result = job.get("effect_result")
        if not result:
            return False
        action = PLAYBOOKS[job["request"]["playbook"]]
        if action is None:
            return result.get("verified") is True
        proof = checked_proof(self.collector, self.credentials["read_token"], result["evidence_id"])
        event = proof["event"]
        if (
            event["kind"] != "response." + action
            or event["data"].get("target") != job["case"]["principal"]
            or event["data"].get("evidence_id") not in job["case"]["evidence_ids"]
        ):
            raise ValueError("Response evidence does not match this playbook")
        code, observed = request(
            self.app_url + "/response-state/" + job["case"]["principal"],
            token=self.credentials["app_token"],
        )
        if code != 200:
            return False
        return bool(
            observed["blocked"]
            if action == "contain"
            else not observed["blocked"]
            if action == "release"
            else observed["enforce_acl"]
            if action == "patch"
            else not observed["enforce_acl"]
        )

    def process_one(self) -> bool:
        if not self.gate.acquire(blocking=False):
            return False
        try:
            with self.ledger.lock:
                row = self.ledger.db.execute(
                    "SELECT v FROM state WHERE k LIKE 'soar-job:%' AND json_extract(v,'$.state') IN ('QUEUED','RUNNING','VERIFYING') ORDER BY coalesce(json_extract(v,'$.last_poll'),0) LIMIT 1"
                ).fetchone()
                if not row:
                    return False
                job = json.loads(row[0])
                job["last_poll"] = time.time()
                if job["state"] == "QUEUED":
                    job["state"] = "DISPATCHING"
                self.ledger.put("soar-job:" + job["id"], job)
            try:
                if time.time() > job["deadline"]:
                    raise ValueError("Verification deadline reached; inspect actual state")
                if job["state"] == "DISPATCHING":
                    private = self.dispatch(job)
                    self.ledger.put("soar-private:" + job["id"], private)
                    job = self.ledger.get("soar-job:" + job["id"])
                    job["state"] = "RUNNING"
                    self.ledger.put("soar-job:" + job["id"], job)
                if self.external_finished(job):
                    with self.ledger.lock:
                        job = self.ledger.get("soar-job:" + job["id"])
                        job["state"] = "VERIFYING"
                        self.ledger.put("soar-job:" + job["id"], job)
                    if self.verify(job):
                        job.update(state="SUCCEEDED", verified=True, completed_at=now())
                        job["evidence_id"] = self.emitter.emit(
                            "soar.completed",
                            {
                                "job_id": job["id"],
                                "case_id": job["case"]["id"],
                                "playbook": job["request"]["playbook"],
                                "verified": True,
                            },
                        )
                        self.ledger.put("soar-job:" + job["id"], job)
            except WorkflowFailed:
                current = self.ledger.get("soar-job:" + job["id"])
                current.update(
                    state="INDETERMINATE",
                    error="External workflow failed; inspect any applied effects before reconciliation",
                )
                self.ledger.put("soar-job:" + job["id"], current)
            except (OSError, ValueError, ConnectionError):
                current = self.ledger.get("soar-job:" + job["id"])
                if current["state"] == "DISPATCHING" or time.time() > current["deadline"]:
                    current.update(
                        state="INDETERMINATE",
                        error="Dispatch/effect/verification uncertain; no automatic resubmission",
                    )
                    self.ledger.put("soar-job:" + job["id"], current)
            return True
        finally:
            self.gate.release()


def create_soar(runner: SoarRunner) -> FastAPI:
    app = FastAPI(title="SABER scoped SOAR gateway")
    ledger, credentials = runner.ledger, runner.credentials

    def operator(auth: str) -> bool:
        return bool(credentials.get("operator_token")) and secrets.compare_digest(
            auth, "Bearer " + credentials["operator_token"]
        )

    def actor(auth: str) -> dict[str, Any]:
        for token, identity in credentials.get("actor_capabilities", {}).items():
            if secrets.compare_digest(auth, "Bearer " + token):
                return dict(identity)
        raise HTTPException(403, "Blue actor capability required")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "soar", "backend": runner.settings.backend}

    @app.post("/jobs")
    def submit(body: PlaybookJob, authorization: str = Header(default="")) -> dict[str, Any]:
        who = actor(authorization)
        tools = allowed(who["team"], who["role"], tuple(who.get("specialties", [])))
        effect = PLAYBOOKS[body.playbook]
        if "run_playbook" not in tools or (effect and effect not in tools):
            raise HTTPException(403, "Playbook exceeds this actor's response permissions")
        code, data = request(runner.collector + "/cases", token=credentials["read_token"])
        case = next((c for c in data.get("cases", []) if c["id"] == body.case_id), None)
        if code != 200 or not case or (effect and case.get("rule") != "cross-owner-document-read"):
            raise HTTPException(400, "Supported observed case required")
        payload = body.model_dump()
        with ledger.lock:
            old = ledger.get("soar-job:" + body.id)
            if old:
                if old["request"] != payload or old["actor"] != who["actor"]:
                    raise HTTPException(409, "Job ID operation cannot change")
                return dict(old)
            for row in ledger.db.execute("SELECT v FROM state WHERE k LIKE 'soar-job:%'"):
                other = json.loads(row[0])
                if (
                    not other.get("resolution")
                    and other["request"]["case_id"] == body.case_id
                    and other["state"]
                    in (
                        "QUEUED",
                        "DISPATCHING",
                        "RUNNING",
                        "VERIFYING",
                        "INDETERMINATE",
                    )
                ):
                    raise HTTPException(
                        409, "Existing case playbook requires completion or operator reconciliation"
                    )
            job = {
                "id": body.id,
                "request": payload,
                "actor": who["actor"],
                "case": case,
                "state": "QUEUED",
                "created_at": now(),
                "deadline": time.time() + runner.settings.timeout_seconds,
            }
            ledger.put("soar-job:" + body.id, job)
        return job

    @app.get("/jobs/{job_id}")
    def status(job_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
        job = ledger.get("soar-job:" + job_id)
        if not job or (
            not operator(authorization) and job["actor"] != actor(authorization)["actor"]
        ):
            raise HTTPException(404, "Unknown actor job")
        return dict(job)

    @app.post("/jobs/{job_id}/reconcile")
    def reconcile(
        job_id: str, body: Reconciliation, authorization: str = Header(default="")
    ) -> dict[str, Any]:
        if not operator(authorization):
            raise HTTPException(403, "Operator inspection required")
        with ledger.lock:
            job = ledger.get("soar-job:" + job_id)
            if not job or job["state"] != "INDETERMINATE":
                raise HTTPException(409, "Only uncertain jobs can be reconciled")
            if not job.get("resolution"):
                from saber.lab.events import redact

                job["resolution"] = {
                    "reason": redact(body.reason),
                    "at": now(),
                    "action": "release-case-hold; original outcome unchanged",
                }
                ledger.put("soar-job:" + job_id, job)
        return dict(job)

    @app.post("/callbacks/{job_id}/execute")
    def callback(job_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
        if not credentials.get("callback_token") or not secrets.compare_digest(
            authorization, "Bearer " + credentials["callback_token"]
        ):
            raise HTTPException(403, "Workflow callback capability required")
        try:
            return runner.execute_bound(job_id)
        except (OSError, ValueError, ConnectionError):
            raise HTTPException(
                409, "Bound effect unavailable or uncertain; inspect before retry"
            ) from None

    return app
