"""Offline tests for the E2 agent orchestration and four-way comparison (no network)."""

from __future__ import annotations

from typing import Any

import pytest

from saber.baselines import agents
from saber.baselines.agents import run_mode
from saber.baselines.claude_cli import CliInvocation
from saber.baselines.compare import run_comparison
from saber.gold.base import load_pilot


def _fake_inv(
    result: str = '{"verdict": "TP", "triggering_rule": "r", "affected_asset": "h"}',
) -> CliInvocation:
    return CliInvocation(
        ok=True,
        requested_model="haiku",
        result_text=result,
        model_used="claude-haiku-4-5",
        provider="firstParty",
        cost_basis="list",
        duration_ms=1000,
        num_turns=1,
    )


def test_run_comparison_offline_deterministic() -> None:
    report = run_comparison(["T0020.001", "T1102.002"], split="dev", seeds=[1], use_llm=False)
    assert report["baselines"] == ["oracle", "naive", "strong"]
    s = report["summary"]
    assert s["oracle"]["score"]["mean"] == 1.0
    assert s["strong"]["score"]["mean"] == 1.0
    assert s["naive"]["score"]["mean"] <= s["strong"]["score"]["mean"]
    assert isinstance(s["naive"]["fp_total"], int) and isinstance(s["naive"]["fn_total"], int)
    assert "single" not in report["baselines"]  # use_llm=False


def test_run_mode_single_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "run_claude_cli", lambda *a, **k: _fake_inv())
    pilot = load_pilot("T1112.002")
    ep = pilot.build("dev", 1)
    out = run_mode("single", pilot, ep, model="haiku", timeout_s=5)
    assert out["completed"] and out["n_calls"] == 1
    assert out["answer"]["verdict"] == "TP"
    assert out["model_used"] == "claude-haiku-4-5"


def test_run_mode_multi_agent_two_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "run_claude_cli", lambda *a, **k: _fake_inv())
    pilot = load_pilot("T1112.002")
    ep = pilot.build("dev", 1)
    out = run_mode("multi_agent", pilot, ep, model="haiku", timeout_s=5)
    assert out["completed"] and out["n_calls"] == 2  # analyst + reviewer


def test_run_mode_multi_agent_falls_back_on_bad_reviewer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def flaky(*_a: Any, **_k: Any) -> CliInvocation:
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_inv()  # analyst draft OK
        return CliInvocation(ok=True, requested_model="haiku", result_text="not json")

    monkeypatch.setattr(agents, "run_claude_cli", flaky)
    pilot = load_pilot("T1112.002")
    ep = pilot.build("dev", 1)
    out = run_mode("multi_agent", pilot, ep, model="haiku", timeout_s=5)
    assert out["n_calls"] == 2 and out["completed"]  # keeps analyst draft when reviewer unparsable
    assert out["answer"]["verdict"] == "TP"


def test_multi_agent_reviewer_timeout_keeps_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def flaky(*_a: Any, **_k: Any) -> CliInvocation:
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_inv()  # analyst draft OK
        return CliInvocation(ok=False, requested_model="haiku", timed_out=True)  # reviewer timeout

    monkeypatch.setattr(agents, "run_claude_cli", flaky)
    pilot = load_pilot("T1112.002")
    ep = pilot.build("dev", 1)
    out = run_mode("multi_agent", pilot, ep, model="haiku", timeout_s=5)
    # A reviewer-call timeout must NOT discard a valid analyst draft (Finding 3 fix).
    assert out["completed"] is True and out["n_calls"] == 2
    assert out["answer"]["verdict"] == "TP"


def test_run_mode_timeout_not_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents,
        "run_claude_cli",
        lambda *a, **k: CliInvocation(ok=False, requested_model="haiku", timed_out=True),
    )
    pilot = load_pilot("T0020.001")
    ep = pilot.build("dev", 1)
    out = run_mode("single", pilot, ep, model="haiku", timeout_s=1)
    assert not out["completed"] and out["answer"] is None and out["tool_failures"] == 1
