"""Controlled evaluation of red policies over multi-path scenarios (Phase 4.1B-2).

This separates three things the previous phases could conflate: scenario *feasibility*
(independent of any red agent), *planning* competence (does the policy find a path it
had the information and budget to walk), and *information* limits (a prerequisite that
cannot be identified from any observation). Every policy runs under identical scenario
configurations and identical action/tick budgets; results are aggregated over seeds
(each seed permutes document identities) with Wilson intervals, never a single episode.

The reference solver and the offline optimal witness length are used ONLY here, offline,
as a clairvoyant diagnostic reference. They are never read by a policy during execution.
DEV_SIMULATION_ONLY; nothing here promotes any subtask to READY_BENCHMARK.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from saber.world import scenario
from saber.world.mission import wilson
from saber.world.store import Store

POLICY_NAMES = ("random", "naive", "adaptive", "online")

DIAGNOSES = (
    "OBJECTIVE_VERIFIED",
    "PLANNING_FAILURE",
    "EXPLORATION_FAILURE",
    "INFORMATION_LIMITATION",
    "BUDGET_EXHAUSTED",
    "ENVIRONMENT_BLOCKED",
    "BLUE_BLOCKED",
    "UNKNOWN",
)

# If a policy had this much budget beyond the clairvoyant optimum and could explore yet
# still failed a prerequisite path, the cause is the policy, not the hidden information.
_AMPLE_SEARCH_SLACK = 8


def _access_principal(spec: scenario.ScenarioSpec) -> str:
    config = scenario.build_config(spec)
    aid = next(a.id for a in config.actors if a.team == "red" and a.role == "access")
    return "acct-" + hashlib.sha256(f"{spec.seed}/{aid}".encode()).hexdigest()[:12]


def optimal_witness_length(spec: scenario.ScenarioSpec) -> int | None:
    """Clairvoyant lower bound: the shortest feasible path's action count (a reference).

    This is an UPPER BOUND on achievable efficiency, not a fair online competitor: it
    assumes the agent already knows every control and prerequisite. Labelled as such.
    """
    return scenario.feasibility(spec).get("min_actions")


def with_budget(spec: scenario.ScenarioSpec, budget: int, seed: int | None = None) -> Any:
    """A spec variant with a different action budget (and matching seed), for sweeps.

    Only the budget and seed change; ACLs, prerequisites and targets are untouched, so a
    sweep never weakens a scenario to help a policy.
    """
    s = seed if seed is not None else spec.seed
    return spec.model_copy(
        update={
            "red_action_budget": budget,
            "tick_budget": max(spec.tick_budget, budget * 3, 40),
            "seed": s,
            "id": f"{spec.family}/{spec.split}/{s}",
            # The declared label is not used by the evaluator; feasibility is recomputed.
            "expected_feasibility": scenario.feasibility(
                spec.model_copy(update={"red_action_budget": budget})
            )["feasibility"],
        }
    )


def evaluate_episode(spec: scenario.ScenarioSpec, policy_name: str, root: Any) -> dict[str, Any]:
    """Run one policy on one scenario and classify the outcome by cause."""
    res = scenario.run_scenario(spec, policy_name, root)
    principal = _access_principal(spec)
    store = Store(Path(root))
    try:
        evs = store.events(through_tick=10**9, limit=100000, principal=principal)
    finally:
        store.close()
    reads = [e for e in evs if e["tool"] == "read_document"]
    explored_public = any(
        e["status"] == 200 and not str(e["target"]).startswith("work-") for e in reads
    )
    attempted_foreign = any(str(e["target"]).startswith("work-") for e in reads)
    repeated = _repeated_actions(evs)
    ep: dict[str, Any] = {
        "scenario": spec.id,
        "family": spec.family,
        "policy": policy_name,
        "budget": spec.red_action_budget,
        "verified": bool(res["verified"]),
        "steps_to_objective": res["steps_to_objective"],
        "actions": len(evs),
        "rejected_actions": res["rejected_actions"],
        "blocked_by_blue": res["blocked_by_blue"] > 0,
        "blocked_by_environment": res["blocked_by_environment"] > 0,
        "client_mission_utility": res["client_mission_utility"],
        "explored_public": explored_public,
        "attempted_foreign": attempted_foreign,
        "repeated_actions": repeated,
        "optimal_witness_length": optimal_witness_length(spec),
    }
    ep["actions_over_optimal"] = (
        ep["actions"] - ep["optimal_witness_length"]
        if ep["verified"] and ep["optimal_witness_length"]
        else None
    )
    ep["diagnosis"] = diagnose(spec, ep)
    return ep


def _repeated_actions(evs: list[dict[str, Any]]) -> int:
    """Count identical (tool, target, status) read/collect actions after the first."""
    seen: set[tuple[str, str, int]] = set()
    repeats = 0
    for e in evs:
        if e["tool"] not in ("read_document", "collect", "exfiltrate"):
            continue
        key = (e["tool"], str(e["target"]), int(e["status"]))
        if key in seen:
            repeats += 1
        seen.add(key)
    return repeats


def diagnose(spec: scenario.ScenarioSpec, ep: dict[str, Any]) -> str:
    """Attribute a non-verified outcome to a cause, with the evidence to support it."""
    if ep["verified"]:
        return "OBJECTIVE_VERIFIED"
    feas = scenario.feasibility(spec)
    cls, reason = feas["feasibility"], feas["reason"]
    if cls == "INVALID":
        return "UNKNOWN"
    if cls == "VALID_BLOCKED":
        return "ENVIRONMENT_BLOCKED" if "access-controlled" in reason else "BUDGET_EXHAUSTED"
    if ep["blocked_by_blue"]:
        return "BLUE_BLOCKED"

    paths = scenario.exfil_candidate_paths(spec)
    has_open = any((not p["blocked"]) and (not p["gated"]) for p in paths)
    has_gated = any((not p["blocked"]) and p["gated"] for p in paths)
    budget, w = ep["budget"], ep["optimal_witness_length"]

    if not has_open and has_gated:
        # The only route needs a prerequisite that no observation can identify.
        if w is not None and budget < w:
            return "BUDGET_EXHAUSTED"  # even a clairvoyant cannot fit
        if ep["explored_public"] and w is not None and budget >= w + _AMPLE_SEARCH_SLACK:
            return "EXPLORATION_FAILURE"  # ample room to search, still failed -> policy
        return "INFORMATION_LIMITATION"  # feasible for a clairvoyant, hidden from an agent

    if has_open:
        if not ep["attempted_foreign"]:
            return "EXPLORATION_FAILURE"  # never even tried a real target (e.g. public-only)
        if ep["actions"] >= budget:
            return "BUDGET_EXHAUSTED"  # tried targets but ran the budget out
        return "PLANNING_FAILURE"  # tried targets, stopped early with budget to spare
    return "UNKNOWN"


def compare_policies(
    spec: scenario.ScenarioSpec,
    root: Any,
    *,
    seeds: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8),
    policies: tuple[str, ...] = POLICY_NAMES,
) -> dict[str, Any]:
    """Run every policy over several seeds (document-identity permutations); aggregate."""
    base = Path(root)
    rows: dict[str, list[dict[str, Any]]] = {p: [] for p in policies}
    for policy in policies:
        for seed in seeds:
            variant = spec.model_copy(
                update={"seed": seed, "id": f"{spec.family}/{spec.split}/{seed}"}
            )
            rows[policy].append(evaluate_episode(variant, policy, base / f"{policy}-{seed}"))
    return {
        "scenario_family": spec.family,
        "budget": spec.red_action_budget,
        "optimal_witness_length": optimal_witness_length(spec),
        "seeds": list(seeds),
        "policies": {p: _aggregate(rows[p]) for p in policies},
    }


def _aggregate(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(episodes)
    verified = sum(e["verified"] for e in episodes)
    steps = [e["steps_to_objective"] for e in episodes if e["verified"] and e["steps_to_objective"]]
    over = [e["actions_over_optimal"] for e in episodes if e["actions_over_optimal"] is not None]
    diag: dict[str, int] = {}
    for e in episodes:
        diag[e["diagnosis"]] = diag.get(e["diagnosis"], 0) + 1
    return {
        "n": n,
        "verified": verified,
        "verified_rate": round(verified / n, 4) if n else None,
        "verified_rate_ci95": wilson(verified, n),
        "mean_steps_when_verified": round(sum(steps) / len(steps), 2) if steps else None,
        "mean_actions_over_optimal": round(sum(over) / len(over), 2) if over else None,
        "mean_rejected": round(sum(e["rejected_actions"] for e in episodes) / n, 2) if n else None,
        "mean_repeated": round(sum(e["repeated_actions"] for e in episodes) / n, 2) if n else None,
        "diagnoses": diag,
    }


def budget_sweep(
    spec: scenario.ScenarioSpec,
    root: Any,
    *,
    budgets: tuple[int, ...] = (6, 8, 10, 12, 15),
    seeds: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8),
    policies: tuple[str, ...] = ("adaptive", "online"),
) -> list[dict[str, Any]]:
    """Sweep the SAME configuration across budgets; report completion and overhead."""
    base = Path(root)
    out = []
    for budget in budgets:
        variant = with_budget(spec, budget)
        row: dict[str, Any] = {
            "budget": budget,
            "optimal_witness_length": optimal_witness_length(variant),
            "feasibility": scenario.feasibility(variant)["feasibility"],
            "policies": {},
        }
        for policy in policies:
            eps = [
                evaluate_episode(
                    variant.model_copy(update={"seed": s, "id": f"{spec.family}/{spec.split}/{s}"}),
                    policy,
                    base / f"b{budget}-{policy}-{s}",
                )
                for s in seeds
            ]
            agg = _aggregate(eps)
            row["policies"][policy] = {
                "verified": agg["verified"],
                "n": agg["n"],
                "verified_rate": agg["verified_rate"],
                "verified_rate_ci95": agg["verified_rate_ci95"],
                "mean_steps_when_verified": agg["mean_steps_when_verified"],
                "diagnoses": agg["diagnoses"],
            }
        out.append(row)
    return out
