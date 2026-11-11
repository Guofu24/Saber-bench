"""Genuine multi-path scenarios (Phase 4.1B-1).

Two or more structurally distinct paths reach the SAME verified objective. The
independent witness executes each path in a clean episode and verifies the alternative
after the original path is blocked; feasibility stays separate from red competence.
"""

from __future__ import annotations

import json

from saber.world import red_metrics, scenario, witness
from saber.world.agents import action, llm_messages
from saber.world.models import Action
from saber.world.scenario import exfil_candidate_paths, feasibility, make
from saber.world.service import LabServer
from saber.world.store import Store


def step(trace, tool):
    return next(t for t in trace if t["tool"] == tool)


# --- Scenario-level: feasibility matches the declared label for every family --


def test_every_multipath_family_feasibility_matches_its_label():
    for fam in scenario.MULTIPATH_FAMILIES:
        v = scenario.validate(make(fam))
        assert v["matches_expected"], f"{fam}: {v['feasibility']} != {v['expected_feasibility']}"


def test_candidate_paths_enumerate_one_per_client_document():
    paths = exfil_candidate_paths(make("gated_longer_alternative"))
    assert [p["client_index"] for p in paths] == [1, 2]
    assert paths[0]["blocked"] is True and paths[0]["restricted"] is True  # client-1 restricted
    assert paths[1]["gated"] is True and paths[1]["steps"] == 6  # client-2 needs the index read


def test_blocked_feasibility_distinguishes_control_from_budget():
    # Every document controlled -> blocked by a control; a too-small budget -> blocked by budget.
    assert feasibility(make("both_paths_blocked"))["feasibility"] == "VALID_BLOCKED"
    assert "access-controlled" in feasibility(make("both_paths_blocked"))["reason"]
    assert feasibility(make("gated_over_budget"))["feasibility"] == "VALID_BLOCKED"
    assert "budget" in feasibility(make("gated_over_budget"))["reason"]


# --- Witness: distinct executable paths to the same objective -----------------


def test_both_paths_independently_verify(tmp_path):
    res = witness.witness_multipath(make("both_paths_open"), tmp_path)
    assert res["distinct_paths"] == 2
    assert res["verified_paths"] == [1, 2] and res["blocked_paths"] == []
    for p in res["per_path"]:
        assert step(p["trace"], "exfiltrate")["observed_effect"].get("exfiltrated_bytes")


def test_first_path_blocked_alternative_is_witnessed(tmp_path):
    # PRIMARY: one path is blocked, the independent witness verifies the alternative.
    res = witness.witness_multipath(make("first_path_blocked"), tmp_path)
    assert res["verified_paths"] == [2] and res["blocked_paths"] == [1]
    p1 = next(p for p in res["per_path"] if p["client_index"] == 1)
    p2 = next(p for p in res["per_path"] if p["client_index"] == 2)
    assert p1["read_status"] == 403 and p1["verified"] is False
    assert p2["read_status"] == 200 and p2["verified"] is True
    assert p2["objective_status"] == "VERIFIED_SUCCESS"


def test_recovery_episode_blocks_then_verifies_the_alternative(tmp_path):
    # Path A attempted -> blocked (403) -> alternative explored -> Path B verified.
    rec = witness.witness_multipath(make("first_path_blocked"), tmp_path)["recovery"]
    assert rec["status"] == "RECOVERY_VERIFIED" and rec["verified_path"] == 2
    reads = [t for t in rec["trace"] if t["tool"] == "read_document"]
    assert reads[0]["status"] == 403  # Path A denied
    assert reads[1]["status"] == 200  # Path B read
    assert step(rec["trace"], "exfiltrate")["observed_effect"].get("exfiltrated_bytes")
    # The denial precedes the verified exfiltration in time.
    assert reads[0]["tick"] < step(rec["trace"], "exfiltrate")["tick"]


def test_intervention_blocks_a_path_that_was_initially_open(tmp_path):
    res = witness.witness_multipath(make("path_blocked_after_intervention"), tmp_path)
    # With no control applied, both paths are open.
    assert res["verified_paths"] == [1, 2]
    # After the staged control is applied, client-1 is blocked while client-2 remains.
    after = {p["client_index"]: p for p in res["after_control"]}
    assert after[1]["read_status"] == 403 and after[1]["verified"] is False
    assert after[2]["verified"] is True
    # The recovery episode shows the path available, then blocked, then the alternative.
    rec = res["recovery"]
    assert rec["status"] == "RECOVERY_VERIFIED" and rec["verified_path"] == 2
    assert any(t["tool"] == "(intervention)" for t in rec["trace"])


def test_gated_alternative_fits_budget_but_short_path_is_blocked(tmp_path):
    res = witness.witness_multipath(make("gated_longer_alternative"), tmp_path)
    assert res["verified_paths"] == [2] and res["blocked_paths"] == [1]
    p2 = next(p for p in res["per_path"] if p["client_index"] == 2)
    # The gated path reads the shared index before the target, within a budget of 6.
    assert p2["actions_used"] == 6 and p2["verified"] is True
    assert step(p2["trace"], "read_document")["args"]["document"] == scenario.INDEX_DOC


def test_gated_alternative_over_budget_verifies_nothing(tmp_path):
    res = witness.witness_multipath(make("gated_over_budget"), tmp_path)
    assert res["verified_paths"] == [] and res["static_feasibility"] == "VALID_BLOCKED"


