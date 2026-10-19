"""Offline tests for the Phase C baseline runners (no network, no live CLI)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from saber.baselines import claude_cli
from saber.baselines.claude_cli import CliInvocation, run_claude_cli, subscription_env
from saber.baselines.claude_cli import CliInvocation as _Inv
from saber.baselines.pilot_runner import (
    _summarize_llm,
    evidence_grounding,
    run_baselines,
    write_report,
)
from saber.baselines.prompt import build_prompt, extract_answer_json
from saber.baselines.rules import naive_answer
from saber.baselines.strong import strong_answer
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
        "claude-haiku-4-5-20251001": {
            "outputTokens": 11,
            "canonicalModel": "claude-haiku-4-5",
            "provider": "firstParty",
            "costBasis": "list",
        }
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


def test_fp_fn_counting_no_double_count() -> None:
    from saber.baselines.pilot_runner import (
        _count_one,
        _false_negative_count,
        _false_positive_count,
    )

    # A set scorer exposes BOTH an int (fn) and the element list (missed); count once, not twice.
    comp = {"detail": {"fn": 2, "missed": ["a", "b"], "fp": 1, "false_positives": ["x"]}}
    assert _false_negative_count([comp]) == 2  # not 2 + len([a,b]) = 4
    assert _false_positive_count([comp]) == 1  # not 1 + len([x]) = 2
    assert _count_one({"extra": ["a", "b", "c"]}, ("fp", "extra")) == 3  # list len when no int
    assert _false_negative_count([{"detail": {}}]) is None  # not exposed -> None, not 0


def test_strong_baseline_dominates_naive_and_reaches_oracle() -> None:
    # The conventional (non-LLM) baseline must use public inputs only, beat (or match) the naive
    # floor on every pilot, and never exceed the oracle.
    for sid in pilot_ids():
        pilot = load_pilot(sid)
        for seed in (1, 2):
            ep = pilot.build("dev", seed)
            strong = pilot.grade(ep, strong_answer(sid, ep), agent_id="strong").score
            naive = pilot.grade(ep, naive_answer(sid, ep), agent_id="naive").score
            assert strong >= naive - 1e-9, f"{sid} seed {seed}: strong {strong} < naive {naive}"
            assert strong <= 1.0 + 1e-9


def test_rules_mean_leaves_headroom() -> None:
    report = run_baselines(split="dev", seeds=[1, 2], use_llm=False)
    s = report["summary"]
    assert s["oracle"]["mean"] == 1.0
    assert s["rules"]["mean"] < 0.6
    assert s["oracle_minus_rules"]["mean"] > 0.3
    assert s["oracle_minus_rules"]["ci95_cluster"] is not None  # cluster bootstrap CI present
    assert len(s["by_seed"]) == 2  # per-seed variability recorded
    assert "llm" not in report["episodes"][0]
    assert s["n_pilots"] == 12 and s["n_episodes"] == 24


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


class _FakePopen:
    """Minimal stand-in for subprocess.Popen used to drive run_claude_cli deterministically."""

    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0, timeout: bool = False):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = 4242
        self._timeout = timeout
        self._calls = 0

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self._calls += 1
        if self._timeout and self._calls == 1:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout or 0)
        return self._stdout, self._stderr

    def kill(self) -> None:  # pragma: no cover - fallback path
        pass


def test_run_claude_cli_parses_envelope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import json as _json

    captured: dict[str, Any] = {}

    def fake_popen(argv: list[str], **kwargs: Any) -> _FakePopen:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _FakePopen(_json.dumps(ENVELOPE))

    monkeypatch.setattr(claude_cli.subprocess, "Popen", fake_popen)
    exe = str(tmp_path / "claude")  # outside cwd, so the resolver accepts it
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: exe)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    inv = run_claude_cli("prompt", model="haiku", cwd="somedir")
    assert "--disallowed-tools" in captured["argv"]
    assert "--strict-mcp-config" in captured["argv"]  # no operator MCP servers load
    assert captured["kwargs"]["cwd"] == "somedir"
    assert "ANTHROPIC_API_KEY" not in captured["kwargs"]["env"]
    assert inv.ok and not inv.is_error
    assert inv.result_text == '{"ok": true}'
    assert inv.model_used == "claude-haiku-4-5"
    assert inv.provider == "firstParty" and inv.cost_basis == "list"
    assert inv.duration_ms == 1234
    assert inv.tool_failures() == 0


def test_run_claude_cli_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        claude_cli.subprocess, "Popen", lambda *a, **k: _FakePopen("", timeout=True)
    )
    monkeypatch.setattr(claude_cli, "_terminate_tree", lambda _proc: None)
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: str(tmp_path / "claude"))
    inv = run_claude_cli("p", model="haiku", cwd="d", timeout_s=1)
    assert not inv.ok and inv.timed_out and inv.tool_failures() == 1
    assert inv.error_detail is not None and "process tree killed" in inv.error_detail


def test_run_claude_cli_missing_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: None)
    inv = run_claude_cli("p", model="haiku", cwd="d")
    assert not inv.ok and inv.error_detail is not None and "not found" in inv.error_detail


def test_run_claude_cli_rejects_executable_in_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    # A planted ./claude (resolved inside the current directory) must be refused.
    planted = str(Path.cwd() / "claude")
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: planted)
    inv = run_claude_cli("p", model="haiku", cwd="d")
    assert not inv.ok and inv.error_detail is not None
    assert "working directory" in inv.error_detail


def test_non_json_stdout_is_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        claude_cli.subprocess,
        "Popen",
        lambda *a, **k: _FakePopen("not json", stderr="boom", returncode=1),
    )
    monkeypatch.setattr(claude_cli.shutil, "which", lambda _: str(tmp_path / "claude"))
    inv = run_claude_cli("p", model="haiku", cwd="d")
    assert not inv.ok and inv.error_detail is not None and "non-JSON" in inv.error_detail


def test_summarize_llm_is_error_not_completed() -> None:
    pilot = load_pilot("T1112.002")
    ep = pilot.build("dev", 1)
    inv = _Inv(ok=True, requested_model="haiku", result_text='{"verdict": "TP"}', is_error=True)
    llm = _summarize_llm(pilot, ep, inv, 100)
    assert llm["completed"] is False  # is_error must not count as a completed episode


def test_report_components_carry_no_truth(tmp_path: Path) -> None:
    report = run_baselines(["T1112.002", "T0167.002"], split="dev", seed=1, use_llm=False)
    truth_keys = {"truth", "missed", "matched", "gold", "expected"}
    for ep in report["episodes"]:
        for comp in ep["rules"]["components"]:
            detail = comp["detail"]
            assert truth_keys.isdisjoint(detail.keys())
            assert all(isinstance(v, (int, float, bool, str)) for v in detail.values())


def test_write_report_refuses_hidden_split() -> None:
    report = run_baselines(["T0020.001"], split="hidden", seed=1, use_llm=False)
    with pytest.raises(ValueError, match="hidden"):
        write_report(report)


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
    assert "Per-pilot" in md and "T0020.001" in md


def test_envelope_contract_fields_present() -> None:
    inv = CliInvocation(ok=True, requested_model="haiku", result_text="x", permission_denials=["d"])
    assert inv.tool_failures() == 1  # one denial
