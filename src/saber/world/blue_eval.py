"""Closed-loop Red vs active-Blue evaluation with a benign client workload (Phase 4.1D-1).

The Runner already couples Red, Blue and Client through the real `World.act()` event loop:
Blue observes Red's server telemetry, opens cases, and applies verified controls (contain /
patch / quarantine / restore) that change the state Red observes on its next turn. This module
does NOT add a simulator or a stronger defender -- it runs the EXISTING components in paired
conditions (no Blue vs the existing reactive Blue), extracts Red / Blue / Client / validity
metrics that already exist in `report()`, `red_metrics` and `mission`, and reconstructs an
intervention-attribution timeline from the sealed event/case store.

Separation of duties is preserved: Red never receives Blue's private decisions or evaluator
truth, Blue never receives Red's hidden plans or scenario labels. Attribution uses evaluator
evidence (a case-bound verified containment, an incident's detected tick), never a Red 403, and
never un-verifies an objective a Red actor already completed. DEV_SIMULATION_ONLY; nothing here
promotes any subtask to READY_BENCHMARK.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from saber.world import red_eval, scenario
from saber.world.mission import wilson
from saber.world.store import Store

BLUE_MODES = ("absent", "reactive")


def with_blue(spec: scenario.ScenarioSpec, mode: str) -> Any:
    """The SAME scenario under a different Blue mode (paired condition). Nothing else changes."""
    return spec.model_copy(update={"blue_mode": mode})


def _red_principals(spec: scenario.ScenarioSpec) -> dict[str, str]:
    config = scenario.build_config(spec)
    seed = spec.seed
    import hashlib

    return {
        a.id: "acct-" + hashlib.sha256(f"{seed}/{a.id}".encode()).hexdigest()[:12]
        for a in config.actors
        if a.team == "red"
    }


def run_episode(spec: scenario.ScenarioSpec, red_policy: str, root: Any) -> dict[str, Any]:
    """Run one closed-loop episode (client+red+blue) and extract all four metric blocks."""
    from saber.world.red_policies import POLICIES
    from saber.world.runtime import Runner

    config = scenario.build_config(spec)
    store = Store(Path(root))
    try:
        scenario.materialize(store, spec)
        runner = Runner(store, config, red_policy=POLICIES[red_policy])
        report = runner.run(ticks=spec.tick_budget)
    finally:
        store.close()

    red = report["red_objectives"]
    mission = report["mission"]
    metrics = report["metrics"]
    # Re-shape into the run_scenario summary so the Red evaluator can classify without re-running.
    res = {
        "scenario": spec.id,
        "family": spec.family,
        "policy": red_policy,
        "feasibility": scenario.feasibility(spec)["feasibility"],
        "verified": red["red_objectives_verified"],
        "total": red["red_objectives_total"],
        "blocked_by_blue": red["red_objectives_blocked_by_blue"],
        "blocked_by_environment": red["red_objectives_blocked_by_environment"],
        "rejected_actions": red["red_actions_rejected"],
        "steps_to_objective": red["red_steps_to_objective"],
        "client_mission_utility": mission["work_availability"],
        "objectives": red["objectives"],
    }
    ep = red_eval.episode_metrics(spec, red_policy, root, res)
    interventions = _interventions(spec, root)
    return {
        "scenario": spec.id,
        "family": spec.family,
        "blue_mode": spec.blue_mode,
        "observability": spec.observability,
        "policy": red_policy,
        "red": _red_block(ep, red, interventions),
        "blue": _blue_block(red, mission, metrics),
        "client": _client_block(mission, metrics),
        "interventions": interventions,
        "validity": _validity_block(red, interventions),
    }


# --- Red / Blue / Client / validity metric blocks -----------------------------


def _red_block(
    ep: dict[str, Any], red: dict[str, Any], interventions: list[dict[str, Any]]
) -> dict[str, Any]:
    # Recovery after intervention: the objective was verified despite having hit >=1 denial
    # (a control the actor had to work around), i.e. it adapted rather than walking a clear path.
    recovered = bool(ep["verified"] and ep["foreign_denials"] > 0)
    return {
        "verified": ep["verified"],
        "feasible": ep["feasible"],
        "diagnosis": ep["diagnosis"],
        "actions": ep["actions"],
        "steps_to_objective": ep["steps_to_objective"],
        "rejected_actions": ep["rejected_actions"],
        "repeated_actions": ep["repeated_actions"],
        "foreign_denials": ep["foreign_denials"],
        "blocked_by_blue": ep["blocked_by_blue"],
        "blocked_by_environment": ep["blocked_by_environment"],
        "budget_exhausted": ep["diagnosis"] == "BUDGET_EXHAUSTED",
        "recovered_after_intervention": recovered,
        "optimal_witness_length": ep["optimal_witness_length"],
    }


def _blue_block(
    red: dict[str, Any], mission: dict[str, Any], metrics: dict[str, Any]
) -> dict[str, Any]:
    verified_incidents = int(metrics.get("verified_incidents", 0))
    detected = int(metrics.get("detected_incidents", 0))
    return {
        "verified_incidents": verified_incidents,
        "detected_incidents": detected,
        "missed_incidents": verified_incidents - detected,
        "detection_rate": mission["incident_recall"],
        "case_precision": mission["case_precision"],
        "containments": int(metrics.get("containments", 0)),
        "false_containments": int(metrics.get("false_containments", 0)),
        "false_containment_rate": mission["false_containment_rate"],
        "detection_before_objective": red["blue_detection_before_objective"],
        "containment_before_objective": red["blue_containment_before_objective"],
        "mean_detection_ticks": metrics.get("detection_delay_ticks_sum", 0) / detected
        if detected
        else None,
    }


def _client_block(mission: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    requests = int(metrics.get("client_requests", 0))
    failures = int(metrics.get("client_failures", 0))
    return {
        "client_requests": requests,
        "tasks_completed": requests - failures,
        "denied_by_containment": int(metrics.get("client_denied_containment", 0)),
        "denied_by_outage": int(metrics.get("client_denied_outage", 0)),
        "collateral_disruption": int(metrics.get("client_denied_collateral", 0)),
        "work_availability": mission["work_availability"],
        "mission_score": mission["mission_score"],
    }


def _validity_block(red: dict[str, Any], interventions: list[dict[str, Any]]) -> dict[str, Any]:
    # Attribution coverage: of the scored objectives that were NOT verified, how many have a
    # supported cause (a case-bound Blue block, an enforced environment control, or budget)?
    failures = [o for o in red["objectives"] if not o["effect_verified"] and o["attempted"]]
    supported = [
        o
        for o in failures
        if o["blocked_by_blue"] or o["blocked_by_environment"] or o["budget_exhausted"]
    ]
    unknown = len(failures) - len(supported)
    return {
        "attempted_failures": len(failures),
        "attribution_supported": len(supported),
        "unknown_attribution": unknown,
        "attribution_coverage": round(len(supported) / len(failures), 4) if failures else None,
        "interventions_total": len(interventions),
        "interventions_unknown": sum(1 for i in interventions if i["attribution"] == "UNKNOWN"),
    }


# --- Intervention attribution timeline (from the sealed store) -----------------


def _interventions(spec: scenario.ScenarioSpec, root: Any) -> list[dict[str, Any]]:
    """Reconstruct each verified Blue intervention with evidence-based attribution."""
    store = Store(Path(root))
    try:
        cases = store.items("cases")
        redobj = store.items("red-objectives")
        red_principals = set(_red_principals(spec).values())
        out: list[dict[str, Any]] = []
        for case in cases.values():
            offenders = store.get("case-evaluation", case["id"], {}).get("offenders", [])
            evidence = case.get("evidence", [])
            for r in case.get("responses", []):
                if r["tool"] not in ("contain", "quarantine", "restore") or not r["verified"]:
                    continue
                affected = str(r["target"])
                control_tick = int(r["tick"])
                # Event tick: the earliest case evidence tick for the affected principal/asset.
                relevant = [
                    e
                    for e in evidence
                    if e.get("principal") == affected or str(e.get("target")) == affected
                ]
                event_tick = min((int(e["tick"]) for e in relevant), default=None)
                obj = redobj.get(affected, {})
                verified_tick = obj.get("verified_tick")
                before, after = _red_action_split(store, affected, control_tick)
                is_red = affected in red_principals
                is_offender = affected in offenders
                if r["tool"] == "contain" and not is_offender:
                    attribution = "FALSE_CONTAINMENT"
                elif event_tick is None:
                    attribution = "UNKNOWN"
                else:
                    attribution = "SUPPORTED"
                out.append(
                    {
                        "case_id": case["id"],
                        "blue_principal": r.get("by"),
                        "control": r["tool"],
                        "affected_principal": affected,
                        "affected_is_red": is_red,
                        "event_tick": event_tick,
                        "observation_tick": control_tick,  # Blue acted on the turn it applied the control
                        "control_tick": control_tick,
                        "red_actions_before": before,
                        "red_actions_after": after,
                        "objective_verified_tick": verified_tick,
                        "objective_verified_before_control": (
                            verified_tick is not None and verified_tick <= control_tick
                        ),
                        "attribution": attribution,
                    }
                )
        return sorted(out, key=lambda i: (i["control_tick"], i["case_id"]))
    finally:
        store.close()


def _red_action_split(store: Store, principal: str, tick: int) -> tuple[int, int]:
    evs = store.events(through_tick=10**9, limit=100000, principal=principal)
    before = sum(1 for e in evs if int(e["tick"]) < tick)
    return before, len(evs) - before


# --- Paired no-Blue vs reactive-Blue study ------------------------------------


def _rate(values: list[bool]) -> dict[str, Any]:
    n = len(values)
    k = sum(values)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _aggregate(eps: list[dict[str, Any]]) -> dict[str, Any]:
    feasible = [e for e in eps if e["red"]["feasible"]]
    diag: dict[str, int] = {}
    for e in eps:
        d = e["red"]["diagnosis"]
        diag[d] = diag.get(d, 0) + 1
    return {
        "n": len(eps),
        "red_verified": _rate([e["red"]["verified"] for e in eps]),
        "red_verified_given_feasible": _rate([e["red"]["verified"] for e in feasible]),
        "red_recovered_after_intervention": sum(
            e["red"]["recovered_after_intervention"] for e in eps
        ),
        "red_mean_actions": _mean([e["red"]["actions"] for e in eps]),
        "red_blocked_by_blue": sum(e["red"]["blocked_by_blue"] for e in eps),
        "red_diagnoses": diag,
        "blue_detection_rate": _rate(
            [bool(e["blue"]["detected_incidents"]) for e in eps if e["blue"]["verified_incidents"]]
        ),
        "blue_verified_containments": sum(e["blue"]["containments"] for e in eps),
        "blue_false_containments": sum(e["blue"]["false_containments"] for e in eps),
        "blue_missed_incidents": sum(e["blue"]["missed_incidents"] for e in eps),
        "blue_mean_detection_ticks": _mean([e["blue"]["mean_detection_ticks"] for e in eps]),
        "client_mean_tasks_completed": _mean([e["client"]["tasks_completed"] for e in eps]),
        "client_collateral": sum(e["client"]["collateral_disruption"] for e in eps),
        "client_mean_mission_score": _mean([e["client"]["mission_score"] for e in eps]),
        "mean_attribution_coverage": _mean([e["validity"]["attribution_coverage"] for e in eps]),
        "unknown_attributions": sum(e["validity"]["unknown_attribution"] for e in eps),
    }


def paired_study(
    spec: scenario.ScenarioSpec,
    root: Any,
    *,
    red_policy: str = "adaptive",
    seeds: tuple[int, ...] = tuple(range(1, 33)),
) -> dict[str, Any]:
    """Run the SAME scenario/seed/budget under no-Blue and reactive-Blue; aggregate both."""
    base = Path(root)
    conditions: dict[str, list[dict[str, Any]]] = {m: [] for m in BLUE_MODES}
    for mode in BLUE_MODES:
        for seed in seeds:
            variant = with_blue(
                spec.model_copy(update={"seed": seed, "id": f"{spec.family}/{spec.split}/{seed}"}),
                mode,
            )
            conditions[mode].append(run_episode(variant, red_policy, base / f"{mode}-{seed}"))
    return {
        "scenario_family": spec.family,
        "red_policy": red_policy,
        "observability": spec.observability,
        "budget": spec.red_action_budget,
        "seeds": list(seeds),
        "structural_feasibility": scenario.feasibility(spec)["feasibility"],
        "conditions": {m: _aggregate(conditions[m]) for m in BLUE_MODES},
    }
