"""Independent red-objective verification: effect-based truth, evidence-based attribution."""

from __future__ import annotations

import json

import pytest

from saber.world.agents import action, llm_messages
from saber.world.environment import World
from saber.world.models import Actor, WorldConfig, default_config
from saber.world.red_metrics import _new_record
from saber.world.red_planner import RED_BUDGET
from saber.world.runtime import Runner
from saber.world.service import LabServer
from saber.world.store import Store


@pytest.fixture
def lab(tmp_path):
    store = Store(tmp_path)
    world = World(store, default_config(2))
    server = LabServer(world)
    server.start()
    world.advance()
    try:
        yield world, server
    finally:
        server.close()
        store.close()


def objective_for(world, actor_id):
    for o in world.report()["red_objectives"]["objectives"]:
        if o["actor"] == actor_id:
            return o
    raise AssertionError(f"no objective for {actor_id}")


def exfil_chain(world, server):
    red = server.client("red-access")
    red.act(action("login"))
    name = f"work-{world.principals['client-1']}"
    read = red.act(action("read_document", document=name))
    red.act(action("collect", document=name))
    return red, name, read


def open_case(server, event_id):
    return server.client("blue-monitor").act(action("open_case", evidence_ids=[event_id]))[
        "case_id"
    ]


def test_1_red_reaches_objective_without_blue(lab):
    world, server = lab
    red, name, _ = exfil_chain(world, server)
    staged = red.act(action("exfiltrate", document=name))
    assert staged["status"] == 201
    obj = objective_for(world, "red-access")
    assert obj["status"] == "VERIFIED_SUCCESS" and obj["effect_verified"] is True
    # login, read, collect, exfiltrate = 4 actions to the verified effect.
    assert obj["steps_to_objective"] == 4
    report = world.report()["red_objectives"]
    assert report["red_objectives_verified"] >= 1


def test_2_blue_containment_before_objective(lab):
    world, server = lab
    red, name, read = exfil_chain(world, server)
    cid = open_case(server, read["event_id"])
    contained = server.client("blue-ir").act(
        action("contain", case_id=cid, principal=world.principals["red-access"])
    )
    assert contained["verified"] is True
    assert red.act(action("exfiltrate", document=name))["status"] == 403
    obj = objective_for(world, "red-access")
    assert obj["effect_verified"] is False and obj["status"] == "VERIFIED_FAILURE"
    assert obj["blocked_by_blue"] is True and obj["containment_before_objective"] is True
    assert world.report()["red_objectives"]["blue_containment_before_objective"] >= 1


def test_3_blue_detection_after_objective(lab):
    world, server = lab
    red, name, _ = exfil_chain(world, server)
    staged = red.act(action("exfiltrate", document=name))
    world.advance()
    world.advance()
    open_case(server, staged["event_id"])  # detection happens only now, after exfiltration
    obj = objective_for(world, "red-access")
    assert obj["status"] == "VERIFIED_SUCCESS"
    assert obj["detection_before_objective"] is False


def test_4_acl_denial_without_containment(lab):
    world, server = lab
    server.client("blue-content").act(action("patch", control="document_acl"))
    red = server.client("red-access")
    red.act(action("login"))
    denied = red.act(action("read_document", document=f"work-{world.principals['client-1']}"))
    assert denied["status"] == 403
    obj = objective_for(world, "red-access")
    assert obj["attempted"] is True and obj["effect_verified"] is False
    assert obj["blocked_by_blue"] is True
    # An enforced ACL is a defender control, but it is not an active containment.
    assert obj["containment_before_objective"] is False
    assert world.report()["red_objectives"]["blue_containment_before_objective"] == 0


def test_5_objective_not_attempted_is_not_a_blue_win(lab):
    world, server = lab
    exfil_chain(world, server)  # only access acts; impact never does
    obj = objective_for(world, "red-impact")
    assert obj["status"] == "NOT_ATTEMPTED"
    assert obj["detection_before_objective"] is False and obj["blocked_by_blue"] is False
    assert obj["containment_before_objective"] is False


def test_6_attempt_without_verified_effect_is_in_progress(lab):
    world, server = lab
    red = server.client("red-access")
    red.act(action("login"))
    red.act(action("read_document", document=f"work-{world.principals['client-1']}"))
    obj = objective_for(world, "red-access")
    assert obj["attempted"] is True and obj["artifact_observed"] is True
    assert obj["effect_verified"] is False and obj["status"] == "IN_PROGRESS"


