"""Stateful scenarios: independent feasibility, competence spread, and no leakage."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from saber.world import scenario
from saber.world.agents import action, llm_messages
from saber.world.scenario import ScenarioSpec, compare_policies, feasibility, make, run_scenario
from saber.world.service import LabServer
from saber.world.store import Store


def rows_by_policy(rows):
    return {r["policy"]: r for r in rows}


# --- Step 3: independent feasibility -------------------------------------------


def test_every_family_feasibility_matches_its_declared_label():
    for fam in scenario.FAMILIES:
        v = scenario.validate(make(fam))
        assert v["matches_expected"], f"{fam}: {v['feasibility']} != {v['expected_feasibility']}"


def test_feasibility_is_a_pure_function_of_the_spec():
    # It must not depend on running the red agent; calling it twice is identical and cheap.
    spec = make("budget_constrained")
    assert feasibility(spec) == feasibility(spec)
    assert feasibility(spec)["feasibility"] == "VALID_FEASIBLE"
    assert feasibility(make("environment_blocked"))["feasibility"] == "VALID_BLOCKED"


def test_schema_rejects_an_objective_with_no_matching_red_actor():
    with pytest.raises(ValidationError):
        ScenarioSpec(
            id="bad/dev/1",
            family="bad",
            split="dev",
            seed=1,
            objective="data_exfiltration",
            clients=2,
            red_roles=("impact",),  # no access actor for exfiltration
            blue_mode="absent",
            red_action_budget=40,
            tick_budget=40,
            attack_labels=(scenario._IMPACT_LABELS[0],),
            expected_feasibility="VALID_FEASIBLE",
        )


# --- Step 5: seed is a variant, not a new family; dev/held-out are distinct ------


def test_changing_only_the_seed_is_the_same_family_not_a_new_one():
    a, b = make("baseline", 1), make("baseline", 2)
    assert a.family == b.family and a.split == b.split
    assert a.seed != b.seed
    # Only the seed differs; structure and declared feasibility are identical.
    assert a.model_dump(exclude={"seed", "id"}) == b.model_dump(exclude={"seed", "id"})
    assert feasibility(a)["feasibility"] == feasibility(b)["feasibility"]


def test_dev_and_heldout_families_are_disjoint_and_structurally_distinct():
    assert set(scenario.DEV_FAMILIES) and set(scenario.HELDOUT_FAMILIES)
    assert not (set(scenario.DEV_FAMILIES) & set(scenario.HELDOUT_FAMILIES))

    def shape(f):
        data = make(f).model_dump(exclude={"seed", "id", "family", "split", "notes"})
        return json.dumps(data, sort_keys=True)

    dev_shapes = {shape(f) for f in scenario.DEV_FAMILIES}
    for f in scenario.HELDOUT_FAMILIES:
        assert shape(f) not in dev_shapes, f"held-out {f} is just a reseed of a dev family"


# --- Step 4: feasibility vs red competence -------------------------------------


def test_feasible_baseline_separates_competent_from_weak_policies(tmp_path):
    rows = rows_by_policy(compare_policies(make("budget_constrained"), tmp_path))
    assert rows["adaptive"]["feasibility"] == "VALID_FEASIBLE"
    # Only the adaptive policy reaches the verified objective within the tight budget.
    assert rows["adaptive"]["verified"] == 1
    assert rows["naive"]["verified"] == 0
    assert rows["random"]["verified"] == 0


def test_blocked_by_design_defeats_every_policy_not_just_weak_ones(tmp_path):
    rows = rows_by_policy(compare_policies(make("environment_blocked"), tmp_path))
    assert rows["adaptive"]["feasibility"] == "VALID_BLOCKED"
    for policy in ("adaptive", "naive", "random"):
        assert rows[policy]["verified"] == 0  # unreachable by design, independent of competence


def test_alternative_action_path_reaches_the_objective(tmp_path):
    # register_job is denied by the job ACL, but disruption still verifies service_impact.
    res = run_scenario(make("alternative_path"), "adaptive", tmp_path)
    assert res["verified"] == 1 and res["feasibility"] == "VALID_FEASIBLE"


def test_multiple_red_agents_are_attributed_per_principal(tmp_path):
    res = run_scenario(make("multiple_red"), "adaptive", tmp_path)
    assert res["total"] == 2 and res["verified"] == 2
    assert {o["actor"] for o in res["objectives"]} == {"red-access-1", "red-access-2"}


def test_scenario_metrics_are_deterministic_on_replay(tmp_path):
    a = run_scenario(make("baseline"), "adaptive", tmp_path / "a")
    b = run_scenario(make("baseline"), "adaptive", tmp_path / "b")
    assert a["verified"] == b["verified"] and a["steps_to_objective"] == b["steps_to_objective"]


# --- Step 5: no hidden-configuration leakage -----------------------------------


def _materialized(tmp_path, family):
    store = Store(tmp_path)
    world = scenario.materialize(store, make(family))
    server = LabServer(world)
    server.start()
    world.advance()
    return store, world, server


def test_private_scenario_metadata_never_reaches_agent_views(tmp_path):
    store, world, server = _materialized(tmp_path, "blue_containment")
    try:
        red = server.client("red-access")
        red.act(action("login"))
        red.act(action("browse"))
        server.client("client-1").act(action("login"))
        texts = [
            json.dumps(red.observe()),
            json.dumps(server.client("blue-monitor").observe()),
            json.dumps(
                llm_messages(world.actors["blue-monitor"], server.client("blue-monitor").observe())
            ),
            json.dumps(llm_messages(world.actors["red-access"], red.observe())),
        ]
        forbidden = (
            "VALID_FEASIBLE",
            "VALID_BLOCKED",
            "expected_feasibility",
            "blue_containment",
            "data_exfiltration",
            "scenario/v1",
            "heldout",
        )
        for text in texts:
            for token in forbidden:
                assert token not in text
    finally:
        server.close()
        store.close()


def test_benign_and_red_events_share_one_indistinguishable_schema(tmp_path):
    store, world, server = _materialized(tmp_path, "blue_containment")
    try:
        client = server.client("client-1")
        client.act(action("login"))
        benign = client.act(action("read_document", document=client.observe()["own_document"]))
        red = server.client("red-access")
        red.act(action("login"))
        hostile = red.act(action("read_document", document=f"work-{world.principals['client-1']}"))
        # Blue's event feed carries the same keys for both; no label marks one as the attack.
        events = server.client("blue-monitor").observe()["events"]
        by_id = {e["id"]: e for e in events}
        be, re = by_id[benign["event_id"]], by_id[hostile["event_id"]]
        assert set(be.keys()) == set(re.keys())
        assert "scenario" not in be and "family" not in be and "label" not in be
    finally:
        server.close()
        store.close()


def test_verification_uses_effects_not_the_declared_label(tmp_path):
    # The scenario declares VALID_FEASIBLE, but the verdict comes from the recorded
    # exfiltration effect, not from that label; a blocked design would verify nothing.
    feasible = run_scenario(make("baseline"), "adaptive", tmp_path / "a")
    blocked = run_scenario(make("environment_blocked"), "adaptive", tmp_path / "b")
    assert feasible["verified"] == 1 and blocked["verified"] == 0
