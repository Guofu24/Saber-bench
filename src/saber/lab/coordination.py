"""Actor-authenticated private team messages, case ownership and rule publication."""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from saber.lab.events import redact
from saber.lab.ledger import Ledger, now
from saber.lab.query import Search


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(pattern=r"^case-[a-f0-9-]{32,36}$")
    assignee: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    query: Search
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


def routes(app: FastAPI, ledger: Ledger, credentials: dict[str, Any]) -> None:
    def actor(auth: str) -> dict[str, Any]:
        for token, identity in credentials.get("actor_capabilities", {}).items():
            if secrets.compare_digest(auth, "Bearer " + token):
                return dict(identity)
        raise HTTPException(403, "Actor capability required")

    @app.get("/team/messages")
    def messages(authorization: str = Header(default="")) -> dict[str, Any]:
        identity = actor(authorization)
        return {
            "team": identity["team"],
            "messages": ledger.get("messages:" + identity["team"], [])[-50:],
        }

    @app.post("/team/messages")
    def share(body: Message, authorization: str = Header(default="")) -> dict[str, Any]:
        identity = actor(authorization)
        if body.evidence_ids and identity["team"] != "blue":
            raise HTTPException(403, "Only SOC can attach collector evidence")
        with ledger.lock:
            for eid in body.evidence_ids:
                if not ledger.db.execute("SELECT 1 FROM events WHERE id=?", (eid,)).fetchone():
                    raise HTTPException(400, "Unknown evidence")
            entry = {
                "actor": identity["actor"],
                "at": now(),
                "text": redact(body.text),
                "evidence_ids": body.evidence_ids,
            }
            history = ledger.get("messages:" + identity["team"], [])
            history.append(entry)
            ledger.put("messages:" + identity["team"], history[-500:])
        return {"shared": True, "team": identity["team"]}

    @app.post("/cases/assign")
    def assign(body: Assignment, authorization: str = Header(default="")) -> dict[str, Any]:
        identity = actor(authorization)
        if identity["team"] != "blue" or identity["role"] != "lead":
            raise HTTPException(403, "SOC lead required")
        if not any(
            a["actor"] == body.assignee and a["team"] == "blue"
            for a in credentials.get("actor_capabilities", {}).values()
        ):
            raise HTTPException(400, "Unknown blue assignee")
        with ledger.lock:
            case: dict[str, Any] | None = ledger.get(body.case_id)
            if not case:
                raise HTTPException(404, "Unknown case")
            case.update(assignee=body.assignee, assigned_by=identity["actor"], assigned_at=now())
            ledger.put(body.case_id, case)
        return {"case": case}

    @app.post("/rules")
    def publish(body: Rule, authorization: str = Header(default="")) -> dict[str, Any]:
        identity = actor(authorization)
        if identity["team"] != "blue" or identity["role"] not in ("content", "lead"):
            raise HTTPException(403, "Detection content role required")
        if not body.query.filters and not body.query.kind:
            raise HTTPException(400, "Rule requires a bounded predicate")
        # These are lab-only replay rules. Publication does not mutate external SIEM config.
        matched = ledger.events(
            before=now(),
            kind=body.query.kind,
            host=body.query.host,
            filters=body.query.filters,
            limit=1000,
        )
        ids = {e["id"] for e in matched}
        if not set(body.evidence_ids).issubset(ids):
            raise HTTPException(400, "Rule must reproduce its cited evidence on the raw store")
        query = body.query.model_dump(exclude_none=True)
        digest = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()
        version = {
            "name": body.name,
            "query": query,
            "sha256": digest,
            "author": identity["actor"],
            "at": now(),
            "evidence_ids": body.evidence_ids,
            "scope": "lab-replay-only",
        }
        ledger.put("detection-rule:" + body.name + ":" + digest, version)
        return {"published": True, "rule": version}
