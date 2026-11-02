"""Real subprocess, loopback DNS/TCP and file evidence; no Gemini or Docker needed."""

import hashlib
import json
import os

import pytest
from click.testing import CliRunner

from saber.cli.main import cli
from saber.world.models import Action, Actor, WorldConfig
from saber.world.native import read_events
from saber.world.runtime import Runner
from saber.world.store import Store


def config():
    return WorldConfig(
        execution_mode="native",
        tick_seconds=0.01,
        red_start_tick=1,
        actors=[
            Actor(id="client-1", team="client", role="employee"),
            Actor(id="red-recon", team="red", role="recon"),
            Actor(id="blue-monitor", team="blue", role="monitor"),
        ],
    )


def test_actual_process_dns_tcp_file_evidence_and_blue_boundary(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, config())
    try:
        runner.run(ticks=2)
        rows = read_events(store, through_tick=2)
        assert len(rows) == 6 * 7
        assert {r["actor_id"] for r in rows} == {a.id for a in config().actors}
        assert all(r["pid"] > 0 and r["pid"] != os.getpid() for r in rows)
        assert {r["event_id"] for r in rows} == {1, 2, 3, 4, 5, 6}
        for actor in config().actors:
            own = read_events(store, actor_id=actor.id, through_tick=2)
            assert len(own) == 14
            assert len(read_events(store, actor_id=actor.id, through_tick=1)) == 7
            capture = own[-7:]
            assert [r["kind"] for r in capture] == [
                "process.start",
                "dns.response",
                "network.connect",
                "http.response",
                "file.write",
                "file.read",
                "process.exit",
            ]
            assert len({r["capture_id"] for r in capture}) == 1
            assert capture[1]["data"]["answer"] == "127.0.0.1"
            assert capture[2]["data"]["remote"].startswith("127.0.0.1:")
            assert capture[-1]["data"]["exit_code"] == 0
            receipt = tmp_path / "workloads" / actor.id / "last-action.json"
            assert hashlib.sha256(receipt.read_bytes()).hexdigest() == capture[-2]["data"]["sha256"]
        public = (tmp_path / "native.jsonl").read_text()
        for secret in runner.server._by_actor.values():
            assert secret not in public
        observation = runner.world.observe(config().actors[-1])
        assert "native_telemetry" in observation
        assert "red-recon" not in json.dumps(observation["native_telemetry"])
        assert "native_telemetry" not in runner.world.observe(config().actors[0])
        page = read_events(store, through_tick=2, limit=7)
        older = read_events(store, through_tick=2, limit=7, before=page[0]["id"])
        assert older[-1]["id"] < page[0]["id"]
        output = CliRunner().invoke(
            cli,
            ["world", "native-logs", "--out", str(tmp_path), "--actor", "client-1", "--limit", "7"],
        )
        assert output.exit_code == 0, output.output
        assert len(output.output.splitlines()) == 7
    finally:
        runner.close()
        store.close()


def test_denied_action_still_has_http_and_os_evidence_without_payload(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, config())
    try:
        result = runner.server.native_act(
            runner.native,
            "client-1",
            0,
            Action(tool="disrupt", args={"password": "SECRET_SENTINEL"}),
        )
        assert result["status"] == 403
        rows = read_events(store, through_tick=0)
        assert next(r for r in rows if r["kind"] == "http.response")["data"]["status"] == 403
        assert "SECRET_SENTINEL" not in json.dumps(rows)
        assert rows[-1]["data"]["exit_code"] == 0  # worker completed; action was denied
    finally:
        runner.close()
        store.close()


def test_transport_failure_is_logged_without_retry_or_success(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, config())
    try:
        runner.server.close()
        with pytest.raises(RuntimeError, match="not retried"):
            runner.server.native_act(runner.native, "client-1", 0, Action(tool="browse"))
        rows = read_events(store, through_tick=0)
        assert rows[-1]["data"]["exit_code"] != 0
        assert rows[-1]["data"]["error"] == "ConnectionRefusedError"
        assert all(r["event_id"] is None for r in rows)
        assert not any(
            r["kind"] in ("network.connect", "file.write", "http.response") for r in rows
        )
    finally:
        runner.close()
        store.close()


def test_disk_failure_preserves_applied_event_and_is_not_retried(tmp_path):
    store = Store(tmp_path)
    runner = Runner(store, config())
    try:
        # A directory at the fixed artifact name makes the real OS write fail.
        (tmp_path / "workloads" / "client-1" / "last-action.json").mkdir(parents=True)
        with pytest.raises(RuntimeError, match="not retried"):
            runner.server.native_act(runner.native, "client-1", 0, Action(tool="browse"))
        rows = read_events(store, through_tick=0)
        assert {r["event_id"] for r in rows} == {1}
        assert len(store.events(through_tick=0)) == 1
        assert rows[-1]["data"]["exit_code"] != 0
        assert not any(r["kind"] == "file.write" for r in rows)
    finally:
        runner.close()
        store.close()
