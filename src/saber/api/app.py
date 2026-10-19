"""FastAPI application factory.

Endpoints are read-mostly and offline. Events are served only through the bounded
``QueryGateway``; a client never supplies `as_of` or `episode_id` (the session binds both).
Sealed truth and scenario ids are never exposed. Errors render as `{code, message, trace_id}`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from saber import __version__
from saber.catalog.loader import default_catalog
from saber.domain.errors import SaberError
from saber.domain.query import EventQueryRequest
from saber.episodes import build_episode
from saber.subtasks import implemented_ids
from saber.telemetry import FakeEventStore, QueryGateway


def create_app() -> FastAPI:
    app = FastAPI(
        title="SABER",
        version=__version__,
        description="SOC Agent Benchmark (offline-first, read-mostly).",
    )

    @app.exception_handler(SaberError)
    async def _saber_error(_: Request, exc: SaberError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.get("/health")
    def health() -> dict[str, Any]:
        cat = default_catalog()
        return {
            "status": "ok",
            "version": __version__,
            "env": "dev",
            "catalog_digest": cat.catalog_digest,
            "subtasks_total": len(cat.subtasks),
            "subtasks_implemented": len(implemented_ids()),
        }

    @app.get("/api/v1/subtasks")
    def list_subtasks(service: str | None = None, environment: str | None = None) -> dict[str, Any]:
        cat = default_catalog()
        impl = set(implemented_ids())
        rows = [
            {
                "id": s.id,
                "service": s.service,
                "environment": s.environment,
                "implemented": s.id in impl,
            }
            for s in cat.subtasks
            if (service is None or s.service == service)
            and (environment is None or s.environment == environment)
        ]
        return {"count": len(rows), "subtasks": rows}

    @app.get("/api/v1/subtasks/{subtask_id}/manifest")
    def manifest(subtask_id: str, seed: int = 42, variant: str = "default") -> dict[str, Any]:
        if subtask_id not in set(implemented_ids()):
            raise HTTPException(status_code=404, detail=f"{subtask_id} not implemented")
        try:
            episode = build_episode(subtask_id, seed, variant)
        except Exception as exc:  # noqa: BLE001 - surface as 400 with a typed message
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # Agent-visible manifest + inputs only; no sealed truth crosses this boundary.
        return episode.public_payload()

    @app.post("/api/v1/subtasks/{subtask_id}/events")
    def search_events(
        subtask_id: str, request: dict[str, Any], seed: int = 42, variant: str = "default"
    ) -> dict[str, Any]:
        """Bounded, session-scoped event search for an episode's as-of time.

        For DEV, each implemented subtask that publishes telemetry is loaded into a FakeEventStore;
        the session binds episode_id and the manifest deadline as the benchmark clock.
        """
        if subtask_id not in set(implemented_ids()):
            raise HTTPException(status_code=404, detail=f"{subtask_id} not implemented")
        episode = build_episode(subtask_id, seed, variant)
        events = _episode_events(subtask_id, episode)
        store = FakeEventStore(events)
        gateway = QueryGateway(store)
        # The benchmark clock is the task's visibility cutoff when it sets one; the episode
        # deadline is only a fallback. Using the cutoff prevents revealing events the task
        # intends to keep beyond the observation window.
        time_policy = episode.subtask.spec().time_policy
        as_of = time_policy.visibility_cutoff or episode.manifest.deadline_at or datetime.now(UTC)
        session = gateway.open_session(episode.bundle.episode_id, as_of)
        query = EventQueryRequest.model_validate(request or {})
        page = gateway.search(session, query)
        return page.model_dump(mode="json")

    @app.get("/api/v1/subtasks/{subtask_id}/report")
    def report(subtask_id: str, seeds: str = "1,42") -> dict[str, Any]:
        from saber.benchmark.report import subtask_report

        if subtask_id not in set(implemented_ids()):
            raise HTTPException(status_code=404, detail=f"{subtask_id} not implemented")
        seed_list = [int(x) for x in seeds.split(",") if x.strip()]
        return subtask_report(subtask_id, seed_list)

    return app


def _episode_events(subtask_id: str, episode: Any) -> list[Any]:
    """Project an episode's public inputs into NormalizedEvents where the subtask carries any.

    Most pilot FILE subtasks model their inputs as domain-specific blobs rather than normalized
    telemetry, so this returns an empty list for them; the endpoint still exercises the gateway
    guards (episode binding, as_of, budgets) deterministically.
    """
    _ = (subtask_id, episode)
    return []
