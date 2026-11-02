"""Authenticated sample vault and durable asynchronous offline analysis jobs."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from saber.lab.analyzers import AnalysisJob, AnalysisSettings, availability, execute
from saber.lab.capabilities import allowed
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger, now


class AnalysisQueue:
    def __init__(
        self,
        ledger: Ledger,
        credentials: dict[str, Any],
        settings: AnalysisSettings,
        assets: Path,
        emitter: Emitter,
    ) -> None:
        self.ledger, self.credentials, self.settings, self.assets, self.emitter = (
            ledger,
            credentials,
            settings,
            assets.resolve(),
            emitter,
        )
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="saber-analysis")
        self.gate = threading.Lock()
        self.upload_gate = threading.Lock()
        (ledger.root / "samples").mkdir(exist_ok=True)
        with ledger.lock:
            for row in ledger.db.execute(
                "SELECT k,v FROM state WHERE k LIKE 'analysis-job:%'"
            ).fetchall():
                value = json.loads(row[1])
                if value["state"] == "RUNNING":
                    value.update(
                        state="INDETERMINATE",
                        error="Analysis interrupted; inspect before a new request",
                    )
                    ledger.put(row[0], value)

    def loop(self) -> None:
        while not self.stop.is_set():
            if not self.process_one():
                self.stop.wait(0.2)

    def process_one(self) -> bool:
        if not self.gate.acquire(blocking=False):
            return False
        try:
            with self.ledger.lock:
                row = self.ledger.db.execute(
                    "SELECT k,v FROM state WHERE k LIKE 'analysis-job:%' AND json_extract(v,'$.state')='QUEUED' ORDER BY json_extract(v,'$.created_at') LIMIT 1"
                ).fetchone()
                if not row:
                    return False
                record = json.loads(row[1])
                record["state"] = "RUNNING"
                self.ledger.put(row[0], record)
            job = AnalysisJob.model_validate(record["request"])
            sample = self.ledger.get("sample:" + job.sample_id)
            try:
                result = execute(
                    job,
                    self.ledger.root / "samples" / job.sample_id,
                    sample["kind"],
                    self.ledger.root / "analysis" / job.id,
                    self.assets,
                    self.settings,
                )
            except (OSError, ValueError):
                result = {
                    "state": "FAILED",
                    "error": "Analyzer failed; diagnostics remain in the private analysis workspace",
                }
            record.update(state=result["state"], result=result, completed_at=now())
            try:
                record["evidence_id"] = self.emitter.emit(
                    "analysis.completed",
                    {
                        "job_id": job.id,
                        "actor": record["actor"],
                        "sample_id": job.sample_id,
                        "engine": job.engine,
                        "state": result["state"],
                        "pid": result.get("pid"),
                        "report_sha256": result.get("report_sha256"),
                    },
                )
            except OSError:
                record.update(
                    state="INDETERMINATE",
                    error="Result recorded but evidence emission failed; inspect storage budget",
                )
            self.ledger.put(row[0], record)
            return True
        finally:
            self.gate.release()

    def close(self) -> None:
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(self.settings.timeout_seconds + 5)


def create_analysis(queue: AnalysisQueue) -> FastAPI:
    app = FastAPI(title="SABER offline analysis vault")
    ledger, credentials, settings = queue.ledger, queue.credentials, queue.settings

    def operator(auth: str) -> bool:
        return bool(credentials.get("upload_token")) and secrets.compare_digest(
            auth, "Bearer " + credentials["upload_token"]
        )

    def identity(auth: str) -> dict[str, Any]:
        if operator(auth):
            return {"actor": "operator", "team": "blue", "role": "lead", "specialties": []}
        for token, actor in credentials.get("actor_capabilities", {}).items():
            if secrets.compare_digest(auth, "Bearer " + token):
                return dict(actor)
        raise HTTPException(403, "Analysis capability required")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": queue.thread.is_alive(), "service": "analysis"}

    @app.get("/tools")
    def tools(authorization: str = Header(default="")) -> dict[str, Any]:
        identity(authorization)
        return {"tools": availability(settings), "sample_limit_mb": settings.max_sample_mb}

    @app.get("/samples")
    def samples(authorization: str = Header(default="")) -> dict[str, Any]:
        identity(authorization)
        with ledger.lock:
            rows = ledger.db.execute(
                "SELECT v FROM state WHERE k LIKE 'sample:%' ORDER BY k LIMIT 1000"
            ).fetchall()
        return {"samples": [json.loads(r[0]) for r in rows], "limit": 1000}

    @app.post("/samples/{sample_id}")
    async def upload(
        sample_id: str,
        request: Request,
        authorization: str = Header(default=""),
        x_saber_kind: str = Header(default="binary"),
    ) -> dict[str, Any]:
        import re

        if not operator(authorization):
            raise HTTPException(403, "Operator upload capability required")
        if not re.fullmatch(r"[a-f0-9]{64}", sample_id) or x_saber_kind not in (
            "binary",
            "memory",
            "pcap",
        ):
            raise HTTPException(422, "Invalid sample hash/type")
        if not queue.upload_gate.acquire(blocking=False):
            raise HTTPException(429, "Another sample upload is in progress")
        temporary = ledger.root / "samples" / ("upload-" + uuid.uuid4().hex)
        try:
            old = ledger.get("sample:" + sample_id)
            if old:
                if old["kind"] != x_saber_kind:
                    raise HTTPException(409, "Sample kind is immutable")
                return dict(old)
            used = sum(
                p.stat().st_size
                for p in ledger.root.rglob("*")
                if p.is_file() and not p.is_symlink()
            )
            digest, count = hashlib.sha256(), 0
            with temporary.open("xb") as stream:
                async for chunk in request.stream():
                    count += len(chunk)
                    if (
                        count > settings.max_sample_mb * 1024 * 1024
                        or used + count >= ledger.budget
                    ):
                        raise HTTPException(413, "Sample or disk budget exceeded")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if count == 0 or digest.hexdigest() != sample_id:
                raise HTTPException(422, "Sample checksum mismatch or empty sample")
            destination = ledger.root / "samples" / sample_id
            if destination.exists():
                raise HTTPException(
                    409, "Unregistered sample file exists; operator inspection required"
                )
            temporary.replace(destination)
            value = {
                "id": sample_id,
                "sha256": sample_id,
                "kind": x_saber_kind,
                "bytes": count,
                "registered_at": now(),
            }
            ledger.put("sample:" + sample_id, value)
            return value
        finally:
            temporary.unlink(missing_ok=True)
            queue.upload_gate.release()

    @app.post("/jobs")
    def submit(job: AnalysisJob, authorization: str = Header(default="")) -> dict[str, Any]:
        actor = identity(authorization)
        if actor["actor"] != "operator" and "analyze_sample" not in allowed(
            actor["team"], actor["role"], tuple(actor.get("specialties", []))
        ):
            raise HTTPException(403, "Analysis role required")
        if not ledger.get("sample:" + job.sample_id):
            raise HTTPException(404, "Unknown registered sample")
        if not availability(settings)[job.engine]["available"]:
            raise HTTPException(503, "Requested analyzer dependency is missing")
        request = job.model_dump()
        with ledger.lock:
            old = ledger.get("analysis-job:" + job.id)
            if old:
                if old["request"] != request or old["actor"] != actor["actor"]:
                    raise HTTPException(409, "Job ID cannot change its actor or operation")
                return dict(old)
            pending = ledger.db.execute(
                "SELECT count(*) FROM state WHERE k LIKE 'analysis-job:%' AND json_extract(v,'$.state') IN ('QUEUED','RUNNING')"
            ).fetchone()[0]
            if pending >= 20:
                raise HTTPException(429, "Analysis queue full")
            record = {
                "id": job.id,
                "actor": actor["actor"],
                "request": request,
                "state": "QUEUED",
                "created_at": now(),
            }
            ledger.put("analysis-job:" + job.id, record)
        return record

    @app.get("/jobs/{job_id}")
    def status(job_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
        actor = identity(authorization)
        record = ledger.get("analysis-job:" + job_id)
        if not record or (record["actor"] != actor["actor"] and actor["actor"] != "operator"):
            raise HTTPException(404, "Unknown actor analysis job")
        return dict(record)

    return app
