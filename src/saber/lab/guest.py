"""Narrow Windows relay protocol: event ingestion and evidence-backed AD containment."""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from saber.lab.ledger import Ledger, now


class GuestAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(pattern=r"^case-[a-f0-9-]{32,36}$")
    action: Literal["contain_domain_user"]


class GuestReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    state: Literal["SUCCEEDED", "FAILED", "INDETERMINATE"]
    disabled_observed: bool
    restore_task_registered: bool


def routes(app: FastAPI, ledger: Ledger, credentials: dict[str, Any]) -> None:
    def require(auth: str, key: str) -> None:
        if not credentials.get(key) or not secrets.compare_digest(
            auth, "Bearer " + credentials[key]
        ):
            raise HTTPException(403, "Scoped capability required")

    @app.post("/guest/actions")
    def enqueue(body: GuestAction, authorization: str = Header(default="")) -> dict[str, Any]:
        require(authorization, "response_token")
        case = ledger.get(body.case_id)
        if (
            not case
            or case.get("rule") != "lab-domain-failed-logon"
            or case.get("principal") != "saber-red"
        ):
            raise HTTPException(
                400, "Windows logon evidence for the synthetic lab account required"
            )
        job_id = hashlib.sha256((body.case_id + body.action).encode()).hexdigest()[:32]
        with ledger.lock:
            existing: dict[str, Any] | None = ledger.get("guest-job:" + job_id)
            if existing:
                return existing
            job = {
                "id": job_id,
                "case_id": body.case_id,
                "action": body.action,
                "account": "saber-red",
                "ttl_seconds": 300,
                "state": "QUEUED",
                "created_at": now(),
            }
            ledger.put("guest-job:" + job_id, job)
        return job

    @app.get("/guest/actions")
    def poll(authorization: str = Header(default="")) -> dict[str, Any]:
        require(authorization, "relay_token")
        with ledger.lock:
            jobs = [
                json.loads(r[0])
                for r in ledger.db.execute("SELECT v FROM state WHERE k LIKE 'guest-job:%'")
            ]
        return {"jobs": [j for j in jobs if j["state"] in ("QUEUED", "DISPATCHED")][:50]}

    @app.post("/guest/actions/{job_id}/claim")
    def claim(job_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
        require(authorization, "relay_token")
        with ledger.lock:
            job: dict[str, Any] | None = ledger.get("guest-job:" + job_id)
            if not job:
                raise HTTPException(404, "Unknown job")
            if job["state"] == "QUEUED":
                job["state"] = "DISPATCHED"
                ledger.put("guest-job:" + job_id, job)
        return job

    @app.post("/guest/receipts")
    def receipt(body: GuestReceipt, authorization: str = Header(default="")) -> dict[str, Any]:
        require(authorization, "relay_token")
        if body.state == "SUCCEEDED" and not (
            body.disabled_observed and body.restore_task_registered
        ):
            raise HTTPException(400, "Verified state and scheduled rollback required")
        with ledger.lock:
            job = ledger.get("guest-job:" + body.id)
            if not job or job["state"] == "QUEUED":
                raise HTTPException(409, "Job was not dispatched")
            if job["state"] not in ("DISPATCHED", body.state):
                raise HTTPException(409, "Receipt conflicts with terminal state")
            job.update(body.model_dump())
            job["completed_at"] = now()
            ledger.put("guest-job:" + body.id, job)
            case = ledger.get(job["case_id"])
            if not any(r.get("job_id") == body.id for r in case["responses"]):
                case["responses"].append(
                    {
                        "job_id": body.id,
                        "action": job["action"],
                        "verified": body.state == "SUCCEEDED",
                        "at": now(),
                    }
                )
                case["status"] = "MITIGATED" if body.state == "SUCCEEDED" else "OPEN"
                ledger.put(job["case_id"], case)
        return {"accepted": True}
