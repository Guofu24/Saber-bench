from __future__ import annotations

import json
import threading
import time

import pytest

from saber.agents.provider import LLMResponse
from saber.world.agents import action, baseline, parse_plan
from saber.world.environment import World
from saber.world.models import Actor, default_config
from saber.world.runtime import Runner
from saber.world.service import LabServer
from saber.world.store import Store


@pytest.fixture
def lab(tmp_path):
    config = default_config(2)
    config = config.model_copy(
        update={
            "actors": config.actors
            + [
                Actor(id="dfir-two", team="blue", role="dfir", specialties=("malware",)),
            ]
        }
    )
    store = Store(tmp_path)
    world = World(store, config)
    server = LabServer(world)
    server.start()
    world.advance()
    try:
        yield world, server
    finally:
        server.close()
        store.close()


def case(server):
    eid = server.client("client-1").act(action("browse"))["event_id"]
    cid = server.client("blue-monitor").act(action("open_case", evidence_ids=[eid]))["case_id"]
    return cid, eid


def test_qualified_assignment_acceptance_handoff_and_cited_completion(lab):
    world, server = lab
    cid, eid = case(server)
    lead, first, second = (server.client(a) for a in ("blue-lead", "blue-dfir", "dfir-two"))
    offer = dict(
        case_id=cid, assignee="blue-dfir", specialty="dfir", objective="Reconstruct this session."
    )
    denied = lead.act(action("create_task", **(offer | {"specialty": "malware"})))
    assert denied["status"] == 400
    task = lead.act(action("create_task", **offer))["task"]
    assert lead.act(action("create_task", **offer))["task"]["id"] == task["id"]
    ref = dict(task_id=task["id"], expected_revision=0)
    assert second.act(action("accept_task", **ref))["status"] == 403
    assert first.act(action("accept_task", **ref))["task"]["status"] == "ACTIVE"
    assert first.observe()["active_specialty"] == "dfir"
    assert first.act(action("finish", reason="premature"))["status"] == 409
    assert lead.act(action("close_case", case_id=cid))["status"] == 409
    handoff = first.act(
        action(
            "handoff_task",
            task_id=task["id"],
            expected_revision=1,
            assignee="dfir-two",
            note="Review evidence before drawing a conclusion.",
            evidence_ids=[eid],
        )
    )
    assert handoff["task"]["status"] == "OFFERED"
    assert (
        first.act(
            action(
                "complete_task",
                task_id=task["id"],
                expected_revision=2,
                note="Not my task anymore",
                evidence_ids=[eid],
            )
        )["status"]
        == 403
    )
    assert (
        second.act(action("accept_task", task_id=task["id"], expected_revision=2))["status"] == 200
    )
    assert (
        second.act(
            action("complete_task", task_id=task["id"], expected_revision=3, note="No citations")
        )["status"]
        == 400
    )
    done = second.act(
        action(
            "complete_task",
            task_id=task["id"],
            expected_revision=3,
            note="Observed ordinary browsing; no evidence of compromise in this case.",
            evidence_ids=[eid],
        )
    )
    assert done["task"]["status"] == "DONE"
    assert len(done["task"]["history"]) == 4
    assert world.store.get("cases", cid)["status"] != "CLOSED"
    assert "tasks" not in server.client("red-access").observe()


def test_durable_notebook_is_private_and_other_actor_parameters_rejected(lab):
    world, server = lab
    blue = server.client("blue-dfir")
    assert (
        blue.act(action("write_note", kind="hypothesis", text="private hypothesis"))["status"]
        == 201
    )
    assert blue.act(action("read_notes"))["notes"][0]["text"] == "private hypothesis"
    assert server.client("blue-ir").act(action("read_notes"))["notes"] == []
    assert blue.act(action("read_notes", actor_id="blue-ir"))["status"] == 400
    for other in ("blue-ir", "red-access", "client-1"):
        assert "private hypothesis" not in json.dumps(server.client(other).observe())
    # Persists separately from the bounded planner memory.
    with world.store.transaction():
        world.store.put("memory", "blue-dfir", {"note": "new planner note"})
    assert blue.act(action("read_notes"))["notes"][0]["text"] == "private hypothesis"


