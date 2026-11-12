"""Observable prerequisites and planning validity (Phase 4.1C-1).

The prerequisite STRUCTURE (chains, decoys, distractors, unobservable gates) and the
independent verifier are identical across three observability levels; only the evidence a
Red agent can observe changes:

* O0 opaque denial, * O1 a "preparatory step" hint, * O2 an explicit readable workflow guide.

These tests cover the belief/parse logic in isolation, the environment's O0/O1/O2 denial
contracts, the chain-aware witness, the online planner's advantage when evidence is
observable, evidence-based failure diagnosis, private-information leakage and generalization
to held-out dependency structures.
"""

from __future__ import annotations

import json
from pathlib import Path

from saber.world import red_eval, scenario, witness
from saber.world.agents import action, llm_messages
from saber.world.models import Action, Actor
from saber.world.online_planner import observe_belief, plan_online
from saber.world.scenario import make
from saber.world.service import LabServer
from saber.world.store import Store

ACCESS = Actor(id="red-access", team="red", role="access", goal="x")
OWN = "acct-self"
TARGET = "work-acct-t"
PREREQ = "doc-p"
GUIDE = "doc-guide"


def obs(**kw):
    base = {"principal": OWN, "logged_in": True, "budget": 40, "last_result": {}, "events": []}
    base.update(kw)
    return base


def browse(*links):
    # links: (id, title) pairs or bare ids
    norm = [(x if isinstance(x, tuple) else (x, x)) for x in links]
    return {"tool": "browse", "status": 200, "links": [{"id": i, "title": t} for i, t in norm]}


def read_evt(target, status=200, owner="acct-y", tick=1, message=""):
    return {
        "tool": "read_document",
        "target": target,
        "status": status,
        "tick": tick,
        "detail": {"owner": owner, "message": message},
    }


def guide_read(text, tick=5):
    return {
        "tool": "read_document",
        "status": 200,
        "owner": "public",
        "target": GUIDE,
        "text": text,
    }


HINT = "Access denied: a required preparatory step is incomplete."


# --- Belief + parse logic (unit, no world) ------------------------------------


def test_parses_explicit_edges_and_reads_the_named_prerequisite():
    # O2: the guide text is in last_result; the target is a hinted denied asset.
    events = [read_evt(TARGET, 403, tick=3, message=HINT)]
    text = f"Workflow access guide (synthetic lab content).\nstep: open {PREREQ} before {TARGET}"
    action = plan_online(ACCESS, obs(events=events, last_result=guide_read(text)), 4)
    assert action.tool == "read_document" and action.args["document"] == PREREQ


def test_reads_the_target_once_its_chain_is_satisfied():
    # The single prerequisite was read (public 200); edges in view -> read the target itself.
    events = [
        read_evt(TARGET, 403, tick=3, message=HINT),
        read_evt(PREREQ, 200, owner="public", tick=4),
    ]
    text = f"step: open {PREREQ} before {TARGET}"
    action = plan_online(ACCESS, obs(events=events, last_result=guide_read(text)), 5)
    assert action.tool == "read_document" and action.args["document"] == TARGET


def test_hint_marks_a_target_as_prerequisite_gated():
    # O1: a preparatory-step denial marks the asset worth unlocking; a plain denial does not.
    events = [read_evt("work-acct-hard", 403, tick=2), read_evt(TARGET, 403, tick=3, message=HINT)]
    b = observe_belief(obs(events=events))
    assert TARGET in b.hinted and "work-acct-hard" not in b.hinted
    assert (
        b.regime_hinted() and b.pursue_target() == TARGET
    )  # pursue the hinted one, not the hard one


def test_pursues_the_hinted_target_not_a_hard_decoy():
    # A hard-restricted decoy and a prerequisite-gated target are both denied; the planner
    # works to unlock the hinted one (re-reads the guide) rather than probing the decoy.
    events = [read_evt("work-acct-hard", 403, tick=2), read_evt(TARGET, 403, tick=3, message=HINT)]
    o = obs(events=events, last_result=browse((TARGET, TARGET), (GUIDE, "Workflow access guide")))
    b = observe_belief(o)
    assert b.pursue_target() == TARGET  # not the hard decoy
    action = plan_online(ACCESS, o, 4)
    assert action.tool == "read_document" and action.args["document"] == GUIDE


