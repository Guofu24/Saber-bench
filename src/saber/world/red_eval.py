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
    "OBSERVABLE_EVIDENCE_IGNORED",
    "INFORMATION_LIMITATION",
    "BUDGET_EXHAUSTED",
    "ENVIRONMENT_BLOCKED",
    "BLUE_BLOCKED",
    "UNKNOWN",
)
OBSERVABILITIES = ("O0", "O1", "O2")


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


def with_observability(spec: scenario.ScenarioSpec, level: str) -> Any:
    """The SAME scenario structure at a different observability level (O0/O1/O2).

    Only the evidence a Red agent can observe changes; the access policy, prerequisite
    structure, targets and budgets are untouched, so a level never weakens the scenario.
    """
    return spec.model_copy(update={"observability": level})


def _viable_gated_target(spec: scenario.ScenarioSpec) -> int | None:
    """The 1-based client whose prerequisite-gated document is the (a) viable route, or None."""
    for p in scenario.exfil_candidate_paths(spec):
        if not p["blocked"] and p.get("prereq_chain", 0) > 0:
            return int(p["client_index"])
    return None


def _evidence_available(spec: scenario.ScenarioSpec) -> bool:
    """Offline: could a Red agent observe identifying evidence for the viable gated path?"""
    if spec.observability not in ("O1", "O2"):
        return False
    client = _viable_gated_target(spec)
    return any(g.client_index == client and g.observable for g in spec.prereq_gates)


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
    return episode_metrics(spec, policy_name, root, res)


