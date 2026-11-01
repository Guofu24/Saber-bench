"""Resume, failure handling, bounded storage and nonblocking inference."""

from __future__ import annotations

import gzip
import json
import threading
import time

import pytest
from click.testing import CliRunner

from saber.agents.provider import LLMResponse
from saber.cli.main import cli
from saber.world.agents import action
from saber.world.models import default_config
from saber.world.runtime import Runner, WorldLock
from saber.world.store import Store


def config():
    return default_config(2).model_copy(update={"tick_seconds": 0.01})


def test_shared_world_runs_and_resumes_without_deleting_any_state(tmp_path):
    cfg = config()
    store = Store(tmp_path)
    runner = Runner(store, cfg)
    report = runner.run(ticks=24)
    assert report["metrics"]["cases"] > 0
    assert report["metrics"]["verified_responses"] > 0
    assert report["metrics"]["unauthorized_reads"] > 0
    assert report["metrics"]["unauthorized_jobs"] > 0
    first_id = store.events(through_tick=24, limit=2000)[0]["id"]
    requests = report["metrics"]["requests"]
    world_id = report["world_id"]
    exported = [
        json.loads(line)
        for line in (tmp_path / "access.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(exported) == requests
    assert all(e["world_id"] == world_id and "effect" not in e for e in exported)
    docs = store.items("documents")
    store.close()
    store = Store(tmp_path)
    resumed = Runner(store, cfg)
    assert resumed.world.tick == 24
    assert store.items("documents") == docs
    report = resumed.run(ticks=3)
    assert report["tick"] == 27
    assert report["world_id"] == world_id
    assert report["metrics"]["requests"] > requests
    assert store.events(through_tick=27, limit=2000)[0]["id"] == first_id
    store.close()


def test_stop_is_graceful_and_does_not_advance_world(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, config())
    (tmp_path / "STOP").write_text("stop")
    report = runner.run(ticks=10)
    assert report["tick"] == 0 and report["stop_reason"] == "stop_file"
    assert not runner.server.thread.is_alive()
    store.close()


def test_world_lock_refuses_second_writer_and_releases(tmp_path):
    with WorldLock(tmp_path):
        with pytest.raises(RuntimeError, match="already running"), WorldLock(tmp_path):
            pass
    with WorldLock(tmp_path):
        pass


def test_change_of_world_identity_is_rejected(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, config())
    runner.close()
    with pytest.raises(ValueError, match="differs"):
        Runner(store, config().model_copy(update={"seed": 99}))
    store.close()


def test_slow_provider_does_not_stop_clients_and_secret_plans_stay_private(tmp_path):
    entered, release = threading.Event(), threading.Event()

    class Slow:
        model_id = "fake"

        def generate(self, messages, *, max_tokens=1024):
            entered.set()
            release.wait(timeout=10)
            return LLMResponse(
                text='{"actions":[{"tool":"browse","args":{}}],"note":"private memory"}',
                model_id="fake",
                input_tokens=10,
                output_tokens=5,
            )

    store = Store(tmp_path)
    runner = Runner(store, config(), provider=Slow())
    try:
        runner.step()
        assert entered.wait(timeout=2)
        for _ in range(2):
            runner.step()
        assert runner.world.report()["metrics"]["client_requests"] == 6
        assert not release.is_set()
        release.set()
        deadline = time.monotonic() + 3
        while runner.planner.results.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        runner.step()
        assert any(m.get("plan_source") == "llm" for m in store.items("memory").values())
    finally:
        release.set()
        runner.close()
        store.close()


def test_archiving_preserves_evidence_pairs_and_case_timelines(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, config())
    client = runner.clients["client-1"]
    first = client.act(action("browse"))
    case = runner.clients["blue-monitor"].act(action("open_case", evidence_ids=[first["event_id"]]))
    for _ in range(110):
        client.act(action("browse"))
    store.archive(100, 1000000)
    archive = next((tmp_path / "sealed-archives").glob("*.gz"))
    rows = [json.loads(x) for x in gzip.decompress(archive.read_bytes()).decode().splitlines()]
    assert rows[0]["id"] == first["event_id"]
    assert "effect" in rows[0]
    timeline = runner.clients["blue-dfir"].act(action("investigate", case_id=case["case_id"]))
    assert timeline["timeline"][0]["event_id"] == first["event_id"]
    runner.close()
    store.close()


def test_archive_budget_fails_without_discarding_events(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, config())
    for _ in range(105):
        runner.clients["client-1"].act(action("browse"))
    with pytest.raises(OSError, match="budget"):
        store.archive(100, 1)
    assert len(store.events(through_tick=0, limit=200)) == 105
    runner.close()
    store.close()


def test_cli_refuses_llm_without_budget_and_can_init_stop_resume(tmp_path):
    cli_runner = CliRunner()
    path = str(tmp_path / "w")
    result = cli_runner.invoke(cli, ["world", "run", "--out", path, "--llm"])
    assert result.exit_code != 0 and "call-budget" in result.output
    assert not (tmp_path / "w").exists()
    result = cli_runner.invoke(
        cli, ["world", "init", "--out", path, "--clients", "1", "--tick-seconds", "0.01"]
    )
    assert result.exit_code == 0, result.output
    assert cli_runner.invoke(cli, ["world", "stop", "--out", path]).exit_code == 0
    blocked = cli_runner.invoke(cli, ["world", "run", "--out", path, "--ticks", "1"])
    assert blocked.exit_code != 0 and "STOP" in blocked.output
    result = cli_runner.invoke(cli, ["world", "run", "--out", path, "--ticks", "1", "--resume"])
    assert result.exit_code == 0, result.output
    assert cli_runner.invoke(cli, ["world", "status", "--out", path]).exit_code == 0


def test_supervisor_restarts_only_failures_and_honors_stop(tmp_path, monkeypatch):
    from saber.world.supervisor import supervise

    attempts = []

    class Child:
        def __init__(self, argv):
            attempts.append(argv)

        def wait(self):
            return 1 if len(attempts) == 1 else 0

    monkeypatch.setattr("saber.world.supervisor.subprocess.Popen", Child)
    assert supervise(tmp_path, [], backoff=0) == 0
    assert len(attempts) == 2
    assert attempts[0][-1] == "--forever"
    (tmp_path / "STOP").write_text("stop")
    assert supervise(tmp_path, [], backoff=0) == 0
    assert len(attempts) == 2


def test_supervisor_bounds_repeated_failure(tmp_path, monkeypatch):
    from saber.world.supervisor import supervise

    attempts = []

    class Child:
        def __init__(self, argv):
            attempts.append(argv)

        def wait(self):
            return 2

    monkeypatch.setattr("saber.world.supervisor.subprocess.Popen", Child)
    assert supervise(tmp_path, [], max_restarts=2, backoff=0) == 2
    assert len(attempts) == 3


def test_cli_supervisor_forwards_llm_options(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        "saber.world.supervisor.supervise", lambda out, args, **kw: seen.append(args) or 0
    )
    result = CliRunner().invoke(
        cli, ["world", "supervise", "--out", str(tmp_path), "--llm", "--call-budget", "20"]
    )
    assert result.exit_code == 0, result.output
    assert seen == [["--llm", "--call-budget", "20"]]


def test_disk_budget_stops_without_losing_checkpoint(tmp_path):
    cfg = config().model_copy(update={"disk_budget_bytes": 1_000_000})
    store = Store(tmp_path)
    runner = Runner(store, cfg)
    (tmp_path / "large-fixture").write_bytes(b"x" * 1_000_000)
    result = runner.run(ticks=3)
    assert result["stop_reason"] == "disk_budget"
    assert result["tick"] == 0
    store.close()
