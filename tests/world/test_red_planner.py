"""Adaptive red planner: belief transitions, feedback recovery and verified stop."""

from __future__ import annotations

from saber.world import red_planner
from saber.world.environment import World
from saber.world.models import Actor, WorldConfig
from saber.world.red_planner import objective_complete, observe_belief, plan_action
from saber.world.runtime import Runner
from saber.world.store import Store

RECON = Actor(id="red-recon", team="red", role="recon", goal="x")
ACCESS = Actor(id="red-access", team="red", role="access", goal="x")
IMPACT = Actor(id="red-impact", team="red", role="impact", goal="x")


def obs(**kw):
    base = {
        "principal": "acct-x",
        "logged_in": True,
        "last_result": {},
        "events": [],
        "team_messages": [],
    }
    base.update(kw)
    return base


def read_evt(doc="work-acct-y", owner="acct-y"):
    return {"tool": "read_document", "status": 200, "target": doc, "detail": {"owner": owner}}


def test_logs_in_before_acting():
    assert plan_action(ACCESS, obs(logged_in=False), 0).tool == "login"


def test_containment_ends_the_campaign():
    restricted = {"status": 403, "error": "Session restricted by the security service."}
    assert plan_action(ACCESS, obs(last_result=restricted), 5).tool == "finish"


def test_enforced_acl_also_ends_the_campaign():
    # A patched document ACL denies the read with 403; the actor stops, not loops.
    denied = {"status": 403, "error": "Access denied."}
    assert plan_action(ACCESS, obs(last_result=denied), 5).tool == "finish"


def test_access_waits_out_a_transient_outage():
    action = plan_action(ACCESS, obs(last_result={"status": 503}), 5)
    assert action.tool == "wait" and action.args["ticks"] == 2


def test_access_reads_then_collects_then_exfiltrates():
    after_read = plan_action(ACCESS, obs(events=[read_evt()]), 3)
    assert after_read.tool == "collect" and after_read.args["document"] == "work-acct-y"
    staged = obs(events=[read_evt(), {"tool": "collect", "status": 201, "target": "work-acct-y"}])
    after_collect = plan_action(ACCESS, staged, 4)
    assert after_collect.tool == "exfiltrate" and after_collect.args["document"] == "work-acct-y"


def test_access_does_not_target_its_own_document():
    # Only a foreign work document is a valid objective; the actor's own is skipped.
    own = {
        "tool": "read_document",
        "status": 200,
        "target": "work-acct-x",
        "detail": {"owner": "acct-x"},
    }
    b = observe_belief(ACCESS, obs(events=[own]))
    assert b.read_foreign == frozenset()
    assert plan_action(ACCESS, obs(events=[own]), 2).tool in {"browse", "read_document"}


def test_access_objective_complete_on_verified_exfil():
    events = [{"tool": "exfiltrate", "status": 201, "target": "work-acct-y"}]
    b = observe_belief(ACCESS, obs(events=events))
    assert objective_complete("access", b)
    assert plan_action(ACCESS, obs(events=events), 3).tool == "finish"


def test_impact_registers_job_then_disrupts_then_stops():
    assert plan_action(IMPACT, obs(), 1).tool == "register_job"
    job = [{"tool": "register_job", "status": 201, "target": "sync-acct-x"}]
    assert plan_action(IMPACT, obs(events=job), 2).tool == "disrupt"
    done = job + [{"tool": "disrupt", "status": 202, "target": "business-app"}]
    assert plan_action(IMPACT, obs(events=done), 3).tool == "finish"


def test_impact_still_disrupts_when_persistence_is_denied():
    # An enforced job ACL denies register_job (403), but disruption is a separate path
    # the planner must still attempt rather than finishing prematurely.
    denied = {"status": 403, "tool": "register_job", "error": "Automation permission required."}
    assert plan_action(IMPACT, obs(last_result=denied), 3).tool == "disrupt"


def test_session_containment_stops_even_impact():
    restricted = {"status": 403, "tool": "disrupt", "error": "Session restricted by the service."}
    assert plan_action(IMPACT, obs(last_result=restricted), 3).tool == "finish"


def test_recon_shares_the_map_then_finishes():
    links = {"links": [{"id": "work-acct-y"}, {"id": "welcome"}]}
    assert plan_action(RECON, obs(last_result=links), 1).tool == "share"
    # Once the map has been shared on the red channel, recon's objective is complete.
    shared = obs(
        team_messages=[{"sender": "red-recon", "text": '{"document_links": ["work-acct-y"]}'}]
    )
    assert plan_action(RECON, shared, 2).tool == "finish"


def test_budget_exhaustion_finishes_cleanly():
    assert plan_action(ACCESS, obs(), red_planner.RED_BUDGET).tool == "finish"


def _blueless_config():
    actors = [
        Actor(id="client-1", team="client", role="employee", goal="work"),
        Actor(id="red-recon", team="red", role="recon", interval_ticks=1, goal="x"),
        Actor(id="red-access", team="red", role="access", interval_ticks=1, goal="x"),
        Actor(id="red-impact", team="red", role="impact", interval_ticks=1, goal="x"),
    ]
    return WorldConfig(actors=actors, seed=1, tick_seconds=0.01, red_start_tick=1)


def test_full_campaign_completes_and_is_deterministic(tmp_path):
    # Without a defender the adaptive campaign should reach a verified exfiltration,
    # register an unauthorized job, cause an outage, and then finish its actors.
    def run(root):
        store = Store(root)
        try:
            runner = Runner(store, _blueless_config())
            report = runner.run(ticks=40)
            access_done = World(store, _blueless_config())
            status = access_done.store.get("actor-control", "red-access", {}).get("status")
            return report["metrics"], status
        finally:
            store.close()

    metrics, access_status = run(tmp_path / "a")
    assert metrics["exfiltrated_bytes"] > 0
    assert metrics["unauthorized_reads"] > 0
    assert metrics["unauthorized_jobs"] > 0
    assert metrics["outage_ticks"] > 0
    assert access_status == "DONE"

    repeat, _ = run(tmp_path / "b")
    assert repeat["exfiltrated_bytes"] == metrics["exfiltrated_bytes"]
