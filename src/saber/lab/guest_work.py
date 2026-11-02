"""Actor-scoped durable work queue for pre-reviewed Windows guest operations."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from saber.lab.capabilities import allowed
from saber.lab.ledger import Ledger, now

WORK_TEAMS = {
    "windows_work": "client",
    "windows_recon": "red",
    "windows_failed_logon": "red",
    "windows_inventory": "blue",
    "windows_collect_evidence": "blue",
}


class Work(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    tool: Literal[
        "windows_work",
        "windows_recon",
        "windows_failed_logon",
        "windows_inventory",
        "windows_collect_evidence",
    ]
    node: str = Field(pattern=r"^[a-z][a-z0-9-]{0,14}$")


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    state: Literal["SUCCEEDED", "FAILED", "INDETERMINATE"]
    node: str
    result: dict[str, Any]


class Reconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=20, max_length=1000)


def routes(app: FastAPI, ledger: Ledger, credentials: dict[str, Any]) -> None:
    def identity(auth: str) -> dict[str, Any]:
        for token, actor in credentials.get("actor_capabilities", {}).items():
            if secrets.compare_digest(auth, "Bearer " + token):
                return dict(actor)
        raise HTTPException(403, "Actor capability required")

    def relay(auth: str) -> None:
        if not credentials.get("relay_token") or not secrets.compare_digest(
            auth, "Bearer " + credentials["relay_token"]
        ):
            raise HTTPException(403, "Relay capability required")

    @app.post("/guest/work")
    def enqueue(body: Work, authorization: str = Header(default="")) -> dict[str, Any]:
        actor = identity(authorization)
        nodes = credentials.get("windows_nodes", [])
        node = next((n for n in nodes if n["name"] == body.node), None)
        if (
            actor["team"] != WORK_TEAMS[body.tool]
            or not node
            or body.tool
            not in allowed(actor["team"], actor["role"], tuple(actor.get("specialties", [])))
        ):
            raise HTTPException(403, "Tool or guest outside actor scope")
        if actor["team"] in ("client", "red") and node["role"] != "workstation":
            raise HTTPException(403, "Client/red work runs only on a lab workstation")
        digest = hashlib.sha256(
            json.dumps(body.model_dump() | {"actor": actor["actor"]}, sort_keys=True).encode()
        ).hexdigest()
        with ledger.lock:
            old: dict[str, Any] | None = ledger.get("guest-work:" + body.id)
            if old:
                if old["digest"] != digest:
                    raise HTTPException(409, "Job ID cannot change its operation")
                return old
            active = ledger.db.execute(
                "SELECT 1 FROM state WHERE k LIKE 'guest-work:%' AND json_extract(v,'$.actor')=? AND json_extract(v,'$.state') IN ('QUEUED','DISPATCHED','INDETERMINATE') AND json_extract(v,'$.resolution') IS NULL LIMIT 1",
                (actor["actor"],),
            ).fetchone()
            if active:
                raise HTTPException(
                    409, "Resolve the existing Windows job before submitting more work"
                )
            job = body.model_dump() | {
                "actor": actor["actor"],
                "state": "QUEUED",
                "digest": digest,
                "created_at": now(),
            }
            ledger.put("guest-work:" + body.id, job)
        return job

    @app.get("/guest/work/{job_id}")
    def status(job_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
        actor = identity(authorization)
        job: dict[str, Any] | None = ledger.get("guest-work:" + job_id)
        if not job or job["actor"] != actor["actor"]:
            raise HTTPException(404, "Unknown actor job")
        return job

    @app.get("/relay/work")
    def poll(authorization: str = Header(default="")) -> dict[str, Any]:
        relay(authorization)
        with ledger.lock:
            jobs = [
                json.loads(r[0])
                for r in ledger.db.execute(
                    "SELECT v FROM state WHERE k LIKE 'guest-work:%' AND json_extract(v,'$.state') IN ('QUEUED','DISPATCHED') ORDER BY json_extract(v,'$.created_at') LIMIT 50"
                )
            ]
        return {"jobs": jobs}

    @app.post("/relay/work/{job_id}/claim")
    def claim(job_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
        relay(authorization)
        with ledger.lock:
            job: dict[str, Any] | None = ledger.get("guest-work:" + job_id)
            if not job:
                raise HTTPException(404, "Unknown job")
            if job["state"] == "QUEUED":
                job["state"] = "DISPATCHED"
                ledger.put("guest-work:" + job_id, job)
        return job

    @app.post("/relay/work-receipts")
    def receipt(body: Receipt, authorization: str = Header(default="")) -> dict[str, Any]:
        relay(authorization)
        if len(json.dumps(body.result)) > 32768:
            raise HTTPException(413, "Guest result too large")
        with ledger.lock:
            job = ledger.get("guest-work:" + body.id)
            if not job or job["state"] == "QUEUED" or job["node"] != body.node:
                raise HTTPException(409, "Receipt not bound to a dispatched guest job")
            if body.state == "SUCCEEDED":
                result = body.result
                valid = isinstance(result.get("pid"), int) and result["pid"] > 0
                tool = job["tool"]
                if tool in ("windows_work", "windows_collect_evidence"):
                    key = "file_sha256" if tool == "windows_work" else "sha256"
                    valid = valid and bool(re.fullmatch(r"[a-f0-9]{64}", str(result.get(key, ""))))
                    valid = valid and isinstance(result.get("bytes"), int) and result["bytes"] > 0
                if tool == "windows_work":
                    valid = (
                        valid
                        and isinstance(result.get("path"), str)
                        and result["path"].startswith("\\\\")
                    )
                if tool == "windows_collect_evidence":
                    valid = valid and result.get("artifact") == "event-evidence.json"
                    valid = (
                        valid and isinstance(result.get("records"), int) and result["records"] >= 0
                    )
                if tool == "windows_recon":
                    valid = (
                        valid
                        and isinstance(result.get("dns"), list)
                        and isinstance(result.get("files"), list)
                    )
                if tool == "windows_inventory":
                    valid = (
                        valid
                        and isinstance(result.get("processes"), list)
                        and isinstance(result.get("connections"), list)
                    )
                if tool == "windows_failed_logon":
                    valid = (
                        valid
                        and result.get("account") == "saber-red"
                        and result.get("attempts") == 1
                    )
                    valid = valid and result.get("authentication_succeeded") is False
                if not valid:
                    raise HTTPException(
                        422, "Successful guest receipt requires measured operation evidence"
                    )
            if job["state"] != "DISPATCHED":
                if job["state"] != body.state or job.get("result") != body.result:
                    raise HTTPException(409, "Terminal receipt is immutable")
                return {"accepted": True}
            job.update(state=body.state, result=body.result, completed_at=now())
            ledger.put("guest-work:" + body.id, job)
        return {"accepted": True}

    @app.post("/relay/work/{job_id}/reconcile")
    def reconcile(
        job_id: str, body: Reconciliation, authorization: str = Header(default="")
    ) -> dict[str, Any]:
        from saber.lab.events import redact

        relay(authorization)
        with ledger.lock:
            job = ledger.get("guest-work:" + job_id)
            if not job or job["state"] != "INDETERMINATE":
                raise HTTPException(409, "Only an indeterminate guest receipt can be reconciled")
            if not job.get("resolution"):
                job["resolution"] = {
                    "at": now(),
                    "reason": redact(body.reason),
                    "disposition": "operator-inspected; resume permitted; original outcome remains unknown",
                }
                ledger.put("guest-work:" + job_id, job)
        return {"reconciled": True, "job_id": job_id, "state": job["state"]}
