"""Role-specific container/guest service entrypoint with graceful shutdown."""

from __future__ import annotations

import argparse
import json
import os
import socket
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from saber.lab.analysis_service import AnalysisQueue, create_analysis
from saber.lab.application import create_application
from saber.lab.collector import create_collector, flush_index
from saber.lab.controller import Controller
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger
from saber.lab.models import LabSpec
from saber.lab.retention import archive
from saber.lab.sensor import PollSensor
from saber.lab.soar import SoarRunner, create_soar
from saber.lab.worker import create_worker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--role",
        choices=["app", "collector", "worker", "controller", "analysis", "soar"],
        required=True,
    )
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--secrets", type=Path, default=Path("/run/secrets"))
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    args = parser.parse_args()
    spec = LabSpec.model_validate_json(args.spec.read_text(encoding="utf-8"))
    team = os.environ.get("SABER_TEAM", "client")
    name = team if args.role == "worker" else args.role
    credentials = json.loads((args.secrets / name).read_text(encoding="utf-8"))
    stop = threading.Event()
    threads = []
    ledger = Ledger(args.data, spec.evidence_budget_mb)
    collector_url = os.environ.get("SABER_COLLECTOR", "http://collector:8080")
    emitter = Emitter(
        ledger,
        name + "-" + socket.gethostname(),
        collector_url,
        credentials.get("ingest_token", ""),
    )
    sensor = PollSensor(emitter, args.data / ("documents" if args.role == "app" else "workspace"))
    controller: Controller | None = None
    analysis_queue: AnalysisQueue | None = None
    soar_runner: SoarRunner | None = None

    def retention_loop() -> None:
        while not stop.wait(60):
            try:
                archive(ledger, spec.retention_days)
            except (OSError, ValueError):
                ledger.put("retention_error", "Archive blocked; hot evidence retained")

    threads.append(threading.Thread(target=retention_loop, daemon=True))
    if args.role == "app":
        app = create_application(ledger, credentials, emitter)
    elif args.role == "collector":
        indexer = os.environ.get("SABER_INDEXER", "")
        index = "saber-" + spec.name
        app = create_collector(ledger, credentials, indexer, index)

        def index_loop() -> None:
            while not stop.wait(2):
                try:
                    flush_index(ledger, indexer, index)
                except (OSError, ValueError, ConnectionError):
                    continue

        threads.append(threading.Thread(target=index_loop, daemon=True))
    elif args.role == "soar":
        soar_runner = SoarRunner(
            ledger,
            credentials,
            spec.soar,
            collector_url,
            os.environ.get("SABER_APP", "http://app:8080"),
            emitter,
        )
        app = create_soar(soar_runner)
        threads.append(soar_runner.thread)
    elif args.role == "analysis":
        analysis_queue = AnalysisQueue(
            ledger,
            credentials,
            spec.analysis,
            Path(os.environ.get("SABER_ANALYSIS_ASSETS", "/config/analysis")),
            emitter,
        )
        app = create_analysis(analysis_queue)
        threads.append(analysis_queue.thread)
    elif args.role == "worker":
        app = create_worker(
            ledger,
            credentials,
            team,
            os.environ.get("SABER_APP", "http://app:8080"),
            collector_url,
            emitter,
        )
    else:
        # Quota provider uses the same persistent controller database, loaded only
        # under explicit Gemini opt-in. No worker receives provider credentials.
        controller = Controller(
            spec,
            args.data,
            credentials,
            {
                t: os.environ.get("SABER_" + t.upper(), f"http://{t}:8080")
                for t in ("client", "red", "blue")
            },
            collector_url,
        )
        if os.environ.get("SABER_LLM") == "1":
            from saber.world.key_layout import TeamKeyLayout
            from saber.world.quota import TeamQuotaProvider

            budget = int(os.environ.get("SABER_CALL_BUDGET", "0"))
            if budget < 1:
                raise ValueError("Explicit positive cumulative call budget required")
            controller.provider = TeamQuotaProvider(
                controller.store,
                TeamKeyLayout.from_file(Path("/run/secrets/gemini-pool")),
                model=os.environ.get("SABER_MODEL", "gemini-3.5-flash-lite"),
                call_budget=budget,
            )
        app = FastAPI(title="SABER lab controller")

        @app.get("/health")
        def controller_health() -> dict[str, Any]:
            return {"ok": controller_thread.is_alive(), "service": "controller"}

        controller_thread = threading.Thread(target=controller.run, daemon=True)
        threads.append(controller_thread)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        for thread in threads:
            thread.start()
        if args.role in ("app", "worker", "analysis", "soar"):
            emitter.start()
            if args.role in ("app", "worker"):
                sensor.start()
        yield
        stop.set()
        if controller:
            controller.stop.set()
        if analysis_queue:
            analysis_queue.stop.set()
        if soar_runner:
            soar_runner.stop.set()
        for thread in threads:
            thread.join(timeout=45)
        sensor.close()
        emitter.close()
        if controller:
            controller.close()
        if analysis_queue:
            analysis_queue.close()
        ledger.close()

    app.router.lifespan_context = lifespan

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"error": "Invalid request; input values redacted"}
        )

    uvicorn.run(
        app,
        host=args.bind,
        port=args.port,
        access_log=False,
        ssl_certfile=str(args.cert) if args.cert else None,
        ssl_keyfile=str(args.key) if args.key else None,
    )


if __name__ == "__main__":
    main()
