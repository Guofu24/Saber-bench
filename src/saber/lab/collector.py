"""Authenticated ingestion, raw evidence, detection/cases and real OpenSearch delivery."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from saber.lab.coordination import routes as coordination_routes
from saber.lab.events import SensorEvent
from saber.lab.guest import routes as guest_routes
from saber.lab.guest_work import routes as guest_work_routes
from saber.lab.ledger import Ledger, now
from saber.lab.query import PATHS, Search, backend_predicates, normalized, public_event
from saber.lab.transport import request


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[SensorEvent] = Field(max_length=100)


def cutoff_time(value: str | None) -> str:
    try:
        stamp = datetime.fromisoformat(value or now())
        if stamp.tzinfo is None or stamp.astimezone(UTC) > datetime.now(UTC):
            raise ValueError("future")
        return stamp.astimezone(UTC).isoformat(timespec="milliseconds")
    except ValueError:
        raise HTTPException(400, "Invalid/future cutoff") from None


def flush_index(ledger: Ledger, indexer: str, index: str) -> int:
    if not indexer:
        return 0
    status, creation = request(
        indexer + "/" + index,
        method="PUT",
        body={
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "ts": {"type": "date"},
                    "host": {"type": "keyword"},
                    "kind": {"type": "keyword"},
                    "sensor": {"type": "keyword"},
                    "data": {"type": "object", "enabled": False},
                    "fields": {"properties": {k: {"type": "keyword"} for k in PATHS}},
                }
            }
        },
    )
    if status != 200 and not (
        status == 400
        and creation.get("error", {}).get("type") == "resource_already_exists_exception"
    ):
        raise ConnectionError("Indexer unavailable")
    target = indexer + "/" + index
    if (
        status == 200
        or ledger.get("indexed_fields_version") != 1
        or ledger.get("indexed_target") != target
    ):
        if status == 400:
            code, _ = request(
                indexer + "/" + index + "/_mapping",
                method="PUT",
                body={
                    "properties": {
                        "fields": {"properties": {k: {"type": "keyword"} for k in PATHS}}
                    }
                },
            )
            if code != 200:
                raise ConnectionError("Indexer normalized-field mapping unavailable")
        with ledger.lock, ledger.db:
            ledger.db.execute("UPDATE events SET delivered=0")
            ledger.put("indexed_fields_version", 1)
            ledger.put("indexed_target", target)
    sent = 0
    for event in ledger.events(pending=True, limit=100):
        status, result = request(
            f"{indexer}/{index}/_doc/{event['id']}",
            method="PUT",
            body=event | {"fields": normalized(event)},
        )
        if status not in (200, 201) or result.get("result") not in ("created", "updated"):
            raise ConnectionError("Indexer did not persist document")
        with ledger.lock, ledger.db:
            ledger.db.execute("UPDATE events SET delivered=1 WHERE id=?", (event["id"],))
        sent += 1
    ledger.put("indexer_last_success", now())
    return sent


def create_collector(
    ledger: Ledger, credentials: dict[str, Any], indexer: str = "", index: str = "saber-lab"
) -> FastAPI:
    app = FastAPI(title="SABER SOC evidence gateway")
    guest_routes(app, ledger, credentials)
    guest_work_routes(app, ledger, credentials)
    coordination_routes(app, ledger, credentials)

    def require_read(auth: str) -> None:
        if not secrets.compare_digest(auth, "Bearer " + credentials["read_token"]):
            raise HTTPException(403, "SOC capability required")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "collector",
            "indexer_last_success": ledger.get("indexer_last_success"),
            "retention_error": ledger.get("retention_error"),
        }

    @app.get("/status")
    def status(authorization: str = Header(default="")) -> dict[str, Any]:
        require_read(authorization)
        with ledger.lock:
            counts = ledger.db.execute(
                "SELECT count(*),coalesce(sum(delivered),0) FROM events"
            ).fetchone()
            sources = {
                r[0].split(":", 1)[1]: json.loads(r[1])
                for r in ledger.db.execute("SELECT k,v FROM state WHERE k LIKE 'source_seen:%'")
            }
        return {
            "raw_events": counts[0],
            "indexed_events": counts[1],
            "sources": sources,
            "indexer_last_success": ledger.get("indexer_last_success"),
        }

    @app.post("/ingest")
    def ingest(body: Batch, authorization: str = Header(default="")) -> dict[str, Any]:
        source = next(
            (
                s
                for s, token in credentials["sources"].items()
                if secrets.compare_digest(authorization, "Bearer " + token)
            ),
            None,
        )
        if source is None:
            raise HTTPException(403, "Collector source capability required")
        if any(e.host != source and not e.host.startswith(source + "-") for e in body.events):
            raise HTTPException(403, "Source cannot impersonate another host")
        accepted = []
        for event in body.events:
            raw = event.model_dump()
            try:
                fresh = ledger.append(raw)
            except ValueError:
                raise HTTPException(409, "Conflicting evidence ID") from None
            if fresh:
                ledger.put("source_seen:" + event.host, now())
                if (
                    source in credentials.get("windows_sources", [])
                    and event.kind == "windows.event"
                    and event.data.get("channel") == "Security"
                    and (
                        event.data.get("event_id") in (4625, 4771)
                        or (
                            event.data.get("event_id") == 4776
                            and str(event.data.get("fields", {}).get("Status", "")).lower()
                            not in ("", "0", "0x0", "0x00000000")
                        )
                    )
                    and event.data.get("fields", {}).get("TargetUserName", "").lower()
                    == "saber-red"
                ):
                    ledger.put(
                        "case-" + event.id,
                        {
                            "id": "case-" + event.id,
                            "status": "OPEN",
                            "opened_at": now(),
                            "rule": "lab-domain-failed-logon",
                            "evidence_ids": [event.id],
                            "principal": "saber-red",
                            "responses": [],
                        },
                    )
                # A transparent rule over service-observed evidence, never actor team labels.
                if (
                    source == "app"
                    and event.kind == "file.read"
                    and event.data.get("owner")
                    and event.data.get("owner") != event.data.get("principal")
                ):
                    case_id = "case-" + event.id
                    ledger.put(
                        case_id,
                        {
                            "id": case_id,
                            "status": "OPEN",
                            "opened_at": now(),
                            "rule": "cross-owner-document-read",
                            "evidence_ids": [event.id],
                            "principal": event.data["principal"],
                            "responses": [],
                        },
                    )
                if (
                    source == "app"
                    and event.kind.startswith("response.")
                    and event.data.get("verified")
                ):
                    case_id = "case-" + str(event.data.get("evidence_id", ""))
                    with ledger.lock:
                        case = ledger.get(case_id)
                        if case:
                            case["responses"].append(
                                {
                                    "event_id": event.id,
                                    "action": event.kind,
                                    "at": event.ts,
                                    "after": event.data.get("after"),
                                }
                            )
                            case["status"] = (
                                "MITIGATED"
                                if event.kind in ("response.patch", "response.contain")
                                else "REOPENED"
                            )
                            ledger.put(case_id, case)
            accepted.append(event.id)
        return {"accepted": accepted}

    @app.post("/search")
    def search(body: Search, authorization: str = Header(default="")) -> dict[str, Any]:
        require_read(authorization)
        cutoff = cutoff_time(body.before)
        selected = ledger.events(
            before=cutoff,
            after=body.after,
            host=body.host,
            kind=body.kind,
            cursor=body.cursor,
            limit=body.limit,
            filters=body.filters,
        )
        return {
            "events": selected,
            "as_of": cutoff,
            "source": "durable-raw-store",
            "next_cursor": [selected[-1]["ts"], selected[-1]["id"]]
            if len(selected) == body.limit
            else None,
        }

    @app.post("/siem/search")
    def siem_search(body: Search, authorization: str = Header(default="")) -> dict[str, Any]:
        require_read(authorization)
        if not indexer:
            raise HTTPException(503, "Indexer not configured")
        filters: list[dict[str, Any]] = [{"range": {"ts": {"lte": cutoff_time(body.before)}}}]
        if body.after:
            filters.append({"range": {"ts": {"gte": body.after}}})
        filters.extend(backend_predicates(body.filters))
        if body.host:
            filters.append({"term": {"host": body.host}})
        if body.kind:
            filters.append({"term": {"kind": body.kind}})
        try:
            status, data = request(
                f"{indexer}/{index}/_search",
                body={
                    "size": body.limit,
                    "sort": [{"ts": "desc"}, {"id": "desc"}],
                    "query": {"bool": {"filter": filters}},
                    **(
                        {
                            "search_after": [
                                int(datetime.fromisoformat(body.cursor[0]).timestamp() * 1000),
                                body.cursor[1],
                            ]
                        }
                        if body.cursor
                        else {}
                    ),
                },
            )
        except (OSError, ValueError, ConnectionError):
            raise HTTPException(503, "Indexer unavailable; raw evidence retained") from None
        if status != 200 or data.get("timed_out") or data.get("_shards", {}).get("failed", 0):
            raise HTTPException(503, "Indexer query failed or partial")
        hits = data["hits"]["hits"]
        return {
            "events": [public_event(h["_source"]) for h in hits],
            "source": "opensearch",
            "next_cursor": [hits[-1]["_source"]["ts"], hits[-1]["_source"]["id"]]
            if len(hits) == body.limit
            else None,
        }

    @app.get("/cases")
    def cases(authorization: str = Header(default="")) -> dict[str, Any]:
        require_read(authorization)
        with ledger.lock:
            values = [
                json.loads(r[0])
                for r in ledger.db.execute(
                    "SELECT v FROM state WHERE k LIKE 'case-%' ORDER BY json_extract(v,'$.opened_at') DESC LIMIT 1000"
                )
            ]
        return {"cases": values}

    @app.get("/evidence/{event_id}")
    def evidence(event_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
        require_read(authorization)
        with ledger.lock:
            row = ledger.db.execute(
                "SELECT data,sha256 FROM events WHERE id=?", (event_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(404, "Unknown evidence")
        return {"event": json.loads(row[0]), "sha256": row[1]}

    return app