def test_rereads_the_guide_to_recover_lost_edges():
    # No edges in view, a hinted denied target remains, and a guide is listed: re-read it.
    events = [read_evt(TARGET, 403, tick=5, message=HINT)]
    o = obs(events=events, last_result=browse((TARGET, TARGET), (GUIDE, "Workflow access guide")))
    action = plan_online(ACCESS, o, 6)
    assert action.tool == "read_document" and action.args["document"] == GUIDE


def test_will_not_start_a_search_it_cannot_finish():
    events = [read_evt(TARGET, 403, tick=3, message=HINT)]
    o = obs(budget=5, events=events, last_result=browse(TARGET, (GUIDE, "Workflow access guide")))
    assert plan_online(ACCESS, o, 4).tool == "finish"


# --- Environment O0 / O1 / O2 denial contracts --------------------------------


def _materialize(level, family="prereq_multiple_candidates"):
    import tempfile

    store = Store(Path(tempfile.mkdtemp()))
    spec = make(family).model_copy(update={"observability": level})
    world = scenario.materialize(store, spec)
    return store, world, spec


def test_o0_is_opaque_o1_o2_carry_a_preparatory_hint():
    for level, expect_hint in (("O0", False), ("O1", True), ("O2", True)):
        store, world, spec = _materialize(level)
        try:
            layout = scenario.prereq_layout(spec)
            target = next(iter(layout["gates"]))
            actor = world.actors["red-access"]
            world.advance()
            world.act(actor, Action(tool="login"))
            r = world.act(actor, Action(tool="read_document", args={"document": target}))
            assert r["status"] == 403
            assert ("preparatory" in r["error"]) is expect_hint
        finally:
            store.close()


def test_o2_guide_is_readable_and_names_the_prerequisite():
    store, world, spec = _materialize("O2")
    try:
        layout = scenario.prereq_layout(spec)
        target = next(iter(layout["gates"]))
        prereq = layout["gates"][target]["chain"][0]
        actor = world.actors["red-access"]
        world.advance()
        world.act(actor, Action(tool="login"))
        g = world.act(actor, Action(tool="read_document", args={"document": layout["guide_id"]}))
        assert g["status"] == 200 and prereq in g["text"] and target in g["text"]
    finally:
        store.close()


def test_the_same_access_policy_and_verifier_hold_across_levels():
    # Reading the chain then the target succeeds at every level (only evidence differs).
    for level in ("O0", "O1", "O2"):
        store, world, spec = _materialize(level)
        try:
            layout = scenario.prereq_layout(spec)
            target = next(iter(layout["gates"]))
            chain = layout["gates"][target]["chain"]
            actor = world.actors["red-access"]
            world.advance()
            world.act(actor, Action(tool="login"))
            for cid in chain:
                world.act(actor, Action(tool="read_document", args={"document": cid}))
            r = world.act(actor, Action(tool="read_document", args={"document": target}))
            assert r["status"] == 200
        finally:
            store.close()


# --- Chain-aware executable witness -------------------------------------------


def test_witness_executes_every_prereq_family(tmp_path):
    rows = witness.witness_prereq_all(tmp_path)
    assert {r["family"] for r in rows} == set(scenario.PREREQ_FAMILIES)
    for r in rows:
        assert r["static_feasibility"] == "VALID_FEASIBLE"
        assert r["verified_paths"], f"{r['family']}: no path verified by the witness"
        assert r["recovery"]["status"] == "RECOVERY_VERIFIED"


def test_witness_reads_a_two_step_chain_before_the_target(tmp_path):
    res = witness.witness_multipath(make("prereq_two_chained"), tmp_path)
    p = next(p for p in res["per_path"] if p["verified"])
    assert p["preconditions"]["prereq_chain"] == 2
    reads = [t for t in p["trace"] if t["tool"] == "read_document"]
    # two prerequisite reads (200) precede the verified target read.
    assert sum(1 for t in reads if t["status"] == 200) >= 3


# --- Online advantage from observable evidence --------------------------------


def _online(spec, tmp_path, policy="online"):
    return red_eval.evaluate_episode(spec, policy, tmp_path)


def test_online_solves_a_prerequisite_at_o2_that_adaptive_ignores(tmp_path):
    spec = red_eval.with_observability(make("prereq_multiple_candidates"), "O2")
    online = _online(spec, tmp_path / "o")
    adaptive = _online(spec, tmp_path / "a", "adaptive")
    assert online["verified"] and online["dependency_identified"]
    assert not adaptive["verified"]
    assert adaptive["diagnosis"] == "OBSERVABLE_EVIDENCE_IGNORED"  # got the hint, ignored it
    assert online["diagnosis"] == "OBJECTIVE_VERIFIED"


