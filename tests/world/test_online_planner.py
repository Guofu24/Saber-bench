"""Online-search red policy and controlled evaluation (Phase 4.1B-2).

The online planner adds prerequisite discovery by exploration over the SAME observation
contract as every other policy. These tests check its belief/decision logic in isolation,
its advantage over the rule-based planner on gated paths, budget sensitivity, held-out
generalization, permutation invariance, evaluator independence and diagnostic attribution.
"""

from __future__ import annotations

from saber.world import online_planner, red_eval, scenario
from saber.world.models import Actor
from saber.world.online_planner import observe_belief, plan_online

ACCESS = Actor(id="red-access", team="red", role="access", goal="x")


def obs(**kw):
    base = {
        "principal": "acct-x",
        "logged_in": True,
        "budget": 40,
        "last_result": {},
        "events": [],
    }
    base.update(kw)
    return base


def browse_result(*ids):
    return {"tool": "browse", "status": 200, "links": [{"id": i, "title": i} for i in ids]}


def read_evt(target, status=200, owner="acct-y", tick=1):
    return {
        "tool": "read_document",
        "target": target,
        "status": status,
        "tick": tick,
        "detail": {"owner": owner},
    }


# --- Belief and decision logic (unit) -----------------------------------------


def test_logs_in_first():
    assert plan_online(ACCESS, obs(logged_in=False), 0).tool == "login"


def test_browses_when_no_map_is_known():
    assert plan_online(ACCESS, obs(), 0).tool == "browse"


def test_reads_an_open_target_from_a_fresh_map():
    action = plan_online(ACCESS, obs(last_result=browse_result("work-acct-y", "index-shared")), 1)
    assert action.tool == "read_document" and action.args["document"] == "work-acct-y"


def test_explores_a_public_document_when_every_target_is_denied():
    events = [read_evt("work-acct-y", 403, tick=3), read_evt("work-acct-z", 403, tick=5)]
    o = obs(
        events=events,
        last_result=browse_result("work-acct-y", "work-acct-z", "index-shared", "welcome"),
    )
    action = plan_online(ACCESS, o, 5)
    # It speculatively reads a non-target document (prerequisite hypothesis), lowest id first.
    assert action.tool == "read_document" and action.args["document"] == "index-shared"


def test_retries_a_denied_target_after_a_public_read():
    events = [
        read_evt("work-acct-y", 403, tick=3),
        read_evt("index-shared", 200, owner="public", tick=5),
    ]
    b = observe_belief(obs(events=events))
    assert b.retryable() == ["work-acct-y"]  # denied at 3, a public was read at 5
    action = plan_online(ACCESS, obs(events=events), 6)
    assert action.tool == "read_document" and action.args["document"] == "work-acct-y"


def test_finishes_when_objective_verified():
    events = [{"tool": "exfiltrate", "target": "work-acct-y", "status": 201, "tick": 6}]
    assert plan_online(ACCESS, obs(events=events), 6).tool == "finish"


def test_finishes_on_session_containment():
    denied = {"tool": "read_document", "status": 403, "error": "Session restricted by the service."}
    assert plan_online(ACCESS, obs(last_result=denied), 5).tool == "finish"


def test_will_not_start_a_search_it_cannot_finish():
    # Every target denied, a public candidate exists, but almost no budget remains: stop.
    events = [read_evt("work-acct-y", 403, tick=3)]
    o = obs(budget=5, events=events, last_result=browse_result("work-acct-y", "index-shared"))
    assert plan_online(ACCESS, o, 4).tool == "finish"


# --- Advantage over the rule-based planner ------------------------------------


def test_online_solves_a_gated_path_that_adaptive_cannot(tmp_path):
    spec = red_eval.with_budget(scenario.make("gated_longer_alternative"), 12)
    online = scenario.run_scenario(spec, "online", tmp_path / "o")
    adaptive = scenario.run_scenario(spec, "adaptive", tmp_path / "a")
    assert online["verified"] == 1  # prerequisite discovered by exploration
    assert adaptive["verified"] == 0  # cannot identify the hidden prerequisite