def test_7_budget_exhaustion_is_a_verified_failure(lab):
    world, _ = lab
    principal = world.principals["red-access"]
    rec = _new_record("access", "data_exfiltration")
    rec.update({"actions": RED_BUDGET, "attempted": True, "artifact_observed": True})
    with world.store.transaction():
        world.store.put("red-objectives", principal, rec)
    obj = objective_for(world, "red-access")
    assert obj["budget_exhausted"] is True and obj["status"] == "VERIFIED_FAILURE"
    assert obj["blocked_by_blue"] is False


def test_8_activity_without_a_recorded_attempt_is_unknown(lab):
    world, _ = lab
    principal = world.principals["red-access"]
    with world.store.transaction():
        world.store.put(
            "incidents", "901", {"tick": 1, "principal": principal, "detected_tick": None}
        )
    obj = objective_for(world, "red-access")
    assert obj["attempted"] is False and obj["status"] == "UNKNOWN"


def test_finished_attempt_without_attributable_cause_is_unknown(lab):
    world, _ = lab
    principal = world.principals["red-access"]
    rec = _new_record("access", "data_exfiltration")
    rec.update({"actions": 3, "attempted": True, "artifact_observed": True})
    with world.store.transaction():
        world.store.put("red-objectives", principal, rec)
        # Actor stopped, not verified, and no containment/ACL/outage/budget cause.
        world.store.put("actor-control", "red-access", {"status": "DONE", "generation": 1})
    obj = objective_for(world, "red-access")
    assert obj["status"] == "UNKNOWN" and obj["blocked_by_blue"] is False


def test_9_multiple_red_agents_in_one_episode(lab):
    world, server = lab
    red, name, _ = exfil_chain(world, server)
    red.act(action("exfiltrate", document=name))
    impact = server.client("red-impact")
    impact.act(action("login"))
    impact.act(action("register_job", name="sync-x"))
    impact.act(action("disrupt"))
    report = world.report()["red_objectives"]
    assert report["red_objectives_total"] == 2
    assert report["red_objectives_verified"] == 2
    assert report["red_objective_completion_rate"] == 1.0


def _blueless_config():
    actors = [
        Actor(id="client-1", team="client", role="employee", goal="work"),
        Actor(id="red-recon", team="red", role="recon", interval_ticks=1, goal="x"),
        Actor(id="red-access", team="red", role="access", interval_ticks=1, goal="x"),
        Actor(id="red-impact", team="red", role="impact", interval_ticks=1, goal="x"),
    ]
    return WorldConfig(actors=actors, seed=3, tick_seconds=0.01, red_start_tick=1)


def test_10_metrics_are_deterministic_on_replay(tmp_path):
    def run(root):
        store = Store(root)
        try:
            return Runner(store, _blueless_config()).run(ticks=40)["red_objectives"]
        finally:
            store.close()

    first = run(tmp_path / "a")
    second = run(tmp_path / "b")
    keys = (
        "red_objectives_total",
        "red_objectives_attempted",
        "red_objectives_verified",
        "red_objective_completion_rate",
        "red_steps_to_objective",
        "red_objectives_blocked_by_blue",
        "red_objectives_blocked_by_environment",
    )
    assert {k: first[k] for k in keys} == {k: second[k] for k in keys}


def test_11_objective_labels_never_leak_to_agents(lab):
    world, server = lab
    exfil_chain(world, server)
    blue_text = json.dumps(
        llm_messages(world.actors["blue-monitor"], server.client("blue-monitor").observe())
    )
    red_text = json.dumps(server.client("red-access").observe())
    for forbidden in (
        "red_objectives",
        "effect_verified",
        "data_exfiltration",
        "steps_to_objective",
    ):
        assert forbidden not in blue_text
        assert forbidden not in red_text


def test_12_repeated_exfiltration_does_not_double_count(lab):
    world, server = lab
    red, name, _ = exfil_chain(world, server)
    red.act(action("exfiltrate", document=name))
    red.act(action("exfiltrate", document=name))  # repeat: same objective, already verified
    obj = objective_for(world, "red-access")
    assert obj["steps_to_objective"] == 4
    assert world.report()["red_objectives"]["red_objectives_verified"] == 1