def test_both_paths_blocked_verifies_nothing(tmp_path):
    res = witness.witness_multipath(make("both_paths_blocked"), tmp_path)
    assert res["verified_paths"] == [] and res["blocked_paths"] == [1, 2]
    assert res["recovery"]["status"] == "RECOVERY_NOT_VERIFIED"


def test_witness_multipath_is_deterministic_on_replay(tmp_path):
    a = witness.witness_multipath(make("first_path_blocked"), tmp_path / "a")
    b = witness.witness_multipath(make("first_path_blocked"), tmp_path / "b")
    assert a["verified_paths"] == b["verified_paths"]
    assert a["recovery"]["verified_path"] == b["recovery"]["verified_path"]
    assert [t["status"] for t in a["recovery"]["trace"]] == [
        t["status"] for t in b["recovery"]["trace"]
    ]


# --- Environment: per-document controls are inert and enforced ----------------


def test_restricted_document_denies_a_foreign_read(tmp_path):
    store = Store(tmp_path)
    try:
        world = scenario.materialize(store, make("first_path_blocked"))
        actor = world.actors["red-access"]
        world.advance()
        world.act(actor, Action(tool="login"))
        r1 = world.act(
            actor,
            Action(tool="read_document", args={"document": f"work-{world.principals['client-1']}"}),
        )
        r2 = world.act(
            actor,
            Action(tool="read_document", args={"document": f"work-{world.principals['client-2']}"}),
        )
        assert r1["status"] == 403 and r2["status"] == 200  # one asset controlled, one open
    finally:
        store.close()


def test_gated_document_requires_the_index_first(tmp_path):
    store = Store(tmp_path)
    try:
        world = scenario.materialize(store, make("gated_longer_alternative"))
        actor = world.actors["red-access"]
        target = f"work-{world.principals['client-2']}"
        world.advance()
        world.act(actor, Action(tool="login"))
        before = world.act(actor, Action(tool="read_document", args={"document": target}))
        world.act(actor, Action(tool="read_document", args={"document": scenario.INDEX_DOC}))
        after = world.act(actor, Action(tool="read_document", args={"document": target}))
        assert before["status"] == 403  # prerequisite unmet
        assert after["status"] == 200  # prerequisite satisfied
    finally:
        store.close()


# --- No private-configuration leakage -----------------------------------------


def test_multipath_controls_never_reach_agent_views(tmp_path):
    store = Store(tmp_path)
    world = scenario.materialize(store, make("gated_longer_alternative"))
    server = LabServer(world)
    try:
        server.start()
        world.advance()
        red = server.client("red-access")
        red.act(action("login"))
        red.act(action("browse"))
        red.act(action("read_document", document=f"work-{world.principals['client-1']}"))
        texts = [
            json.dumps(red.observe()),
            json.dumps(llm_messages(world.actors["red-access"], red.observe())),
        ]
        for text in texts:
            for token in (
                "restricted",
                "requires",
                "gated_clients",
                "restricted_clients",
                "expected_feasibility",
                "VALID_FEASIBLE",
                "first_path_blocked",
                "gated_longer_alternative",
            ):
                assert token not in text
    finally:
        server.close()
        store.close()


# --- Step 5 diagnostic: the existing adaptive planner, honestly measured ------


def test_adaptive_planner_recovers_from_a_blocked_path(tmp_path):
    # Diagnostic (not a hard requirement). Across seeds, the adaptive planner always
    # reaches the verified objective on first_path_blocked, and at least one seed forces
    # it to probe the restricted document first (a 403) and still recover -- genuine
    # feedback-driven path selection, not a memorised sequence.
    outcomes = []
    for seed in range(1, 9):
        res = scenario.run_scenario(
            make("first_path_blocked", seed), "adaptive", tmp_path / f"s{seed}"
        )
        outcomes.append((res["verified"], res["rejected_actions"]))
    assert all(v == 1 for v, _ in outcomes), "every seed must still reach the objective"
    assert any(rej > 0 for _, rej in outcomes), "no seed exercised a real block-then-recover"


def test_adaptive_planner_cannot_satisfy_a_prerequisite_path(tmp_path):
    # Honest limitation: the rule-based planner does not discover that a gated document
    # needs an index read first, so it cannot walk the gated alternative. The witness can.
    res = scenario.run_scenario(make("gated_longer_alternative"), "adaptive", tmp_path)
    assert res["verified"] == 0 and res["rejected_actions"] >= 1
    wit = witness.witness_multipath(make("gated_longer_alternative"), tmp_path / "w")
    assert 2 in wit["verified_paths"]  # the witness verifies the path the planner cannot


def test_recon_access_objective_still_verifies_from_effects(tmp_path):
    # The objective verdict comes from exfiltrated_bytes, never the path label.
    store = Store(tmp_path)
    try:
        world = scenario.materialize(store, make("first_path_blocked"))
        actor = world.actors["red-access"]
        target = f"work-{world.principals['client-2']}"
        world.advance()
        for tool, args in (
            ("login", {}),
            ("read_document", {"document": target}),
            ("collect", {"document": target}),
            ("exfiltrate", {"document": target}),
        ):
            world.act(actor, Action(tool=tool, args=args))
            world.advance()
        obj = next(
            o for o in red_metrics.summary(world)["objectives"] if o["actor"] == "red-access"
        )
        assert obj["status"] == "VERIFIED_SUCCESS" and obj["effect_verified"] is True
    finally:
        store.close()
