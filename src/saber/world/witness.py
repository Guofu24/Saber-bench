"""Executable feasibility witness.

The scenario solver reasons about feasibility from a `ScenarioSpec`. This module
validates that reasoning at the execution level: it builds the candidate action
sequence toward the objective, runs it through the real `World.act()` pathway in a
fresh isolated episode **with no blue intervention**, and verifies the objective
only from the independent `red_metrics` effect-based verifier -- never from the
solver's claim, the planner, or an HTTP status.

This measures STRUCTURAL feasibility (no blue). It is deliberately separate from
the blue-active runtime outcome (`scenario.compare_policies`): a scenario can be
structurally feasible yet contained once a blue team is actively defending.

A missing witness never means "impossible": `NO_WITNESS_FOUND` records only that
this solver produced no satisfying path. Private scenario metadata is never written
into world state, so it cannot reach any agent observation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from saber.world import red_metrics, scenario
from saber.world.models import Action
from saber.world.store import Store

WITNESS_STATUSES = (
    "WITNESS_VERIFIED",
    "WITNESS_FAILED",
    "NO_WITNESS_FOUND",
    "INVALID_SCENARIO",
    "UNKNOWN",
)

# Ordered candidate steps and the server-side transition each one should produce.
_STEPS = {
    "data_exfiltration": (
        ("browse", "portal document links listed"),
        ("login", "session established"),
        ("read_document", "unauthorized_access of a foreign document"),
        ("collect", "foreign bytes staged (collected_bytes)"),
        ("exfiltrate", "exfiltrated_bytes recorded (objective effect)"),
    ),
    "service_impact": (
        ("login", "session established"),
        ("disrupt", "service disruption recorded (objective effect)"),
    ),
}
_EFFECT_KEYS = (
    "unauthorized_access",
    "collected_bytes",
    "exfiltrated_bytes",
    "unauthorized_job",
    "disruption",
)


def _effect(store: Store, event_id: int | None) -> dict[str, Any]:
    if event_id is None:
        return {}
    row = store.db.execute("SELECT data FROM effects WHERE event_id=?", (event_id,)).fetchone()
    if not row:
        return {}
    data = json.loads(row[0])
    return {k: data[k] for k in _EFFECT_KEYS if data.get(k)}


def run_witness(spec: scenario.ScenarioSpec, root: Any) -> dict[str, Any]:
    """Execute the candidate path for one scenario and verify it from server effects."""
    static = scenario.feasibility(spec)
    cls = static["feasibility"]
    base = {
        "scenario": spec.id,
        "family": spec.family,
        "objective": spec.objective,
        "static_feasibility": cls,
        "static_reason": static["reason"],
        "note": "structural feasibility, no blue intervention",
    }
    if cls == "INVALID":
        return base | {"status": "INVALID_SCENARIO", "verified": False, "agree": True, "trace": []}
    if cls == "UNKNOWN":
        return base | {"status": "UNKNOWN", "verified": False, "agree": True, "trace": []}

    role = scenario.OBJECTIVE_ROLE[spec.objective]
    steps = _STEPS[spec.objective]
    store = Store(Path(root))
    try:
        world = scenario.materialize(store, spec)
        actor_id = next(a.id for a in world.config.actors if a.team == "red" and a.role == role)
        actor = world.actors[actor_id]
        target = f"work-{world.principals['client-1']}"

        trace: list[dict[str, Any]] = []
        used = 0  # red actions spent; the witness respects the scenario's action budget
        budget = spec.red_action_budget
        world.advance()  # tick 1
        # One wait action covers an initial outage (it also counts against the budget).
        if spec.initial_outage_ticks > 1 and used < budget:
            wait = spec.initial_outage_ticks - 1
            args = {"ticks": wait, "reason": "wait out the scenario outage"}
            result = world.act(actor, Action(tool="wait", args=args))
            used += 1
            trace.append(
                _record(world, actor_id, "wait", args, "wait out the outage", result, store)
            )
            for _ in range(wait):
                world.advance()
        for tool, expectation in steps:
            if used >= budget:  # budget exhausted: the objective cannot be reached in time
                break
            world.advance()
            args = (
                {"document": target} if tool in ("read_document", "collect", "exfiltrate") else {}
            )
            result = world.act(actor, Action(tool=tool, args=args))
            used += 1
            trace.append(_record(world, actor_id, tool, args, expectation, result, store))

        summary = red_metrics.summary(world)
        obj: dict[str, Any] = next((o for o in summary["objectives"] if o["actor"] == actor_id), {})
        verified = bool(obj.get("effect_verified"))
        if cls == "VALID_FEASIBLE":
            status = "WITNESS_VERIFIED" if verified else "WITNESS_FAILED"
        else:  # VALID_BLOCKED: executing the would-be path must NOT verify the objective
            status = "WITNESS_VERIFIED" if verified else "NO_WITNESS_FOUND"
        agree = (cls == "VALID_FEASIBLE") == verified
        return base | {
            "status": status,
            "verified": verified,
            "agree": agree,
            "actor": actor_id,
            "objective_status": obj.get("status"),
            "red_actions": sum(1 for t in trace if t["tool"] != "wait"),
            "trace": trace,
        }
    finally:
        store.close()


def _record(
    world: Any,
    actor_id: str,
    tool: str,
    args: dict[str, Any],
    expectation: str,
    result: dict[str, Any],
    store: Store,
) -> dict[str, Any]:
    return {
        "tick": world.tick,
        "actor": actor_id,
        "tool": tool,
        "args": args,
        "status": result.get("status"),
        "expected_transition": expectation,
        "observed_effect": _effect(store, result.get("event_id")),
        "event_id": result.get("event_id"),
    }


def witness_all(root: Any) -> list[dict[str, Any]]:
    base = Path(root)
    out = []
    for family in scenario.FAMILIES:
        spec = scenario.make(family)
        out.append(run_witness(spec, base / family))
    return out
