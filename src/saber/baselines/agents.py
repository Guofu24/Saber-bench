"""LLM SOC agent modes for the E2 comparison: single, specialized, and coordinated multi-agent.

All modes reuse the controlled subscription CLI runner (:func:`run_claude_cli`) — isolated empty
cwd, tools + MCP disallowed, bounded turns, API-key env scrubbed. They differ only in prompting and
orchestration:

* **single** — the plain one-shot prompt (``saber.baselines.prompt.build_prompt``).
* **specialist** — the one-shot prompt plus a service-specific analyst role (MON/CNT/HUNT/IR).
* **multi_agent** — a specialist analyst drafts an answer, then a senior reviewer critiques and
  returns a corrected final answer (two bounded calls). Falls back to the draft if the reviewer
  does not return parseable JSON.

Every call records its own invocation (latency, tool failures, model) for resource accounting.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from typing import TYPE_CHECKING, Any

from saber.baselines.claude_cli import CliInvocation, run_claude_cli
from saber.baselines.prompt import build_prompt, extract_answer_json
from saber.catalog.loader import default_catalog

if TYPE_CHECKING:
    from saber.gold.base import GoldEpisode, GoldPilot

SPECIALIST_PREAMBLE = {
    "MON": "You are a SOC monitoring & detection engineer. Triage the alert from the surrounding "
    "telemetry, name the firing rule, and identify the affected asset; do not trust a label field "
    "over the evidence.",
    "CNT": "You are a detection-content author. Write precise rules/signatures that catch the "
    "technique while avoiding false positives on benign look-alikes.",
    "HUNT": "You are a threat hunter. Enumerate every indicator/compromised host exhaustively, "
    "including hosts with only historical traces, and exclude benign distractors.",
    "IR": "You are an incident responder. Handle evidence in the correct order, normalise "
    "timestamps to UTC, and state preservation precisely.",
}


def _service(subtask_id: str) -> str:
    return default_catalog().subtask(subtask_id).service


def _call(
    prompt: str, *, model: str, timeout_s: float
) -> tuple[dict[str, Any] | None, CliInvocation, int]:
    """Run one bounded CLI call in an isolated cwd; return (parsed_answer_or_None, inv, wall_ms)."""
    tmp = tempfile.mkdtemp(prefix="saber-agent-")
    t0 = time.monotonic()
    try:
        inv = run_claude_cli(prompt, model=model, cwd=tmp, timeout_s=timeout_s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    wall_ms = int((time.monotonic() - t0) * 1000)
    answer = extract_answer_json(inv.result_text)[0] if inv.ok else None
    return answer, inv, wall_ms


def _specialist_prompt(pilot: GoldPilot, episode: GoldEpisode) -> str:
    preamble = SPECIALIST_PREAMBLE.get(_service(pilot.SUBTASK_ID), "")
    return f"{preamble}\n\n{build_prompt(pilot, episode)}"


def _reviewer_prompt(pilot: GoldPilot, episode: GoldEpisode, draft: dict[str, Any]) -> str:
    return (
        "You are a senior SOC reviewer doing QA on a junior analyst's answer. "
        f"Review it for errors: missed items, false positives, wrong normalisation, wrong verdict.\n\n"
        f"{build_prompt(pilot, episode)}\n\n"
        f"JUNIOR ANALYST DRAFT (JSON):\n{json.dumps(draft, ensure_ascii=False)}\n\n"
        "Return the CORRECTED final answer as a single JSON object matching the schema above, "
        "no commentary. If the draft is already correct, return it unchanged."
    )


def run_mode(
    mode: str, pilot: GoldPilot, episode: GoldEpisode, *, model: str, timeout_s: float
) -> dict[str, Any]:
    """Run one LLM mode and return {answer, calls:[inv-summaries], wall_ms, model_used, ...}."""
    calls: list[CliInvocation] = []
    wall = 0

    if mode == "single":
        prompt = build_prompt(pilot, episode)
    elif mode in ("specialist", "multi_agent"):
        prompt = _specialist_prompt(pilot, episode)
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    answer, inv, w = _call(prompt, model=model, timeout_s=timeout_s)
    calls.append(inv)
    wall += w

    analyst_timed_out = inv.timed_out
    if mode == "multi_agent" and answer is not None:
        final, rinv, w2 = _call(
            _reviewer_prompt(pilot, episode, answer), model=model, timeout_s=timeout_s
        )
        calls.append(rinv)
        wall += w2
        if final is not None:  # reviewer's corrected answer wins; else keep the valid draft
            answer = final

    # Completion depends on having a usable answer and the ANALYST call succeeding. A reviewer-call
    # timeout does not discard a valid draft (that confound would deflate multi_agent unfairly).
    completed = answer is not None and not analyst_timed_out
    return {
        "mode": mode,
        "answer": answer,
        "completed": completed,
        "n_calls": len(calls),
        "wall_ms": wall,
        "duration_ms": sum(c.duration_ms or 0 for c in calls) or None,
        "tool_failures": sum(c.tool_failures() for c in calls),
        "model_used": next((c.model_used for c in calls if c.model_used), None),
        "provider": next((c.provider for c in calls if c.provider), None),
        "cost_usd_listprice": round(sum(c.total_cost_usd or 0.0 for c in calls), 6),
        "parse_note": "ok" if answer is not None else (calls[0].error_detail or "no answer"),
    }
