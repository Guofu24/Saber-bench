"""Offline tests for the Phase C baseline runners (no network, no live CLI)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from saber.baselines import claude_cli
from saber.baselines.claude_cli import CliInvocation, run_claude_cli, subscription_env
from saber.baselines.pilot_runner import (
    evidence_grounding,
    run_baselines,
    write_report,
)
from saber.baselines.prompt import build_prompt, extract_answer_json
from saber.baselines.rules import naive_answer
from saber.gold.base import load_pilot, pilot_ids

ENVELOPE = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": '{"ok": true}',
    "num_turns": 1,
    "duration_ms": 1234,
    "total_cost_usd": 0.001,
    "permission_denials": [],
    "usage": {"input_tokens": 10},
    "modelUsage": {
        "claude-haiku-4-5-20251001": {"outputTokens": 11, "canonicalModel": "claude-haiku-4-5"}
    },
}


def test_rules_baseline_discriminates_on_every_pilot() -> None:
    for sid in pilot_ids():
        pilot = load_pilot(sid)
        ep = pilot.build("dev", 1)
        oracle = pilot.grade(ep, pilot.answer_from_gold(ep), agent_id="oracle").score
        rules = pilot.grade(ep, naive_answer(sid, ep), agent_id="rules").score
        assert abs(oracle - 1.0) < 1e-9, f"{sid} oracle should be full credit"
        assert 0.0 <= rules < 1.0, f"{sid} naive rules must score below oracle, got {rules}"


def test_rules_mean_leaves_headroom() -> None:
    report = run_baselines(split="dev", seed=1, use_llm=False)
    s = report["summary"]
    assert s["oracle_mean"] == 1.0
    assert s["rules_mean"] < 0.6
    assert s["oracle_minus_rules"] > 0.3
    assert "llm" not in report["episodes"][0]
    assert report["summary"]["n"] == 12


@pytest.mark.parametrize(
    ("text", "expect_keys", "note_contains"),
    [
        ('{"a": 1}', ["a"], "whole"),
        ('```json\n{"a": 1}\n```', ["a"], "whole"),
        ('Here is my answer:\n{"a": 1, "b": 2}\nDone.', ["a", "b"], "first JSON object"),
        ("no json here", None, "no JSON"),
        ("", None, "empty"),
        ('{"a": [1, 2', None, "no JSON"),
        ("{not valid json}", None, "invalid"),
    ],
)
def test_extract_answer_json(text: str, expect_keys: list[str] | None, note_contains: str) -> None:
    obj, note = extract_answer_json(text)
    if expect_keys is None:
        assert obj is None
    else:
        assert obj is not None
        assert sorted(obj.keys()) == sorted(expect_keys)
    assert note_contains in note


def test_extract_handles_strings_with_braces() -> None:
    obj, _ = extract_answer_json('{"pattern": "a{2}b", "note": "has } brace"}')
    assert obj == {"pattern": "a{2}b", "note": "has } brace"}


def test_build_prompt_contains_spec_and_no_truth() -> None:
    pilot = load_pilot("T1102.002")
    ep = pilot.build("dev", 1)
    prompt = build_prompt(pilot, ep)
    assert pilot.OUTPUT_SPEC in prompt
    assert "JSON object and nothing else" in prompt
    # The sealed truth list must not leak into the prompt verbatim.
    assert str(ep.gold_truth["compromised"]) not in prompt


def test_subscription_env_scrubs_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-removed")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    env = subscription_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "CLAUDE_CODE_USE_BEDROCK" not in env


def test_run_claude_cli_parses_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as _json

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert "--disallowed-tools" in argv
        assert "--output-format" in argv and "json" in argv
        assert kwargs["cwd"] == "somedir"
        assert "ANTHROPIC_API_KEY" not in kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, stdout=_json.dumps(ENVELOPE), stderr="")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    inv = run_claude_cli("prompt", model="haiku", cwd="somedir")
    assert inv.ok and not inv.is_error
    assert inv.result_text == '{"ok": true}'
    assert inv.model_used == "claude-haiku-4-5"
    assert inv.duration_ms == 1234
    assert inv.tool_failures() == 0


def test_run_claude_cli_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(claude_cli.subprocess, "run", boom)
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: "claude")
    inv = run_claude_cli("p", model="haiku", cwd="d", timeout_s=1)
    assert not inv.ok and inv.timed_out and inv.tool_failures() == 1


def test_run_claude_cli_missing_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: None)
    inv = run_claude_cli("p", model="haiku", cwd="d")
    assert not inv.ok and inv.error_detail is not None and "not found" in inv.error_detail


def test_non_json_stdout_is_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **_k: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, stdout="not json", stderr="boom")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: "claude")
    inv = run_claude_cli("p", model="haiku", cwd="d")
    assert not inv.ok and inv.error_detail is not None and "non-JSON" in inv.error_detail


def test_evidence_grounding_flags_hallucination() -> None:
    pilot = load_pilot("T1102.002")
    ep = pilot.build("dev", 1)
    real = ep.gold_truth["compromised"][0]
    answer = {"compromised": [real, "ws-totally-made-up-9999"]}
    g = evidence_grounding(ep, answer)
    assert g["checked"] >= 1
    assert g["fraction"] is not None and g["fraction"] < 1.0
    assert any("made-up" in h for h in g["hallucinated"])


def test_evidence_grounding_clean_for_naive() -> None:
    pilot = load_pilot("T0397.002")
    ep = pilot.build("dev", 1)
    g = evidence_grounding(ep, naive_answer("T0397.002", ep))
    assert g["fraction"] == 1.0  # naive copies real locations; no hallucination


def test_write_report(tmp_path: Path) -> None:
    report = run_baselines(["T0020.001", "T1102.002"], split="dev", seed=1, use_llm=False)
    jpath, mpath = write_report(report, tmp_path)
    assert jpath.exists() and mpath.exists()
    md = mpath.read_text(encoding="utf-8")
    assert "Per-episode" in md and "T0020.001" in md


def test_envelope_contract_fields_present() -> None:
    inv = CliInvocation(ok=True, requested_model="haiku", result_text="x", permission_denials=["d"])
    assert inv.tool_failures() == 1  # one denial
