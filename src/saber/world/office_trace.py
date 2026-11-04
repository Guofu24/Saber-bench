"""Bounded operator traces from executed events and public case evidence only."""

from __future__ import annotations

import hashlib
from typing import Any

from saber.world.models import WorldConfig
from saber.world.store import Store

TRACE_LIMIT = 200
CASE_LIMIT = 12
RESPONSE_LIMIT = 8
SOURCES = {"llm", "scripted", "scripted-fallback"}


def trace(store: Store, config: WorldConfig, through_tick: int) -> dict[str, Any]:
    """Export no private plans/notebooks or evaluator labels.

    Imported-log tools have an explicit bounded, masked query/evidence preview;
    other action arguments and result bodies remain private.

    Call under the snapshot's store lock. Direct HTTP calls lack a planner journal;
    their source stays unknown rather than being attributed to Gemini.
    """
    principals = {
        "acct-" + hashlib.sha256(f"{config.seed}/{a.id}".encode()).hexdigest()[:12]: a.id
        for a in config.actors
    }
    actor_ids = {a.id for a in config.actors}
    events = store.events(through_tick=through_tick, limit=TRACE_LIMIT)
    visible_ids = {e["id"] for e in events}
    forensic_rows = sorted(
        (
            row
            for actor in config.actors
            for row in store.get("forensic-office", actor.id, [])
            if row["event_id"] in visible_ids
        ),
        key=lambda row: row["event_id"],
    )[-20:]
    forensic_results = {row["event_id"]: row["result"] for row in forensic_rows}
    journals: dict[int, tuple[str, dict[str, Any]]] = {
        row["event_id"]: (actor.id, row)
        for actor in config.actors
        for row in store.get("journals", actor.id, [])[-100:]
        if row.get("event_id") in visible_ids
    }
    cases = store.items("cases")
    rows = []
    for event in events:
        actor_id = principals.get(event["principal"])
        if actor_id is None:
            continue
        entry = journals.get(event["id"])
        journal: dict[str, Any] = entry[1] if entry and entry[0] == actor_id else {}
        requested_case = journal.get("action", {}).get("args", {}).get("case_id")
        case_id = event["target"] if event["target"] in cases else None
        if isinstance(requested_case, str) and requested_case in cases and event["status"] < 400:
            case_id = requested_case
        source = journal.get("source")
        rows.append(
            {
                "id": event["id"],
                "tick": event["tick"],
                "actor_id": actor_id,
                "tool": event["tool"][:80],
                "target": event["target"][:160],
                "target_actor_id": principals.get(event["target"]),
                "status": event["status"],
                "source": source if source in SOURCES else "unknown",
                "case_id": case_id,
                **(
                    {"forensics": forensic_results[event["id"]]}
                    if event["id"] in forensic_results
                    else {}
                ),
            }
        )
    referenced = {row["case_id"] for row in rows if row["case_id"]}
    relevant = [
        case
        for case in cases.values()
        if case["opened_tick"] <= through_tick
        and (visible_ids.intersection(case["evidence_ids"]) or case["id"] in referenced)
    ]
    relevant.sort(key=lambda case: (case["opened_tick"], case["id"]))
    case_rows = []
    for case in relevant[-CASE_LIMIT:]:
        case_rows.append(
            {
                "id": case["id"],
                "status": case["status"],
                "evidence_ids": [eid for eid in case["evidence_ids"] if eid in visible_ids][:50],
                "evidence_count": len(case["evidence_ids"]),
                "responses": [
                    {
                        "actor_id": response["by"],
                        "tick": response["tick"],
                        "tool": response["tool"][:80],
                        "target": response["target"][:160],
                        "verified": response["verified"] is True,
                    }
                    for response in case.get("responses", [])[-RESPONSE_LIMIT:]
                    if response.get("by") in actor_ids and response["tick"] <= through_tick
                ],
            }
        )
    return {"limit": TRACE_LIMIT, "events": rows, "cases": case_rows}