def test_online_matches_adaptive_on_an_open_alternative(tmp_path):
    for fam in ("both_paths_open", "first_path_blocked"):
        res = scenario.run_scenario(scenario.make(fam), "online", tmp_path / fam)
        assert res["verified"] == 1


def test_online_stops_cleanly_when_every_path_is_blocked(tmp_path):
    res = scenario.run_scenario(scenario.make("both_paths_blocked"), "online", tmp_path)
    assert res["verified"] == 0  # environment-blocked by design; the policy gives up


# --- Budget sensitivity (same config, varied budget) --------------------------


def test_budget_sensitivity_of_the_gated_configuration(tmp_path):
    base = scenario.make("gated_longer_alternative")
    low = scenario.run_scenario(red_eval.with_budget(base, 6), "online", tmp_path / "low")
    high = scenario.run_scenario(red_eval.with_budget(base, 12), "online", tmp_path / "high")
    assert low["verified"] == 0  # no room to search for the prerequisite
    assert high["verified"] == 1  # enough budget for exploration + the path


def test_online_does_not_depend_on_document_names(tmp_path):
    # Permutation test: seeds permute the principal-derived document ids.
    results = [
        scenario.run_scenario(scenario.make("first_path_blocked", s), "online", tmp_path / f"s{s}")[
            "verified"
        ]
        for s in range(1, 9)
    ]
    assert results == [1] * 8  # name-independent recovery


# --- Held-out generalization --------------------------------------------------


def test_online_generalizes_to_held_out_structures(tmp_path):
    res = red_eval.compare_policies(
        scenario.make("heldout_multi_restricted_gated"),
        tmp_path,
        seeds=(1, 2, 3, 4),
        policies=("adaptive", "online"),
    )
    assert res["policies"]["online"]["verified"] == 4  # discovers the gated path among decoys
    assert res["policies"]["adaptive"]["verified"] == 0


# --- Evaluator independence (no leakage) --------------------------------------


def test_online_planner_imports_no_evaluator_modules():
    # The policy must not reach the solver, witness, scenario private fields or metrics.
    for forbidden in ("scenario", "witness", "feasibility", "red_metrics", "red_eval"):
        assert not hasattr(online_planner, forbidden)


# --- Diagnostic attribution ---------------------------------------------------


def test_diagnosis_attributes_failures_to_the_correct_cause(tmp_path):
    # Gated-only scenario: a non-exploring policy fails on the hidden prerequisite, not
    # on incompetence -> INFORMATION_LIMITATION; the explorer verifies.
    spec = red_eval.with_budget(scenario.make("gated_longer_alternative"), 12)
    adaptive = red_eval.evaluate_episode(spec, "adaptive", tmp_path / "a")
    online = red_eval.evaluate_episode(spec, "online", tmp_path / "o")
    assert adaptive["diagnosis"] == "INFORMATION_LIMITATION"
    assert online["diagnosis"] == "OBJECTIVE_VERIFIED"
    # An all-controlled scenario is environment-blocked, never blamed on the policy.
    blocked = red_eval.evaluate_episode(
        scenario.make("both_paths_blocked"), "online", tmp_path / "b"
    )
    assert blocked["diagnosis"] == "ENVIRONMENT_BLOCKED"


def test_compare_policies_reports_uncertainty_intervals(tmp_path):
    res = red_eval.compare_policies(
        scenario.make("first_path_blocked"), tmp_path, seeds=(1, 2, 3), policies=("online",)
    )
    agg = res["policies"]["online"]
    assert agg["n"] == 3 and agg["verified"] == 3
    assert agg["verified_rate_ci95"] is not None and len(agg["verified_rate_ci95"]) == 2


def test_offline_witness_length_is_a_reference_not_a_policy(tmp_path):
    # The clairvoyant optimum is shorter than any online episode on a gated path.
    spec = red_eval.with_budget(scenario.make("gated_longer_alternative"), 12)
    ep = red_eval.evaluate_episode(spec, "online", tmp_path)
    assert ep["optimal_witness_length"] == 6
    assert ep["actions"] > ep["optimal_witness_length"]  # the online agent pays an exploration cost
