"""Authenticated team executor with durable job IDs, process deadlines and artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from saber.lab.events import Emitter
from saber.lab.ledger import Ledger
from saber.lab.sensor import sensor_coverage
from saber.lab.task import TOOLS


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    actor: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    tool: str = Field(pattern=r"^[a-z_]{1,40}$")
    args: dict[str, Any] = Field(default_factory=dict)


def create_worker(
    ledger: Ledger,
    credentials: dict[str, Any],
    team: str,
    app_url: str,
    collector_url: str,
    emitter: Emitter,
    *,
    browser: bool = True,
) -> FastAPI:
    app = FastAPI(title=f"SABER {team} executor")
    accounts = {a["actor_id"]: a for a in credentials["accounts"].values()}
    gate = threading.Semaphore(1)

    @app.get("/jobs/{job_id}")
    def receipt(job_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
        if not secrets.compare_digest(authorization, "Bearer " + credentials["rpc_token"]):
            raise HTTPException(403, "Executor capability required")
        with ledger.lock:
            row = ledger.db.execute("SELECT result FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Job not recorded; outcome unknown to controller")
        return {
            "state": "COMPLETED" if row[0] else "INDETERMINATE",
            "result": json.loads(row[0]) if row[0] else None,
        }

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "team": team, "tools": sorted(TOOLS[team]), "sensor": sensor_coverage()}

    @app.post("/execute")
    def run(job: Job, authorization: str = Header(default="")) -> dict[str, Any]:
        if not secrets.compare_digest(authorization, "Bearer " + credentials["rpc_token"]):
            raise HTTPException(403, "Executor capability required")
        account = accounts.get(job.actor)
        if account is None or account["team"] != team or job.tool not in TOOLS[team]:
            raise HTTPException(403, "Actor/tool not available on this executor")
        if job.tool in (
            "contain",
            "release",
            "patch",
            "unpatch",
            "contain_domain_user",
        ) and account["role"] not in (
            "ir",
            "content",
            "lead",
        ):
            raise HTTPException(403, "Response role required")
        if len(json.dumps(job.args)) > 8192:
            raise HTTPException(413, "Arguments too large")
        if not gate.acquire(blocking=False):
            raise HTTPException(429, "Executor busy; job not accepted")
        try:
            try:
                fresh, saved = ledger.job(job.id, job.model_dump())
            except ValueError:
                raise HTTPException(409, "Job ID arguments conflict") from None
            if not fresh:
                if saved is None:
                    raise HTTPException(
                        409, "INDETERMINATE: job already started; inspect evidence before retry"
                    )
                return saved
            directory = ledger.root / "workspace" / job.actor
            directory.mkdir(parents=True, exist_ok=True)
            if directory.resolve() != directory.absolute() or any(
                p.is_symlink() for p in directory.iterdir()
            ):
                raise HTTPException(400, "Workspace links are forbidden")
            payload = {
                "team": team,
                "tool": job.tool,
                "args": job.args,
                "token": account["token"],
                "app": app_url,
                "collector": collector_url,
                "read_token": credentials.get("read_token", ""),
                "response_token": credentials.get("response_token", ""),
                "browser": browser,
            }
            argv = [sys.executable, "-m", "saber.lab.task"]
            env = {
                k: os.environ[k]
                for k in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PLAYWRIGHT_BROWSERS_PATH")
                if k in os.environ
            }
            # Explicit source path supports both exported packages and the project venv.
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
            start = time.monotonic()
            previous = {p.name: p.stat().st_mtime_ns for p in directory.iterdir() if p.is_file()}
            process = subprocess.Popen(
                argv,
                cwd=directory,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=os.name == "posix",
            )
            emitter.emit(
                "process.launch",
                {
                    "job_id": job.id,
                    "pid": process.pid,
                    "ppid": os.getpid(),
                    "command_line": subprocess.list2cmdline(argv),
                    "tool": job.tool,
                },
                "saber-executor-v1",
            )
            try:
                output, _ = process.communicate(json.dumps(payload).encode() + b"\n", timeout=30)
                result = (
                    json.loads(output)
                    if len(output) <= 2_000_000
                    else {"status": 502, "error": "OutputLimit"}
                )
            except subprocess.TimeoutExpired:
                if sys.platform != "win32":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.communicate()
                result = {
                    "status": 504,
                    "error": "Timeout; effect may be indeterminate, no automatic retry",
                }
            except (ValueError, OSError):
                result = {"status": 502, "error": "Invalid worker output; no automatic retry"}
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
            artifacts = []
            for name in ("browser.png", "read-document.txt", "collected.txt", "evidence.json"):
                path = directory / name
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and path.stat().st_mtime_ns != previous.get(name)
                ):
                    artifacts.append(
                        {
                            "name": name,
                            "bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                    )
            event_id = emitter.emit(
                "process.exit",
                {
                    "job_id": job.id,
                    "pid": process.pid,
                    "exit_code": process.returncode,
                    "duration_ms": round((time.monotonic() - start) * 1000),
                    "status": result.get("status"),
                    "artifacts": artifacts,
                },
                "saber-executor-v1",
            )
            result.update(
                {
                    "job_id": job.id,
                    "executor_host": emitter.host,
                    "pid": process.pid,
                    "exit_code": process.returncode,
                    "execution_evidence": event_id,
                    "artifacts": artifacts,
                }
            )
            ledger.finish(job.id, result)
            return result
        finally:
            gate.release()

    return app
