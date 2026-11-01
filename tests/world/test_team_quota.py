"""Team isolation, sticky failover, durable cursors and trusted planner routing."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from click.testing import CliRunner

from saber.agents.gemini import KeyPool
from saber.agents.provider import LLMResponse
from saber.cli.main import cli
from saber.domain.errors import BudgetExceeded, IntegrationBlocked
from saber.world.key_layout import TeamKeyLayout
from saber.world.models import Actor
from saber.world.quota import TeamQuotaProvider
from saber.world.runtime import Planner
from saber.world.store import Store
from tests.world.test_quota import MESSAGES, ok


def layout():
    return TeamKeyLayout.from_pool(
        KeyPool(keys=[f"fake-{i}" for i in range(6)]), client_keys=2, red_keys=2
    )


def provider(store, send=ok, **kwargs):
    return TeamQuotaProvider(
        store,
        layout(),
        model="test",
        call_budget=kwargs.pop("call_budget", 100),
        rpm=kwargs.pop("rpm", 100),
        rpd=100,
        transport=send,
        **kwargs,
    )


def test_file_uses_exact_200_200_remainder_boundaries(tmp_path):
    path = tmp_path / "keys.txt"
    path.write_text(
        "\ufeff# header\n\n" + "\n".join(f"KEY{i}=fake-{i}" for i in range(603)), encoding="utf-8"
    )
    groups = TeamKeyLayout.from_file(path)
    assert groups.counts() == {"client": 200, "red": 200, "blue": 203}
    assert groups.pool.keys[groups.indices["client"][-1]] == "fake-199"
    assert groups.pool.keys[groups.indices["red"][0]] == "fake-200"
    assert groups.pool.keys[groups.indices["blue"][0]] == "fake-400"
    assert "fake-" not in repr(groups)


def test_duplicate_entries_are_rejected_without_silently_moving_boundaries(tmp_path):
    path = tmp_path / "keys.txt"
    path.write_text("secret-a\nsecret-b\nsecret-c\nsecret-d\nsecret-a\n")
    with pytest.raises(ValueError, match="Duplicate") as exc:
        TeamKeyLayout.from_file(path, client_keys=2, red_keys=2)
    assert "secret-a" not in str(exc.value)
    with pytest.raises(ValueError, match="at least 401"):
        TeamKeyLayout.from_pool(KeyPool(keys=[f"k{i}" for i in range(400)]))


def test_healthy_key_stays_active_and_local_quota_advances_only_own_queue(tmp_path):
    store = Store(tmp_path)
    seen = []

    def send(url, key, body):
        seen.append(key)
        return ok(url, key, body)

    p = provider(store, send, rpm=2)
    for team in ("client", "client", "client", "red", "blue"):
        p.generate_for(team, MESSAGES)
    assert seen == ["fake-0", "fake-0", "fake-1", "fake-2", "fake-4"]
    assert store.get("llm-pools", "client")["active_key"] == 2
    assert store.get("meta", "llm_usage")["by_team"]["client"]["successes"] == 3
    store.close()


def test_429_immediately_uses_next_key_in_same_team(tmp_path):
    store = Store(tmp_path)
    seen = []

    def send(url, key, body):
        seen.append(key)
        return (
            (429, {"error": {"details": [{"retryDelay": "600s"}]}})
            if key == "fake-0"
            else ok(url, key, body)
        )

    p = provider(store, send)
    assert p.generate_for("client", MESSAGES).text == "ok"
    assert seen == ["fake-0", "fake-1"]
    p.generate_for("red", MESSAGES)
    p.generate_for("blue", MESSAGES)
    assert seen == ["fake-0", "fake-1", "fake-2", "fake-4"]
    q = store.get("quota", p.providers["client"]._project(0, "fake-0") + "/test")
    assert q["disabled"] is False and q["cool_until"] >= q["day"][0] + 599
    store.close()


def test_team_exhaustion_never_borrows_keys_or_stops_other_teams(tmp_path):
    store = Store(tmp_path)
    seen = []

    def send(url, key, body):
        seen.append(key)
        return (429, {}) if key in ("fake-0", "fake-1") else ok(url, key, body)

    p = provider(store, send)
    with pytest.raises(IntegrationBlocked):
        p.generate_for("client", MESSAGES)
    assert seen == ["fake-0", "fake-1"]
    assert store.get("llm-pools", "client")["state"] == "waiting_for_quota"
    assert p.generate_for("red", MESSAGES).text == "ok"
    assert p.generate_for("blue", MESSAGES).text == "ok"
    assert seen[-2:] == ["fake-2", "fake-4"]
    store.close()


def test_active_cursor_and_cooldown_survive_restart_and_key_returns_after_reset(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("saber.world.quota.time.time", lambda: 1000.0)
    seen = []

    def first(url, key, body):
        seen.append(key)
        return (429, {}) if key == "fake-0" else ok(url, key, body)

    store = Store(tmp_path)
    provider(store, first).generate_for("client", MESSAGES)
    store.close()
    store = Store(tmp_path)

    def second(url, key, body):
        seen.append(key)
        return ok(url, key, body)

    p = provider(store, second)
    p.generate_for("client", MESSAGES)
    assert seen == ["fake-0", "fake-1", "fake-1"]
    monkeypatch.setattr("saber.world.quota.time.time", lambda: 1100.0)

    def third(url, key, body):
        seen.append(key)
        return (429, {}) if key == "fake-1" else ok(url, key, body)

    provider(store, third).generate_for("client", MESSAGES)
    assert seen[-2:] == ["fake-1", "fake-0"]
    store.close()


def test_failed_key_is_disabled_and_global_budget_still_limits_failover(tmp_path):
    store = Store(tmp_path)
    seen = []

    def send(url, key, body):
        seen.append(key)
        return (401, {})

    p = provider(store, send, call_budget=1)
    with pytest.raises(BudgetExceeded):
        p.generate_for("client", MESSAGES)
    assert seen == ["fake-0"]
    assert next(iter(store.items("quota").values()))["disabled"] is True
    with pytest.raises(BudgetExceeded):
        p.generate_for("blue", MESSAGES)
    assert store.get("meta", "llm_usage")["attempts"] == 1
    store.close()


def test_parallel_teams_share_global_budget_without_crossing_pool_boundaries(tmp_path):
    store = Store(tmp_path)
    seen = []

    def send(url, key, body):
        expected_team = body["contents"][0]["parts"][0]["text"]
        seen.append((expected_team, key))
        return ok(url, key, body)

    p = provider(store, send, call_budget=7)

    def call(team):
        try:
            return p.generate_for(team, [{"role": "user", "content": team}]).text
        except BudgetExceeded:
            return "budget"

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(call, ["client", "red", "blue"] * 5))
    assert results.count("ok") == 7
    for team, key in seen:
        assert int(key.split("-")[-1]) in layout().indices[team]
    usage = store.get("meta", "llm_usage")
    assert sum(x["attempts"] for x in usage["by_team"].values()) == usage["attempts"] == 7
    store.close()


def test_planner_routes_by_actor_team_not_prompt_and_stops_retry_on_shutdown(tmp_path):
    store = Store(tmp_path)
    seen = []
    stopping = threading.Event()

    class Spy(TeamQuotaProvider):
        def generate_for(self, team, messages, **kwargs):
            seen.append(team)
            return LLMResponse(
                text='{"actions":[{"tool":"share","args":{"text":"ok"}}]}',
                model_id="test",
                input_tokens=1,
                output_tokens=1,
            )

    p = Spy(store, layout(), model="test", call_budget=5, transport=ok)
    planner = Planner(p, actors=1, workers=1)
    try:
        planner.request(Actor(id="r", team="red", role="recon"), {"tick": 1, "team": "blue"})
        assert planner.results.get(timeout=3)[0] == "r"
        assert seen == ["red"]
    finally:
        planner.close()

    def send(url, key, body):
        stopping.set()
        return 429, {}

    with pytest.raises(IntegrationBlocked, match="stopping"):
        provider(store, send).generate_for("client", MESSAGES, should_stop=stopping.is_set)
    assert store.get("meta", "llm_usage")["attempts"] == 1
    store.close()


def test_router_does_not_allow_unscoped_generation(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(IntegrationBlocked, match="trusted actor team"):
        provider(store).generate(MESSAGES)
    assert store.get("meta", "llm_usage") is None
    assert "fake-" not in json.dumps(store.items("llm-pools"))
    store.close()


def test_cli_defaults_to_team_layout_without_network(tmp_path, monkeypatch):
    keys = tmp_path / "keys.txt"
    keys.write_text("\n".join(f"fake-{i}" for i in range(602)))
    captured = []

    class FakeRunner:
        server = type("Server", (), {"url": "http://127.0.0.1:1"})()

        def __init__(self, store, config, *, provider, emitter):
            captured.append(provider)

        def run(self, **kwargs):
            return {"stop_reason": "test"}

        def close(self):
            pass

    monkeypatch.setattr("saber.world.cli.Runner", FakeRunner)
    result = CliRunner().invoke(
        cli,
        [
            "world",
            "run",
            "--out",
            str(tmp_path / "w"),
            "--llm",
            "--key-pool",
            str(keys),
            "--call-budget",
            "100",
        ],
    )
    assert result.exit_code == 0, result.output
    assert isinstance(captured[0], TeamQuotaProvider)
    assert {t: len(p.indices) for t, p in captured[0].providers.items()} == {
        "client": 200,
        "red": 200,
        "blue": 202,
    }
    assert "fake-" not in result.output
