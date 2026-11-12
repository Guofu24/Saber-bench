"""Closed-loop Red vs active-Blue evaluation (Phase 4.1D-1).

The Runner already couples Red, Blue and Client through the real event loop. These tests prove
the loop is genuinely closed (Blue's verified control changes what Red observes next), that a
verified objective is never un-verified by a later containment, that benign client work is not
treated as malicious, that interventions are attributed from evidence, and that paired
no-Blue vs reactive-Blue evaluation separates structural feasibility from reachability.
"""

from __future__ import annotations

import json
from pathlib import Path

from saber.world import blue_eval, red_metrics, scenario, witness
from saber.world.agents import _suspicious
from saber.world.models import Action
from saber.world.scenario import make
from saber.world.store import Store


def _world(tmp_path, family="blue_containment"):
    store = Store(Path(tmp_path))
    world = scenario.materialize(store, make(family))
    world.advance()  # tick 1
    return store, world


def _foreign(world, i=1):
    return f"work-{world.principals[f'client-{i}']}"


# --- The loop is genuinely closed ---------------------------------------------


def test_blue_observes_a_red_event_and_responds_through_the_loop(tmp_path):
    ep = blue_eval.run_episode(
        blue_eval.with_blue(make("blue_containment"), "reactive"), "adaptive", tmp_path
    )
    assert ep["blue"]["containments"] >= 1  # Blue acted on Red telemetry
    assert ep["red"]["diagnosis"] == "BLUE_BLOCKED"  # and it changed the Red outcome
    contains = [
        i for i in ep["interventions"] if i["control"] == "contain" and i["affected_is_red"]
    ]
    assert contains and contains[0]["attribution"] == "SUPPORTED"
    # Response latency through the loop: Blue applied the control after the triggering event.
    assert contains[0]["control_tick"] >= contains[0]["event_tick"]


def test_a_verified_containment_blocks_a_subsequent_red_action(tmp_path):
    # Drive the real blue tools through the loop: Red reads (incident) -> Blue opens a case and
    # contains the Red principal -> Red's NEXT read is denied "restricted". The control changed
    # the state Red observes, which is exactly a closed loop.
    store, world = _world(tmp_path)
    red = world.actors["red-access"]
    rp = world.principals["red-access"]
    world.act(red, Action(tool="login"))
    evt = world.act(red, Action(tool="read_document", args={"document": _foreign(world, 1)}))
    world.advance()
    opened = world.act(
        world.actors["blue-monitor"],
        Action(tool="open_case", args={"evidence_ids": [evt["event_id"]], "summary": "x"}),
    )
    world.advance()
    cont = world.act(
        world.actors["blue-ir"],
        Action(tool="contain", args={"case_id": opened["case_id"], "principal": rp}),
    )
    assert cont.get("verified") is True
    world.advance()
    blocked = world.act(red, Action(tool="read_document", args={"document": _foreign(world, 2)}))
    assert blocked["status"] == 403 and "restricted" in blocked["error"].lower()
    store.close()


def test_containment_after_the_objective_does_not_erase_the_verified_effect(tmp_path):
    # Red verifies exfiltration; a LATER containment must not un-verify the recorded effect.
    store, world = _world(tmp_path)
    red = world.actors["red-access"]
    target = _foreign(world)
    for tool, args in (
        ("login", {}),
        ("read_document", {"document": target}),
        ("collect", {"document": target}),
        ("exfiltrate", {"document": target}),
    ):
        world.act(red, Action(tool=tool, args=args))
        world.advance()
    obj = next(o for o in red_metrics.summary(world)["objectives"] if o["actor"] == "red-access")
    assert obj["status"] == "VERIFIED_SUCCESS"
    verified_tick = obj["verified_tick"]
    # Apply a containment strictly after verification.
    principal = world.principals["red-access"]
    with store.transaction():
        store.put("blocks", principal, {"until": 10**9, "case_id": "late"})
    after = next(o for o in red_metrics.summary(world)["objectives"] if o["actor"] == "red-access")
    assert after["status"] == "VERIFIED_SUCCESS" and after["verified_tick"] == verified_tick
    store.close()


def test_red_uses_another_permitted_path_after_a_local_denial(tmp_path):
    # A per-document denial (not a full containment) leaves an alternative; Red takes it.
    store, world = _world(tmp_path, "first_path_blocked")
    red = world.actors["red-access"]
    blocked, open_target = _foreign(world, 1), _foreign(world, 2)
    world.act(red, Action(tool="login"))
    denied = world.act(red, Action(tool="read_document", args={"document": blocked}))
    assert denied["status"] == 403  # Path A is access-controlled
    for tool, args in (
        ("read_document", {"document": open_target}),
        ("collect", {"document": open_target}),
        ("exfiltrate", {"document": open_target}),
    ):
        world.advance()
        world.act(red, Action(tool=tool, args=args))
    obj = next(o for o in red_metrics.summary(world)["objectives"] if o["actor"] == "red-access")
    assert obj["status"] == "VERIFIED_SUCCESS"  # the alternative path verified
    store.close()


def test_blue_blocked_is_a_defensive_outcome_not_a_planning_failure(tmp_path):
    # When Blue contains Red on a structurally feasible scenario, the diagnosis is BLUE_BLOCKED.
    ep = blue_eval.run_episode(
        blue_eval.with_blue(make("blue_containment"), "reactive"), "adaptive", tmp_path
    )
    assert ep["red"]["feasible"] and not ep["red"]["verified"]
    assert ep["red"]["diagnosis"] == "BLUE_BLOCKED"


