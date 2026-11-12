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


# --- Multi-path witness (Phase 4.1B-1) ----------------------------------------
# A data_exfiltration scenario can expose several structurally distinct paths to the
# SAME verified objective (any foreign document's exfil). These functions execute each
# candidate path INDEPENDENTLY in a clean episode and verify it from server effects, and
# run one recovery episode that attempts a blocked path, receives the denial, then walks
# an alternative to the verified objective. Structural feasibility only -- no blue.

_EXPECT = {
    "browse": "portal document links listed",
    "login": "session established",
    "read_document": "read (200) or an access denial (403)",
    "collect": "foreign bytes staged (collected_bytes)",
    "exfiltrate": "exfiltrated_bytes recorded (objective effect)",
}


def _access_actor(world: Any) -> tuple[str, Any]:
    aid = next(a.id for a in world.config.actors if a.team == "red" and a.role == "access")
    return aid, world.actors[aid]


def _exfil_target(world: Any, client_index: int) -> str:
    return f"work-{world.principals[f'client-{client_index}']}"


def _prereq_chain(spec: scenario.ScenarioSpec, client_index: int) -> list[str]:
    """The prerequisite reference documents a clairvoyant reads, in order, for this client."""
    layout = scenario.prereq_layout(spec)
    target = scenario.client_document(spec.seed, client_index)
    chain: list[str] = layout["gates"].get(target, {}).get("chain", [])
    return chain


def _wait_out_outage(
    world: Any, actor: Any, spec: Any, store: Store, trace: list[dict[str, Any]]
) -> int:
    """Issue the single wait action that covers an initial outage; return actions spent."""
    if spec.initial_outage_ticks > 1:
        wait = spec.initial_outage_ticks - 1
        args = {"ticks": wait, "reason": "wait out the scenario outage"}
        result = world.act(actor, Action(tool="wait", args=args))
        trace.append(_record(world, actor.id, "wait", args, "wait out the outage", result, store))
        for _ in range(wait):
            world.advance()
        return 1
    return 0


def run_exfil_path(
    spec: scenario.ScenarioSpec, root: Any, client_index: int, *, apply_staged: bool = False
) -> dict[str, Any]:
    """Execute one candidate exfiltration path in a clean episode; verify from effects.

    `apply_staged=True` applies the scenario's staged per-document control before the
    path runs, which answers whether this path remains feasible after that control.
    """
    store = Store(Path(root))
    try:
        world = scenario.materialize(store, spec)
        actor_id, actor = _access_actor(world)
        target = _exfil_target(world, client_index)
        steps: list[tuple[str, dict[str, Any]]] = [("browse", {}), ("login", {})]
        if client_index in spec.gated_clients:
            steps.append(("read_document", {"document": scenario.INDEX_DOC}))
        for cid in _prereq_chain(spec, client_index):
            steps.append(("read_document", {"document": cid}))
        steps += [
            ("read_document", {"document": target}),
            ("collect", {"document": target}),
            ("exfiltrate", {"document": target}),
        ]

        trace: list[dict[str, Any]] = []
        budget = spec.red_action_budget
        world.advance()
        used = _wait_out_outage(world, actor, spec, store, trace)
        if apply_staged:
            scenario.apply_staged_restriction(world, spec)
        for tool, args in steps:
            if used >= budget:
                break
            world.advance()
            result = world.act(actor, Action(tool=tool, args=args))
            used += 1
            trace.append(_record(world, actor_id, tool, args, _EXPECT[tool], result, store))

        summary = red_metrics.summary(world)
        obj: dict[str, Any] = next((o for o in summary["objectives"] if o["actor"] == actor_id), {})
        read_status = next(
            (
                t["status"]
                for t in trace
                if t["tool"] == "read_document" and t["args"].get("document") == target
            ),
            None,
        )
        blocked_by = spec.document_acl or client_index in spec.restricted_clients
        return {
            "path_id": f"client-{client_index}",
            "client_index": client_index,
            "preconditions": {
                "restricted": bool(blocked_by),
                "gated": client_index in spec.gated_clients,
                "prereq_chain": len(_prereq_chain(spec, client_index)),
                "outage_ticks": spec.initial_outage_ticks,
                "staged_control_applied": apply_staged,
            },
            "action_budget": budget,
            "tick_budget": spec.tick_budget,
            "actions_used": used,
            "read_status": read_status,
            "verified": bool(obj.get("effect_verified")),
            "objective_status": obj.get("status"),
            "trace": trace,
        }
    finally:
        store.close()