def test_scripted_worker_accepts_and_uses_assigned_secondary_specialty(lab):
    world, server = lab
    cid, _ = case(server)
    actor = world.actors["dfir-two"]
    worker = server.client(actor.id)
    task = server.client("blue-lead").act(
        action(
            "create_task",
            case_id=cid,
            assignee=actor.id,
            specialty="malware",
            objective="Collect and describe this application artifact without executing it.",
        )
    )["task"]
    selected = []
    for turn in range(3):
        step = baseline(actor, worker.observe(), turn)
        selected.append(step.tool)
        assert worker.act(step)["status"] < 400
    assert selected == ["accept_task", "capture_artifact", "analyze_artifact"]
    obs = worker.observe()
    assert obs["active_specialty"] == "malware" and obs["artifacts"][0]["analyzed"]
    assert baseline(actor, obs, 3).tool == "share"
    assert world.store.get("tasks", task["id"])["status"] == "ACTIVE"
    # The scripted worker does not pretend its metadata extraction answers the task.


def test_wait_and_finish_stop_scripted_fallback_and_survive_restart(tmp_path):
    config = default_config(1).model_copy(update={"tick_seconds": 0.01})
    store = Store(tmp_path)
    runner = Runner(store, config)
    try:
        actor = config.actors[0]
        empty, _ = parse_plan(actor, '{"actions":[],"note":"waiting"}')
        assert [a.tool for a in empty] == ["wait"]
        client = runner.clients[actor.id]
        client.act(action("wait", ticks=3, reason="Work break."))
        runner.step()
        runner.step()
        assert store.get("memory", actor.id, {}).get("turns", 0) == 0
        runner.step()
        assert store.get("memory", actor.id)["turns"] == 1
        client.act(action("finish", reason="Mission completed."))
        runner.step()
        assert store.get("memory", actor.id)["turns"] == 1
        assert client.act(action("wait", reason="Cannot silently resume."))["status"] == 409
    finally:
        runner.close()
        store.close()

    store = Store(tmp_path)
    runner = Runner(store, config)
    try:
        runner.step()
        assert store.get("memory", config.actors[0].id)["turns"] == 1
        assert runner.clients[config.actors[0].id].observe()["control"]["status"] == "DONE"
    finally:
        runner.close()
        store.close()


def test_inflight_plan_cannot_restart_finished_actor(tmp_path):
    entered, released = threading.Event(), threading.Event()

    class Slow:
        model_id = "fake"

        def generate(self, messages, *, max_tokens=1024):
            entered.set()
            released.wait(timeout=5)
            return LLMResponse(
                text='{"actions":[{"tool":"write_document","args":{"text":"stale overwrite"}}]}',
                model_id="fake",
                input_tokens=1,
                output_tokens=1,
            )

    actor = Actor(id="client", team="client", role="person")
    cfg = default_config(1).model_copy(update={"actors": [actor]})
    store = Store(tmp_path)
    runner = Runner(store, cfg, provider=Slow())
    try:
        runner.step()
        assert entered.wait(timeout=2)
        assert (
            runner.clients["client"].act(
                action("finish", reason="Done before inference finished.")
            )["status"]
            == 200
        )
        released.set()
        deadline = time.monotonic() + 3
        while runner.planner.results.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        runner.step()
        world_control = store.get("actor-control", "client")
        assert world_control["status"] == "DONE"
        assert store.get("metrics", "total")["discarded_plans"] == 1
        assert "stale overwrite" not in json.dumps(store.items("documents"))
    finally:
        released.set()
        runner.close()
        store.close()
