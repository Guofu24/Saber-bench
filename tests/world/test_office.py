"""Operator snapshots track real runtime counters without exposing private world state."""

import json

from saber.population.office import OfficeEmitter
from saber.world.models import default_config
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