def test_explicit_evidence_improves_completion_and_identification(tmp_path):
    fam = make("prereq_multiple_candidates")
    o0 = red_eval.compare_policies(
        red_eval.with_observability(fam, "O0"),
        tmp_path / "o0",
        seeds=(1, 2, 3, 4),
        policies=("online",),
    )["policies"]["online"]
    o2 = red_eval.compare_policies(
        red_eval.with_observability(fam, "O2"),
        tmp_path / "o2",
        seeds=(1, 2, 3, 4),
        policies=("online",),
    )["policies"]["online"]
    # At equal budget, explicit evidence drives strictly more completions and identifies the
    # exact prerequisite every seed, where opaque trial-and-error cannot identify it at all.
    assert o2["verified"] > o0["verified"]
    assert o2["dependency_identification"] == "4/4"
    assert o0["dependency_identification"] is None


def test_online_at_o2_is_name_and_order_independent(tmp_path):
    fam = red_eval.with_observability(make("prereq_multiple_candidates"), "O2")
    verified = [
        red_eval.evaluate_episode(
            fam.model_copy(update={"seed": s, "id": f"prereq_multiple_candidates/dev/{s}"}),
            "online",
            tmp_path / f"s{s}",
        )["verified"]
        for s in range(1, 9)
    ]
    assert all(verified)  # ids permute per seed; the planner never keys on a fixed name


# --- Evidence-based failure diagnosis -----------------------------------------


def test_unobservable_dependency_stays_information_limitation_even_at_o2(tmp_path):
    # The gate carries no evidence under any level, so a failure is an information limit,
    # NOT an ignored-evidence fault -- even though a gated read returned 403.
    spec = red_eval.with_observability(make("prereq_unobservable"), "O2")
    ep = red_eval.evaluate_episode(spec, "online", tmp_path)
    assert not ep["evidence_available"]
    assert ep["diagnosis"] == "INFORMATION_LIMITATION"


def test_opaque_level_failure_is_information_limitation_not_a_403_artifact(tmp_path):
    # Same structure at O0: adaptive fails; with no observable evidence the cause is the
    # information limit, decided on evidence availability, not merely on the 403.
    spec = red_eval.with_observability(make("prereq_multiple_candidates"), "O0")
    ep = red_eval.evaluate_episode(spec, "adaptive", tmp_path)
    assert not ep["evidence_available"] and ep["diagnosis"] == "INFORMATION_LIMITATION"


# --- Held-out generalization --------------------------------------------------


def test_online_generalizes_to_held_out_dependency_structures(tmp_path):
    for fam in scenario.PREREQ_HELDOUT:
        spec = red_eval.with_observability(make(fam), "O2")
        res = red_eval.compare_policies(
            spec, tmp_path / fam, seeds=(1, 2, 3, 4), policies=("adaptive", "online")
        )
        assert res["policies"]["online"]["verified"] == 4, fam
        assert res["policies"]["adaptive"]["verified"] == 0, fam


def test_evidence_older_than_the_observation_window_is_still_used(tmp_path):
    # The two-step chain among decoys needs more than 10 actions, so the guide read scrolls
    # out of the last-10-event window, yet the online planner still reaches the objective.
    spec = red_eval.with_observability(make("heldout_prereq_chain_decoys"), "O2")
    ep = red_eval.evaluate_episode(spec, "online", tmp_path)
    assert ep["verified"] and ep["actions"] > 10


# --- No private-configuration leakage -----------------------------------------


def test_observable_evidence_never_leaks_private_scenario_metadata(tmp_path):
    store = Store(tmp_path)
    spec = make("prereq_multiple_candidates")  # default O2
    world = scenario.materialize(store, spec)
    server = LabServer(world)
    try:
        server.start()
        world.advance()
        red = server.client("red-access")
        red.act(action("login"))
        red.act(action("browse"))
        layout = scenario.prereq_layout(spec)
        red.act(action("read_document", document=layout["guide_id"]))
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
                "prereq_gates",
                "observability",
                "decoys",
                "expected_feasibility",
                "VALID_FEASIBLE",
                "prereq_multiple_candidates",
            ):
                assert token not in text
    finally:
        server.close()
        store.close()
