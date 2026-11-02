"""Actual file-backed business service with a deliberately configurable lab ACL.

No OS exploits or arbitrary commands. Red exercises only lab document authorization;
blue changes enforced service policy and sessions, with before/after evidence.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from saber.lab.capabilities import allowed
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger


class DocumentWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=2000)


class ResponseAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(contain|release|patch|unpatch)$")
    principal: str = Field(pattern=r"^acct-[a-f0-9]{12}$")
    evidence_id: str = Field(min_length=32, max_length=36)
    ttl_seconds: int = Field(default=60, ge=5, le=300)


def create_application(ledger: Ledger, credentials: dict[str, Any], emitter: Emitter) -> FastAPI:
    import time

    app = FastAPI(title="SABER business lab")
    accounts = credentials["accounts"]
    documents = ledger.root / "documents"
    documents.mkdir(exist_ok=True)
    for user, account in accounts.items():
        if account["team"] == "client" and not (documents / f"{user}.txt").exists():
            (documents / f"{user}.txt").write_text(
                f"SYNTHETIC business document owned by {user}\n", encoding="utf-8"
            )

    def identity(auth: str, active: bool = True) -> tuple[str, dict[str, Any]]:
        import secrets

        for user, account in accounts.items():
            if secrets.compare_digest(auth, "Bearer " + account["token"]):
                if active and ledger.get("blocked:" + user, 0) > time.time():
                    emitter.emit(
                        "auth.denied", {"principal": user, "reason": "contained", "status": 403}
                    )
                    raise HTTPException(403, "Session contained")
                return user, account
        raise HTTPException(401, "Authentication required")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "business-app"}

    @app.get("/", response_class=HTMLResponse)
    def portal() -> str:
        return """<!doctype html><html><meta charset="utf-8"><title>SABER Business Portal</title>
        <body><h1>Business workspace</h1><button id="login">Sign in</button><button id="documents">Documents</button>
        <pre id="output"></pre><script>
        async function call(path, method='GET') { const r=await fetch(path,{method});
          document.getElementById('output').textContent=JSON.stringify(await r.json(),null,2); }
        document.getElementById('login').onclick=()=>call('/login','POST');
        document.getElementById('documents').onclick=()=>call('/documents');
        </script></body></html>"""

    @app.post("/login")
    def login(authorization: str = Header(default="")) -> dict[str, Any]:
        user, _ = identity(authorization)
        ledger.put("session:" + user, True)
        eid = emitter.emit("auth.login", {"principal": user, "status": 200})
        return {"status": 200, "principal": user, "evidence_id": eid}

    @app.get("/documents")
    def listing(authorization: str = Header(default="")) -> dict[str, Any]:
        user, _ = identity(authorization)
        eid = emitter.emit("http.list", {"principal": user, "status": 200})
        return {
            "status": 200,
            "documents": [p.stem for p in documents.glob("*.txt")],
            "evidence_id": eid,
        }

    @app.get("/documents/{owner}")
    def read_document(owner: str, authorization: str = Header(default="")) -> Any:
        user, account = identity(authorization)
        if owner not in accounts or accounts[owner]["team"] != "client":
            raise HTTPException(404, "Unknown document")
        if not ledger.get("session:" + user, False):
            raise HTTPException(401, "Sign in first")
        allowed = not ledger.get("enforce_acl", False) or user == owner or account["team"] == "blue"
        if not allowed:
            eid = emitter.emit(
                "file.access_denied", {"principal": user, "owner": owner, "status": 403}
            )
            return JSONResponse(status_code=403, content={"status": 403, "evidence_id": eid})
        content = (documents / f"{owner}.txt").read_bytes()
        eid = emitter.emit(
            "file.read",
            {
                "principal": user,
                "owner": owner,
                "path": f"documents/{owner}.txt",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "status": 200,
            },
        )
        return {"status": 200, "text": content.decode(), "owner": owner, "evidence_id": eid}

    @app.put("/documents")
    def write_document(
        body: DocumentWrite, authorization: str = Header(default="")
    ) -> dict[str, Any]:
        user, account = identity(authorization)
        if account["team"] != "client" or not ledger.get("session:" + user, False):
            raise HTTPException(403, "Document write not permitted")
        content = body.text.encode()
        path = documents / f"{user}.txt"
        path.write_bytes(content)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        eid = emitter.emit(
            "file.write",
            {
                "principal": user,
                "owner": user,
                "path": f"documents/{user}.txt",
                "bytes": len(content),
                "sha256": digest,
                "status": 200,
            },
        )
        return {"status": 200, "sha256": digest, "evidence_id": eid}

    @app.get("/state")
    def state(authorization: str = Header(default="")) -> dict[str, Any]:
        user, account = identity(authorization, active=False)
        if account["team"] != "blue":
            raise HTTPException(403, "Blue role required")
        return {
            "acl": ledger.get("enforce_acl", False),
            "blocked": {
                p: ledger.get("blocked:" + p, 0)
                for p in accounts
                if ledger.get("blocked:" + p, 0) > time.time()
            },
        }

    def responder(auth: str) -> tuple[str, dict[str, Any]]:
        scoped = credentials.get("soar_response_token", "")
        if scoped and secrets.compare_digest(auth, "Bearer " + scoped):
            return "soar-service", {"team": "blue", "role": "lead"}
        return identity(auth)

    @app.get("/response-state/{principal}")
    def response_state(principal: str, authorization: str = Header(default="")) -> dict[str, Any]:
        _, account = responder(authorization)
        if account["team"] != "blue":
            raise HTTPException(403, "Blue capability required")
        if principal not in accounts or accounts[principal]["team"] == "blue":
            raise HTTPException(400, "Invalid lab principal")
        return {
            "blocked": ledger.get("blocked:" + principal, 0) > time.time(),
            "enforce_acl": bool(ledger.get("enforce_acl", False)),
        }

    @app.post("/respond")
    def respond(body: ResponseAction, authorization: str = Header(default="")) -> dict[str, Any]:
        user, account = responder(authorization)
        if account["team"] != "blue" or body.action not in allowed(
            account["team"], account["role"], tuple(account.get("specialties", []))
        ):
            raise HTTPException(403, "Response role required")
        if body.principal not in accounts or accounts[body.principal]["team"] == "blue":
            raise HTTPException(400, "Invalid lab response target")
        with ledger.lock:
            record = ledger.db.execute(
                "SELECT data FROM events WHERE id=?", (body.evidence_id,)
            ).fetchone()
        if not record:
            raise HTTPException(400, "Local service evidence required")
        import json

        evidence = json.loads(record[0])
        if (
            evidence["data"].get("principal") != body.principal
            or evidence["kind"] != "file.read"
            or evidence["data"].get("owner") == body.principal
        ):
            raise HTTPException(400, "Evidence does not support the scoped response")
        key = (
            "blocked:" + body.principal if body.action in ("contain", "release") else "enforce_acl"
        )
        before = ledger.get(key, False)
        after = (
            (time.time() + body.ttl_seconds if body.action == "contain" else 0)
            if key.startswith("blocked:")
            else body.action == "patch"
        )
        ledger.put(key, after)
        verified = ledger.get(key) == after
        eid = emitter.emit(
            "response." + body.action,
            {
                "principal": user,
                "target": body.principal,
                "evidence_id": body.evidence_id,
                "before": before,
                "after": after,
                "verified": verified,
                "status": 200,
            },
        )
        return {
            "status": 200,
            "verified": verified,
            "changed": before != after,
            "before": before,
            "after": after,
            "evidence_id": eid,
        }

    return app