def _recovery_episode(spec: scenario.ScenarioSpec, root: Any) -> dict[str, Any]:
    """One clean episode: attempt each path in order, skip a denied one, verify the next."""
    store = Store(Path(root))
    try:
        world = scenario.materialize(store, spec)
        actor_id, actor = _access_actor(world)
        trace: list[dict[str, Any]] = []
        budget = spec.red_action_budget
        world.advance()
        used = _wait_out_outage(world, actor, spec, store, trace)

        def do(tool: str, args: dict[str, Any], note: str) -> dict[str, Any]:
            nonlocal used
            world.advance()
            result: dict[str, Any] = world.act(actor, Action(tool=tool, args=args))
            used += 1
            trace.append(_record(world, actor_id, tool, args, note, result, store))
            return result

        if used < budget:
            do("browse", {}, "enumerate the document map")
        if used < budget:
            do("login", {}, "establish a session")

        # Scenario C: show Path A available, then an observable control blocks it.
        if spec.staged_restricted_clients and used < budget:
            i = spec.staged_restricted_clients[0]
            do(
                "read_document",
                {"document": _exfil_target(world, i)},
                f"probe client-{i} (available before the intervention)",
            )
            scenario.apply_staged_restriction(world, spec)
            trace.append(
                {
                    "tick": world.tick,
                    "actor": actor_id,
                    "tool": "(intervention)",
                    "args": {},
                    "status": None,
                    "expected_transition": f"control applied: client-{i} document restricted",
                    "observed_effect": {},
                    "event_id": None,
                }
            )

        verified_path: int | None = None
        for p in scenario.exfil_candidate_paths(spec):
            i = p["client_index"]
            if used >= budget:
                break
            target = _exfil_target(world, i)
            if i in spec.gated_clients and used < budget:
                do(
                    "read_document",
                    {"document": scenario.INDEX_DOC},
                    "satisfy the prerequisite index",
                )
            for cid in _prereq_chain(spec, i):
                if used < budget:
                    do("read_document", {"document": cid}, "satisfy the prerequisite chain")
            if used >= budget:
                break
            result = do("read_document", {"document": target}, f"attempt the client-{i} path")
            if result.get("status") != 200:
                continue  # denied: receive the feedback and explore the alternative
            if used < budget:
                do("collect", {"document": target}, "stage the foreign bytes")
            if used < budget:
                do("exfiltrate", {"document": target}, "exfiltrate to the local sink (objective)")
            summary = red_metrics.summary(world)
            obj: dict[str, Any] = next(
                (o for o in summary["objectives"] if o["actor"] == actor_id), {}
            )
            if obj.get("effect_verified"):
                verified_path = i
                break

        return {
            "status": "RECOVERY_VERIFIED" if verified_path is not None else "RECOVERY_NOT_VERIFIED",
            "verified_path": verified_path,
            "actions_used": used,
            "action_budget": budget,
            "trace": trace,
        }
    finally:
        store.close()


def witness_multipath(spec: scenario.ScenarioSpec, root: Any) -> dict[str, Any]:
    """Enumerate exfil paths, witness each independently, and run one recovery episode."""
    base = Path(root)
    static = scenario.feasibility(spec)
    paths_meta = scenario.exfil_candidate_paths(spec)
    per_path = [
        run_exfil_path(spec, base / f"path-{p['client_index']}", p["client_index"])
        for p in paths_meta
    ]
    after_control = None
    if spec.staged_restricted_clients:
        after_control = [
            run_exfil_path(
                spec, base / f"ctl-{p['client_index']}", p["client_index"], apply_staged=True
            )
            for p in paths_meta
        ]
    recovery = _recovery_episode(spec, base / "recovery")
    return {
        "scenario": spec.id,
        "family": spec.family,
        "objective": spec.objective,
        "static_feasibility": static["feasibility"],
        "static_reason": static["reason"],
        "distinct_paths": len(paths_meta),
        "verified_paths": [r["client_index"] for r in per_path if r["verified"]],
        "blocked_paths": [r["client_index"] for r in per_path if not r["verified"]],
        "per_path": per_path,
        "after_control": after_control,
        "recovery": recovery,
        "note": "structural multi-path feasibility, no blue intervention",
    }


def witness_multipath_all(root: Any) -> list[dict[str, Any]]:
    base = Path(root)
    return [
        witness_multipath(scenario.make(fam), base / fam) for fam in scenario.MULTIPATH_FAMILIES
    ]


def witness_prereq_all(root: Any) -> list[dict[str, Any]]:
    """Execute the clairvoyant prerequisite path for every Phase 4.1C-1 family and verify it.

    The witness reads the required chain in order (from the private layout) and verifies from
    server effects -- independent of observability, which only changes what an AGENT can see.
    """
    base = Path(root)
    return [witness_multipath(scenario.make(fam), base / fam) for fam in scenario.PREREQ_FAMILIES]
