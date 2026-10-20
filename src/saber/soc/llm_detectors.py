"""LLM-backed detector configurations for the G3 multi-agent evaluation (web_sqli_probe).

Each config turns the live access log into a detection regex via the subscription CLI, then the regex
is run (sandboxed) over the real log to get matched lines. Configs are designed for a clean
call-budget-matched ablation that isolates COORDINATION from COMPUTE:

* ``single``            — 1 call.
* ``specialist``        — 1 call, SOC-analyst role prompt.
* ``multi_agent``       — 2 calls: analyst draft -> reviewer corrects (coordination).
* ``budget_single``     — 2 calls: analyst draft -> the SAME agent self-refines (no second role).
* ``multi_no_reviewer`` — 2 calls: two independent analyst drafts, ensembled (OR), no reviewer.

Comparing multi_agent vs budget_single vs multi_no_reviewer (all 2 calls) tests whether the reviewer
earns its extra call. All calls reuse the isolated-cwd, tools-disallowed, env-scrubbed CLI runner.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from saber.baselines.claude_cli import CliInvocation, run_claude_cli
from saber.baselines.prompt import extract_answer_json
from saber.grading.execsandbox import run_regex_rule

if TYPE_CHECKING:
    from saber.range.live.episode import LiveEpisode

_OUT = '{"rule": {"engine": "regex", "pattern": "<regex>", "ignore_case": true}}'


def _analyst_prompt(log: list[str], *, specialist: bool) -> str:
    role = (
        "You are a specialized SOC web-attack detection analyst. "
        if specialist
        else "You are a SOC detection engineer. "
    )
    return (
        f"{role}Below is a REAL web access log (one JSON record per line) from a live service. "
        "Some requests are SQL-injection probes; many benign requests merely contain a SQL word.\n\n"
        f"ACCESS LOG:\n{chr(10).join(log)}\n\n"
        f"Write ONE Python regex matching the SQL-injection lines and NOT the benign ones. "
        f"Respond with ONLY this JSON, no commentary:\n{_OUT}"
    )


def _reviewer_prompt(log: list[str], draft: dict[str, Any]) -> str:
    return (
        "You are a senior detection REVIEWER. Improve the analyst's regex to cut false positives "
        "(benign SQL-word lines) and false negatives (missed probes).\n\n"
        f"ACCESS LOG:\n{chr(10).join(log)}\n\nDRAFT: {json.dumps(draft)}\n\n"
        f"Return ONLY the corrected JSON:\n{_OUT}"
    )


def _selfrefine_prompt(log: list[str], draft: dict[str, Any]) -> str:
    return (
        "You are a SOC detection engineer. Here is YOUR OWN draft regex. Critique it yourself and "
        "return an improved version that reduces false positives and false negatives.\n\n"
        f"ACCESS LOG:\n{chr(10).join(log)}\n\nYOUR DRAFT: {json.dumps(draft)}\n\n"
        f"Return ONLY the improved JSON:\n{_OUT}"
    )


def _call(
    prompt: str, *, model: str, timeout_s: float
) -> tuple[dict[str, Any] | None, CliInvocation]:
    tmp = tempfile.mkdtemp(prefix="saber-soc-agent-")
    try:
        inv = run_claude_cli(prompt, model=model, cwd=tmp, timeout_s=timeout_s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return (extract_answer_json(inv.result_text)[0] if inv.ok else None), inv


def _pattern(ans: dict[str, Any] | None) -> tuple[str, bool]:
    rule = (ans or {}).get("rule") or {}
    p = rule.get("pattern")
    return (p if isinstance(p, str) else ""), bool(rule.get("ignore_case", True))


def _matched(episode: LiveEpisode, pattern: str, ignore_case: bool) -> list[str]:
    res = run_regex_rule(pattern, episode.access_log_lines, ignore_case=ignore_case)
    if not res.parse_ok or res.timed_out:
        return []
    return sorted((f"line-{i}" for i in res.matched), key=lambda s: int(s.split("-")[1]))


def make_detector(
    mode: str, *, model: str, timeout_s: float
) -> Callable[[LiveEpisode], dict[str, Any]]:
    """Return a detector(episode)->{pattern, matched_line_ids, calls, completed, wall_ms, cost}."""

    def detector(episode: LiveEpisode) -> dict[str, Any]:
        log = episode.access_log_lines
        t0 = time.monotonic()
        calls: list[CliInvocation] = []
        if mode in ("single", "specialist"):
            ans, inv = _call(
                _analyst_prompt(log, specialist=(mode == "specialist")),
                model=model,
                timeout_s=timeout_s,
            )
            calls.append(inv)
        elif mode == "multi_agent":
            draft, inv1 = _call(
                _analyst_prompt(log, specialist=True), model=model, timeout_s=timeout_s
            )
            calls.append(inv1)
            ans = draft
            if draft is not None:
                rev, inv2 = _call(_reviewer_prompt(log, draft), model=model, timeout_s=timeout_s)
                calls.append(inv2)
                ans = rev if rev is not None else draft
        elif mode == "budget_single":
            draft, inv1 = _call(
                _analyst_prompt(log, specialist=False), model=model, timeout_s=timeout_s
            )
            calls.append(inv1)
            ans = draft
            if draft is not None:
                ref, inv2 = _call(_selfrefine_prompt(log, draft), model=model, timeout_s=timeout_s)
                calls.append(inv2)
                ans = ref if ref is not None else draft
        elif mode == "multi_no_reviewer":
            a1, inv1 = _call(
                _analyst_prompt(log, specialist=False), model=model, timeout_s=timeout_s
            )
            a2, inv2 = _call(
                _analyst_prompt(log, specialist=False), model=model, timeout_s=timeout_s
            )
            calls.extend([inv1, inv2])
            # ensemble without coordination: OR the two patterns (union of matches)
            p1, _ = _pattern(a1)
            p2, _ = _pattern(a2)
            parts = [p for p in (p1, p2) if p]
            ans = (
                {"rule": {"pattern": "|".join(f"(?:{p})" for p in parts), "ignore_case": True}}
                if parts
                else None
            )
        else:
            raise ValueError(f"unknown LLM mode {mode!r}")

        pattern, ic = _pattern(ans)
        completed = ans is not None and bool(pattern) and not calls[0].timed_out
        return {
            "mode": mode,
            "pattern": pattern,
            "ignore_case": ic,
            "matched_line_ids": _matched(episode, pattern, ic) if pattern else [],
            "completed": completed,
            "calls": [
                {
                    "timed_out": c.timed_out,
                    "is_error": c.is_error,
                    "duration_ms": c.duration_ms,
                    "cost": c.total_cost_usd,
                    "model": c.model_used,
                }
                for c in calls
            ],
            "n_calls": len(calls),
            "tool_failures": sum(c.tool_failures() for c in calls),
            "wall_ms": int((time.monotonic() - t0) * 1000),
            "cost_usd_listprice": round(sum(c.total_cost_usd or 0.0 for c in calls), 6),
        }

    return detector
