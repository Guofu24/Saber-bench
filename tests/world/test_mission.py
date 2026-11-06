"""Mission outcome: avoidable loss of client work is charged; justified containment is not."""

from __future__ import annotations

import json

from saber.world.agents import action, llm_messages
from saber.world.environment import World
from saber.world.mission import mission_outcome, wilson
from saber.world.models import default_config
from saber.world.service import LabServer
from saber.world.store import Store

CLIENTS = ("client-1", "client-2")


def attack(world, server):
    red = server.client("red-access")
    red.act(action("login"))
    name = f"work-{world.principals['client-1']}"
    read = red.act(action("read_document", document=name))["event_id"]
    collect = red.act(action("collect", document=name))["event_id"]
    disrupt = server.client("red-impact").act(action("disrupt"))["event_id"]
    return read, collect, disrupt


def passive(world, server, events):
    pass


def targeted(world, server, events):
    read, collect, disrupt = events
    blue, ir = server.client("blue-monitor"), server.client("blue-ir")
    theft = blue.act(action("open_case", evidence_ids=[read, collect]))["case_id"]
    ir.act(action("contain", case_id=theft, principal=world.principals["red-access"]))
    outage = blue.act(action("open_case", evidence_ids=[disrupt]))["case_id"]
    ir.act(action("restore", case_id=outage))


def indiscriminate(world, server, events):
    # Opens a case for every visible event and blocks whoever appears in it.
    blue, ir = server.client("blue-monitor"), server.client("blue-ir")
    for event in blue.observe()["events"]:
        cid = blue.act(action("open_case", evidence_ids=[event["id"]]))["case_id"]
        ir.act(action("contain", case_id=cid, principal=event["principal"]))
        if event["tool"] == "disrupt":
            ir.act(action("restore", case_id=cid))


def run(root, defender, *, attacked=True, work_ticks=10):
    store = Store(root)
    world = World(store, default_config(2))
    server = LabServer(world)
    server.start()
    world.advance()
    try:
        clients = [server.client(c) for c in CLIENTS]
        for client in clients:
            client.act(action("login"))
        defender(world, server, attack(world, server) if attacked else None)
        for _ in range(work_ticks):
            world.advance()
            for client in clients:
                client.act(action("call_app"))
        text = json.dumps(
            llm_messages(world.actors["blue-monitor"], server.client("blue-monitor").observe())
        )
        assert "client_denied" not in text and "work_availability" not in text
        return world.report()["mission"]
    finally:
        server.close()
        store.close()


def test_targeted_defender_beats_passive_and_indiscriminate(tmp_path):
    idle = run(tmp_path / "passive", passive)
    good = run(tmp_path / "targeted", targeted)
    blunt = run(tmp_path / "indiscriminate", indiscriminate)
    # Red's outage lasts incident_ttl_ticks without a restore: 5 work ticks x 2 clients.
    assert idle["client_denied_outage"] == 10 and idle["detection_quality"] == 0
    assert good["work_availability"] == 1 and good["detection_quality"] == 1
    assert good["client_denied_collateral"] == 0 and good["mission_score"] == 1
    assert blunt["client_denied_collateral"] == 20
    assert blunt["work_availability"] < idle["work_availability"]
    assert blunt["false_containment_rate"] > 0
    # Detection cannot buy back the work a blunt defender destroyed.
    assert good["mission_score"] > idle["mission_score"] > blunt["mission_score"]


def test_quiet_world_charges_blocking_users_without_any_attack(tmp_path):
    idle = run(tmp_path / "passive", passive, attacked=False)
    blunt = run(tmp_path / "indiscriminate", indiscriminate, attacked=False)
    assert idle["mission_score"] == 1 and idle["detection_quality"] is None
    assert blunt["client_denied_collateral"] == 20
    assert blunt["mission_score"] < idle["mission_score"]


def test_containing_an_offending_client_is_not_collateral(tmp_path):
    store = Store(tmp_path)
    world = World(store, default_config(2))
    server = LabServer(world)
    server.start()
    world.advance()
    try:
        client = server.client("client-2")
        client.act(action("login"))
        read = client.act(action("read_document", document=f"work-{world.principals['client-1']}"))
        cid = server.client("blue-monitor").act(
            action("open_case", evidence_ids=[read["event_id"]])
        )["case_id"]
        server.client("blue-ir").act(
            action("contain", case_id=cid, principal=world.principals["client-2"])
        )
        assert client.act(action("call_app"))["status"] == 403
        mission = world.report()["mission"]
        assert mission["client_denied_containment"] == 1
        assert mission["client_denied_collateral"] == 0
        assert mission["work_availability"] == 1
        assert mission["false_containment_rate"] == 0
    finally:
        server.close()
        store.close()


def test_empty_and_legacy_metrics_do_not_fail():
    empty = mission_outcome({})
    assert empty["mission_score"] is None and empty["work_availability_ci95"] is None
    # Worlds created before these counters existed report zero avoidable loss.
    legacy = mission_outcome({"client_requests": 4, "client_failures": 1})
    assert legacy["work_availability"] == 1 and legacy["mission_score"] == 1


def test_wilson_interval_stays_in_unit_range():
    assert wilson(0, 0) is None
    low, high = wilson(10, 10)
    assert 0.6 < low < 1 and high == 1.0
    low, high = wilson(0, 3)
    assert low == 0.0 and 0 < high < 1
