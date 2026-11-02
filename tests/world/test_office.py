"""Operator snapshots track real runtime counters without exposing private world state."""

import json

from saber.population.office import OfficeEmitter
from saber.world.agents import action
from saber.world.models import default_config
from saber.world.office_trace import trace
from saber.world.runtime import Runner
from saber.world.store import Store


def test_snapshot_lifecycle_resume_and_private_fields(tmp_path):
    events = []
    (tmp_path / "deployment.json").write_text('{"selected_profile":"sandbox"}')
    store = Store(tmp_path)
    cfg = default_config(2).model_copy(update={"tick_seconds": 0.01})
    runner = Runner(store, cfg, emitter=OfficeEmitter(sink=events.extend))
    assert events[-1]["status"] == "running"
    with store.transaction():
        store.put("memory", "client-1", {"note": "PRIVATE PLAN", "credential": "SECRET"})
    report = runner.run(ticks=3)
    saved = json.loads((tmp_path / "office.json").read_text())
    assert saved == events[-1]
    assert saved["status"] == "stopped" and saved["profile"] == "sandbox"
    assert saved["tick"] == report["tick"] == 3
    assert saved["engine"] == "scripted" and saved["llm"]["attempts"] == 0
    assert saved["actions"]["actions_scripted"] == report["metrics"]["actions_scripted"]
    assert len(saved["actors"]) == len(cfg.actors)
    assert saved["actors"][0]["last_tick"] == 3
    assert saved["actors"][0]["turns"] == 3
    assert all(e["type"] == "world_snapshot" for e in events)
    assert all(a["activity"] == "idle" for a in saved["actors"])
    assert "PRIVATE PLAN" not in json.dumps(events) and "SECRET" not in json.dumps(events)
    assert "documents" not in saved and "url" not in saved
    resumed = Runner(store, cfg, emitter=OfficeEmitter(sink=events.extend))
    try:
        assert events[-1]["world_id"] == saved["world_id"]
        assert events[-1]["run_id"] != saved["run_id"]
        assert events[-1]["tick"] == 3 and events[-1]["status"] == "running"
    finally:
        resumed.close()
        store.close()


def test_snapshot_uses_provider_ledger_and_only_pool_indices(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, default_config(1))
    try:
        with store.transaction():
            store.put("meta", "engine", "hybrid")
            store.put("meta", "llm_key_layout", "teams")
            store.put(
                "meta",
                "llm_usage",
                {
                    "attempts": 7,
                    "successes": 5,
                    "input_tokens": 70,
                    "output_tokens": 25,
                    "by_team": {"red": {"attempts": 3, "successes": 2}},
                },
            )
            store.put(
                "llm-pools",
                "red",
                {
                    "model": "fake",
                    "first_key": 201,
                    "last_key": 400,
                    "keys": 200,
                    "active_key": 202,
                    "state": "cooling_down",
                    "secret": "NEVER EXPORT",
                },
            )
        runner.step()
        saved = json.loads((tmp_path / "office.json").read_text())
        assert saved["llm"] == {
            "attempts": 7,
            "successes": 5,
            "input_tokens": 70,
            "output_tokens": 25,
        }
        assert saved["llm_by_team"]["red"]["attempts"] == 3
        assert saved["pools"]["red"]["active_key"] == 202
        assert "NEVER EXPORT" not in json.dumps(saved)
    finally:
        runner.close()
        store.close()