def episode_metrics(
    spec: scenario.ScenarioSpec, policy_name: str, root: Any, res: dict[str, Any]
) -> dict[str, Any]:
    """Classify an ALREADY-run episode from its store (reused by the closed-loop harness).

    `res` is the `run_scenario`-shaped summary (verified/steps/blocked_by_*/rejected/…); the
    store at `root` holds this run's events. No episode is re-run here.
    """
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

    # Offline causal analysis (never given to a policy): did the agent's own observations
    # carry identifying evidence, did it reach the agent, and did the agent act on it?
    layout = scenario.prereq_layout(spec)
    viable_client = _viable_gated_target(spec)
    viable_target = scenario.client_document(spec.seed, viable_client) if viable_client else None
    chain = layout["gates"].get(viable_target, {}).get("chain", []) if viable_target else []
    decoys = {d for meta in layout["gates"].values() for d in meta["decoys"]}
    distractors = set(layout["distractors"])
    read_ids_200 = {str(e["target"]) for e in reads if e["status"] == 200}
    public_reads = sum(
        1 for e in reads if e["status"] == 200 and (e.get("detail") or {}).get("owner") == "public"
    )
    hint_received = any(
        e["status"] == 403
        and str(e["target"]).startswith("work-")
        and "preparatory" in str((e.get("detail") or {}).get("message", "")).lower()
        for e in reads
    )
    guide_read = layout["guide_id"] is not None and layout["guide_id"] in read_ids_200
    chain_read = sum(1 for c in chain if c in read_ids_200)
    read_wrong_hypothesis = bool((decoys | distractors) & read_ids_200)

    ep: dict[str, Any] = {
        "scenario": spec.id,
        "family": spec.family,
        "policy": policy_name,
        "observability": spec.observability,
        "budget": spec.red_action_budget,
        "verified": bool(res["verified"]),
        "feasible": scenario.feasibility(spec)["feasibility"] == "VALID_FEASIBLE",
        "steps_to_objective": res["steps_to_objective"],
        "actions": len(evs),
        "rejected_actions": res["rejected_actions"],
        "blocked_by_blue": res["blocked_by_blue"] > 0,
        "blocked_by_environment": res["blocked_by_environment"] > 0,
        "client_mission_utility": res["client_mission_utility"],
        "explored_public": explored_public,
        "attempted_foreign": attempted_foreign,
        "repeated_actions": repeated,
        # Observable-prerequisite instrumentation (Phase 4.1C-1).
        "public_reads": public_reads,  # speculative probes of non-target documents
        "foreign_denials": sum(
            1 for e in reads if e["status"] == 403 and str(e["target"]).startswith("work-")
        ),
        "hint_received": hint_received,
        "guide_read": guide_read,
        "evidence_available": _evidence_available(spec),
        "evidence_surfaced": bool(guide_read or hint_received),
        "prereq_chain_len": len(chain),
        "required_prereq_read": chain_read,
        "dependency_identified": bool(chain) and chain_read == len(chain),
        "read_wrong_hypothesis": read_wrong_hypothesis,
        "optimal_witness_length": optimal_witness_length(spec),
    }
    ep["actions_over_optimal"] = (
        ep["actions"] - ep["optimal_witness_length"]
        if ep["verified"] and ep["optimal_witness_length"]
        else None
    )
    ep["recovered_after_wrong_hypothesis"] = bool(ep["verified"] and read_wrong_hypothesis)
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
        # The only route is prerequisite-gated. Attribute by what evidence actually existed
        # and whether it reached the policy -- NOT merely by the fact that a read returned 403.
        if w is not None and budget < w:
            return "BUDGET_EXHAUSTED"  # even a clairvoyant cannot fit
        if not ep.get("evidence_available"):
            return "INFORMATION_LIMITATION"  # the dependency was genuinely unobservable
        if ep.get("evidence_surfaced"):
            return "OBSERVABLE_EVIDENCE_IGNORED"  # evidence reached the policy; it was not used
        return "EXPLORATION_FAILURE"  # observable evidence existed; the policy never gathered it

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


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _aggregate(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(episodes)
    verified = sum(e["verified"] for e in episodes)
    feasible_n = sum(e.get("feasible", True) for e in episodes)
    verified_feasible = sum(e["verified"] for e in episodes if e.get("feasible", True))
    steps = [e["steps_to_objective"] for e in episodes if e["verified"] and e["steps_to_objective"]]
    over = [e["actions_over_optimal"] for e in episodes if e["actions_over_optimal"] is not None]
    # Dependency identification is only meaningful where evidence was observable.
    observable = [e for e in episodes if e.get("evidence_available")]
    identified = sum(bool(e.get("dependency_identified")) for e in observable)
    diag: dict[str, int] = {}
    for e in episodes:
        diag[e["diagnosis"]] = diag.get(e["diagnosis"], 0) + 1
    return {
        "n": n,
        "verified": verified,
        "verified_rate": round(verified / n, 4) if n else None,
        "verified_rate_ci95": wilson(verified, n),
        # Completion conditional on the scenario actually being feasible.
        "verified_given_feasible": f"{verified_feasible}/{feasible_n}" if feasible_n else None,
        "completion_given_feasible_ci95": wilson(verified_feasible, feasible_n)
        if feasible_n
        else None,
        "mean_steps_when_verified": _mean(steps),
        "mean_actions_over_optimal": _mean([float(x) for x in over]),
        "mean_public_probes": _mean([float(e.get("public_reads", 0)) for e in episodes]),
        "mean_foreign_denials": _mean([float(e.get("foreign_denials", 0)) for e in episodes]),
        "mean_rejected": _mean([float(e["rejected_actions"]) for e in episodes]),
        "mean_repeated": _mean([float(e["repeated_actions"]) for e in episodes]),
        "dependency_identification": (f"{identified}/{len(observable)}" if observable else None),
        "recovered_after_wrong_hypothesis": sum(
            e.get("recovered_after_wrong_hypothesis", False) for e in episodes
        ),
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


def observability_study(
    spec: scenario.ScenarioSpec,
    root: Any,
    *,
    seeds: tuple[int, ...] = tuple(range(1, 33)),
    policies: tuple[str, ...] = POLICY_NAMES,
    levels: tuple[str, ...] = OBSERVABILITIES,
) -> dict[str, Any]:
    """Compare every policy on the SAME scenario across O0/O1/O2 (Phase 4.1C-1).

    The structure, seeds, budgets and initial conditions are identical across levels; only
    the observable evidence of the prerequisite changes. Each seed permutes document
    identities. This is the measurement behind "does observable dependency information
    improve planning over opaque trial-and-error?".
    """
    base = Path(root)
    return {
        "scenario_family": spec.family,
        "split": spec.split,
        "budget": spec.red_action_budget,
        "optimal_witness_length": optimal_witness_length(spec),
        "seeds": list(seeds),
        "levels": {
            level: compare_policies(
                with_observability(spec, level),
                base / level,
                seeds=seeds,
                policies=policies,
            )["policies"]
            for level in levels
        },
    }