# --- Benign workload ----------------------------------------------------------


def test_benign_client_activity_is_not_flagged_malicious(tmp_path):
    # Authorized reads (own doc, public) and a mistyped login are not suspicious; a foreign read is.
    me = "acct-me"
    assert not _suspicious(
        {"tool": "read_document", "status": 200, "detail": {"owner": me}, "principal": me}
    )
    assert not _suspicious(
        {"tool": "read_document", "status": 200, "detail": {"owner": "public"}, "principal": me}
    )
    assert not _suspicious({"tool": "login", "status": 401, "detail": {}, "principal": me})
    assert _suspicious(
        {"tool": "read_document", "status": 200, "detail": {"owner": "acct-x"}, "principal": me}
    )
    # And a client reading its own document creates no incident in the real world.
    store, world = _world(tmp_path)
    client = world.actors["client-1"]
    world.act(client, Action(tool="login"))
    world.act(client, Action(tool="read_document", args={"document": _foreign(world, 1)}))
    assert not store.items("incidents")  # authorized self-read is not an incident
    store.close()


def test_false_containment_is_attributed_to_the_affected_client(tmp_path):
    # Mechanism: a (contrived) case citing a benign client event that contains the client is
    # recorded as a false containment and attributed to that client -- the attribution path works.
    store, world = _world(tmp_path)
    client = world.actors["client-1"]
    cp = world.principals["client-1"]
    world.act(client, Action(tool="login"))
    evt = world.act(client, Action(tool="read_document", args={"document": _foreign(world, 1)}))
    world.advance()
    mon = world.actors["blue-monitor"]
    opened = world.act(
        mon, Action(tool="open_case", args={"evidence_ids": [evt["event_id"]], "summary": "benign"})
    )
    world.advance()
    ir = world.actors["blue-ir"]
    res = world.act(
        ir, Action(tool="contain", args={"case_id": opened["case_id"], "principal": cp})
    )
    assert res.get("verified") is True
    assert store.get("metrics", "total")["false_containments"] == 1
    store.close()
    interventions = blue_eval._interventions(make("blue_containment"), tmp_path)
    fc = [i for i in interventions if i["attribution"] == "FALSE_CONTAINMENT"]
    assert fc and fc[0]["affected_principal"] == cp and not fc[0]["affected_is_red"]


# --- Information separation, observation time, determinism ---------------------


def test_no_future_telemetry_is_visible(tmp_path):
    store, world = _world(tmp_path)
    red = world.actors["red-access"]
    for _ in range(4):
        world.act(red, Action(tool="browse"))
        world.advance()
    tick = world.tick
    assert all(int(e["tick"]) <= 3 for e in store.events(through_tick=3, limit=1000))
    for ev in world.observe(red)["events"]:
        assert int(ev["tick"]) <= tick
    store.close()


def test_no_private_red_blue_or_scenario_state_leaks(tmp_path):
    store, world = _world(tmp_path)
    red = world.actors["red-access"]
    world.act(red, Action(tool="read_document", args={"document": _foreign(world)}))
    red_view = json.dumps(world.observe(red))
    blue_view = json.dumps(world.observe(world.actors["blue-monitor"]))
    # Red never sees Blue cases/offenders or any scenario label.
    for token in (
        "offenders",
        "case-evaluation",
        "expected_feasibility",
        "blue_containment",
        "VALID_FEASIBLE",
        "case_tp",
    ):
        assert token not in red_view
    # Blue never sees the scenario label or feasibility either.
    for token in (
        "expected_feasibility",
        "blue_containment",
        "VALID_FEASIBLE",
        "restricted_clients",
    ):
        assert token not in blue_view
    store.close()


def test_closed_loop_replay_is_deterministic(tmp_path):
    a = blue_eval.run_episode(
        blue_eval.with_blue(make("blue_containment"), "reactive"), "adaptive", tmp_path / "a"
    )
    b = blue_eval.run_episode(
        blue_eval.with_blue(make("blue_containment"), "reactive"), "adaptive", tmp_path / "b"
    )
    assert a["red"]["verified"] == b["red"]["verified"]
    assert a["blue"]["containments"] == b["blue"]["containments"]
    assert [i["control_tick"] for i in a["interventions"]] == [
        i["control_tick"] for i in b["interventions"]
    ]


def test_structural_witness_is_unchanged_by_the_runner(tmp_path):
    assert witness.run_witness(make("baseline"), tmp_path / "w")["status"] == "WITNESS_VERIFIED"
    rec = witness.witness_multipath(make("first_path_blocked"), tmp_path / "m")["recovery"]
    assert rec["status"] == "RECOVERY_VERIFIED"


# --- Paired study: structural feasibility vs reachability under Blue -----------


def test_paired_study_separates_feasibility_from_reachability(tmp_path):
    study = blue_eval.paired_study(
        make("blue_containment"), tmp_path, red_policy="adaptive", seeds=(1, 2, 3, 4)
    )
    assert study["structural_feasibility"] == "VALID_FEASIBLE"  # feasible with no Blue
    absent = study["conditions"]["absent"]["red_verified"]
    reactive = study["conditions"]["reactive"]["red_verified"]
    assert absent["rate"] > reactive["rate"]  # reactive Blue reduces reachability
    assert absent["ci95"] is not None and reactive["ci95"] is not None
    assert study["conditions"]["reactive"]["blue_verified_containments"] >= 1