def test_office_shows_work_state_without_task_objectives_or_notebook_text(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, default_config(1))
    try:
        client = runner.clients["client-1"]
        client.act(action("write_note", kind="hypothesis", text="PRIVATE NOTE"))
        event = client.act(action("browse"))["event_id"]
        cid = runner.clients["blue-monitor"].act(action("open_case", evidence_ids=[event]))[
            "case_id"
        ]
        task = runner.clients["blue-lead"].act(
            action(
                "create_task",
                case_id=cid,
                assignee="blue-dfir",
                specialty="dfir",
                objective="PRIVATE OBJECTIVE",
            )
        )["task"]
        runner.clients["blue-dfir"].act(
            action("accept_task", task_id=task["id"], expected_revision=0)
        )
        client.act(action("finish", reason="PRIVATE REASON"))
        with store.transaction():
            store.put(
                "learning-proposals",
                "test-proposal",
                {
                    "actor_id": "client-1",
                    "status": "AWAITING_SUITE",
                    "lesson": "PRIVATE LESSON",
                },
            )
        runner._publish_office(runner.world.report())
        snapshot = json.loads((tmp_path / "office.json").read_text())
        by_id = {a["id"]: a for a in snapshot["actors"]}
        assert by_id["client-1"]["control_status"] == "DONE"
        assert by_id["blue-dfir"]["active_task"] == task["id"]
        assert by_id["blue-dfir"]["task_counts"]["active"] == 1
        assert by_id["client-1"]["learning_counts"] == {
            "episodes": 1,
            "proposals": 1,
            "published": 0,
        }
        assert "PRIVATE" not in json.dumps(snapshot)
    finally:
        runner.close()
        store.close()


def test_trace_links_executed_read_case_and_containment_without_private_bodies(tmp_path):
    store = Store(tmp_path)
    cfg = default_config(1)
    runner = Runner(store, cfg)
    try:
        red = runner.clients["red-access"]
        principal = runner.world.principals["red-access"]
        document = "work-" + runner.world.principals["client-1"]
        red.act(action("login"))
        read = red.act(action("read_document", document=document))
        assert read["status"] == 200 and "text" in read
        case_id = runner.clients["blue-monitor"].act(
            action("open_case", evidence_ids=[read["event_id"]], summary="PRIVATE CASE SUMMARY")
        )["case_id"]
        response = runner.clients["blue-ir"].act(
            action("contain", case_id=case_id, principal=principal)
        )
        assert response["verified"] is True
        blocked = red.act(action("collect", document=document))
        assert blocked["status"] == 403
        with store.transaction():
            store.put(
                "journals",
                "blue-ir",
                [
                    {
                        "event_id": response["event_id"],
                        "source": "scripted",
                        "action": {"args": {"case_id": case_id, "secret": "PRIVATE ARGS"}},
                    }
                ],
            )
        runner._publish_office(runner.world.report())
        saved = json.loads((tmp_path / "office.json").read_text())
        history = saved["trace"]
        rows = {e["id"]: e for e in history["events"]}
        assert rows[read["event_id"]]["actor_id"] == "red-access"
        assert rows[read["event_id"]]["source"] == "unknown"  # Direct HTTP is not an LLM plan.
        assert rows[response["event_id"]]["case_id"] == case_id
        assert rows[response["event_id"]]["target_actor_id"] == "red-access"
        assert rows[response["event_id"]]["source"] == "scripted"
        assert rows[blocked["event_id"]]["status"] == 403
        case = history["cases"][0]
        assert case["evidence_ids"] == [read["event_id"]]
        assert case["responses"][0]["actor_id"] == "blue-ir"
        assert case["responses"][0]["verified"] is True
        assert "PRIVATE" not in json.dumps(saved)
        assert read["text"] not in json.dumps(saved)
        assert "unauthorized_access" not in json.dumps(saved)
    finally:
        runner.close()
        store.close()


def test_trace_is_bounded_and_never_reads_future_events(tmp_path):
    store = Store(tmp_path)
    cfg = default_config(1)
    runner = Runner(store, cfg)
    try:
        principal = runner.world.principals["client-1"]
        with store.transaction():
            for _ in range(205):
                store.event(0, principal, "browse", "portal", 200, {}, {"secret": "PRIVATE"})
            future = store.event(999, principal, "browse", "future", 200, {}, {})
        history = trace(store, cfg, 0)
        assert len(history["events"]) == history["limit"] == 200
        assert history["events"][-1]["id"] == future - 1
        assert history["events"][0]["id"] == future - 200
        assert "PRIVATE" not in json.dumps(history)
    finally:
        runner.close()
        store.close()
