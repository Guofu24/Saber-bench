"""Evidence queries and case work, restricted to the authenticated local world.

Never read the private effects table or sealed archives. Analyst findings are
claims with citations, not evaluator labels. All writes run in World's transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from saber.world.environment import World
    from saber.world.models import Action, Actor


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Query(Arguments):
    world_id: str
    after_id: int = Field(default=0, ge=0)
    from_tick: int = Field(default=0, ge=0)
    as_of_tick: int = Field(ge=0)
    limit: int = Field(default=25, ge=1, le=50)
    principal: str | None = Field(default=None, max_length=100)
    tool: str | None = Field(default=None, max_length=40)
    target: str | None = Field(default=None, max_length=100)


class Evidence(Arguments):
    world_id: str
    evidence_ids: list[int] = Field(min_length=1, max_length=50)
    as_of_tick: int = Field(ge=0)


class CaseRef(Arguments):
    case_id: str


class CaseUpdate(CaseRef):
    expected_revision: int = Field(ge=0)
    note: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[int] = Field(default_factory=list, max_length=50)


class Finding(CaseUpdate):
    classification: Literal["UNDETERMINED", "TP", "FP"] = "UNDETERMINED"
    severity: Literal["critical", "high", "medium", "low", "unknown"] = "unknown"
    next_step: str = Field(default="", max_length=500)


HELP = {
    "query_events": "Search retained telemetry, oldest first. args: world_id, as_of_tick, after_id=0, from_tick=0, limit=25 (max 50), optional principal/tool/target exact filters. Follow next_after_id; retention gaps are explicit.",
    "get_evidence": "Fetch public telemetry by ID, including snapshots already held in cases. args: world_id, as_of_tick, evidence_ids (1..50). No evaluator truth or archive access.",
    "get_case": "Fetch a case outside the recent observation window. args: case_id. Includes revision for guarded updates.",
    "append_evidence": "Add observed events to an open case. args: case_id, expected_revision, evidence_ids (max 50), note. Existing evidence remains unchanged.",
    "record_finding": "Record an analyst claim, not ground truth. args: case_id, expected_revision, evidence_ids, note, classification (UNDETERMINED/TP/FP), severity (critical/high/medium/low/unknown), next_step.",
    "reopen_case": "Lead reopens a closed case for new evidence or a disputed decision. args: case_id, expected_revision, evidence_ids, note.",
}
READ_TOOLS = frozenset({"query_events", "get_evidence", "get_case"})
CASE_TOOLS = frozenset({"append_evidence", "record_finding"})


def scope(world: World, world_id: str, as_of_tick: int) -> None:
    if world_id != world.store.get("meta", "world_id"):
        raise ValueError("different world")
    if not 0 <= as_of_tick <= world.tick:
        raise ValueError("future or invalid cutoff")


def evidence(world: World, ids: list[int], cutoff: int) -> list[dict[str, Any]]:
    if not ids or len(ids) > 50 or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("invalid evidence ids")
    found = {e["id"]: e for e in world.store.evidence(ids, cutoff)}
    missing = set(ids) - found.keys()
    if missing:
        for case in world.store.items("cases").values():
            for event in case["evidence"]:
                if event["id"] in missing and event["tick"] <= cutoff:
                    found[event["id"]] = event
    if set(ids) - found.keys():
        raise ValueError("evidence unavailable at cutoff; may have left retention")
    return [found[i] for i in sorted(set(ids))]


def checked_case(world: World, args: CaseUpdate, *, closed: bool = False) -> dict[str, Any]:
    case = world._case({"case_id": args.case_id})
    if case.get("revision", 0) != args.expected_revision:
        raise ValueError("stale case revision")
    if not closed and case["status"] == "CLOSED":
        raise ValueError("reopen case before writing")
    return case


def save_case(world: World, case: dict[str, Any], actor: Actor, note: str) -> None:
    case["revision"] = int(case.get("revision", 0)) + 1
    case.setdefault("worklog", []).append(
        {"by": actor.id, "tick": world.tick, "note": note, "revision": case["revision"]}
    )
    # Case histories are durable; the world disk budget bounds growth.
    world.store.put("cases", case["id"], case)


def execute(world: World, actor: Actor, action: Action) -> tuple[int, dict[str, Any], str]:
    tool, raw = action.tool, action.args
    if tool == "query_events":
        query = Query.model_validate(raw)
        scope(world, query.world_id, query.as_of_tick)
        if query.from_tick > query.as_of_tick:
            raise ValueError("invalid time window")
        clauses = ["id>?", "tick>=?", "tick<=?"]
        params: list[Any] = [query.after_id, query.from_tick, query.as_of_tick]
        for field in ("principal", "tool", "target"):
            value = getattr(query, field)
            if value is not None:
                clauses.append(f"{field}=?")
                params.append(value)
        rows = world.store.db.execute(
            "SELECT id FROM events WHERE " + " AND ".join(clauses) + " ORDER BY id LIMIT ?",
            (*params, query.limit + 1),
        ).fetchall()
        ids = [int(r[0]) for r in rows[: query.limit]]
        events = world.store.evidence(ids, query.as_of_tick)
        oldest = world.store.db.execute("SELECT min(id), min(tick) FROM events").fetchone()
        return (
            200,
            {
                "events": events,
                "world_id": query.world_id,
                "as_of_tick": query.as_of_tick,
                "next_after_id": ids[-1] if ids else query.after_id,
                "has_more": len(rows) > query.limit,
                "retention": {
                    "first_event_id": oldest[0],
                    "first_tick": oldest[1],
                    "truncated_before": bool(oldest[0] and oldest[0] > 1),
                    "archives_searchable": False,
                },
            },
            "telemetry",
        )
    if tool == "get_evidence":
        lookup = Evidence.model_validate(raw)
        scope(world, lookup.world_id, lookup.as_of_tick)
        return (
            200,
            {"evidence": evidence(world, lookup.evidence_ids, lookup.as_of_tick)},
            "telemetry",
        )
    if tool == "get_case":
        ref = CaseRef.model_validate(raw)
        case = world._case(ref.model_dump())
        case.setdefault("revision", 0)
        return 200, {"case": case}, case["id"]
    request = (Finding if tool == "record_finding" else CaseUpdate).model_validate(raw)
    case = checked_case(world, request, closed=tool == "reopen_case")
    cited = evidence(world, request.evidence_ids, world.tick) if request.evidence_ids else []
    if tool == "append_evidence":
        if not cited:
            raise ValueError("evidence required")
        merged = {e["id"]: e for e in case["evidence"]}
        merged.update({e["id"]: e for e in cited})
        if len(merged) > 200:
            raise ValueError("split investigations larger than 200 events")
        case["evidence"] = [merged[i] for i in sorted(merged)]
        case["evidence_ids"] = sorted(merged)
        case["timeline"] = []  # Previous timeline no longer covers all case evidence.
        world._extend_case_evaluation(case, cited)
    elif tool == "record_finding":
        assert isinstance(request, Finding)
        if not set(request.evidence_ids) <= set(case["evidence_ids"]):
            raise ValueError("attach evidence before citing it")
        if request.classification != "UNDETERMINED" and not cited:
            raise ValueError("a verdict requires evidence")
        case["classification"] = request.classification
        case["severity"] = request.severity
        case["next_step"] = request.next_step
        case.setdefault("findings", []).append(
            request.model_dump(exclude={"case_id", "expected_revision"})
            | {"by": actor.id, "tick": world.tick}
        )
    elif tool == "reopen_case":
        if case["status"] != "CLOSED":
            raise ValueError("case is not closed")
        case["status"] = "OPEN"
        case["classification"] = "UNDETERMINED"
        case.pop("disposition", None)
    else:
        raise ValueError("unknown case operation")
    save_case(world, case, actor, request.note)
    return (
        200,
        {"case_id": case["id"], "revision": case["revision"], "message": "Case updated."},
        case["id"],
    )
