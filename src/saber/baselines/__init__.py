"""Controlled baseline runners for the Gold Evaluation Pilot (Phase C).

Two baselines run on the SAME gold episodes:

* ``rules`` — a deterministic, non-LLM "first-pass analyst" heuristic per pilot
  (:mod:`saber.baselines.rules`). It is intentionally naive so the hard negatives
  bite; it is the discrimination FLOOR, not a reference solution.
* ``llm`` — a genuine Claude baseline invoked through the authenticated Claude Code
  CLI (``claude -p``) under claude.ai **subscription** auth
  (:mod:`saber.baselines.claude_cli`). The API-key environment is scrubbed so the
  runner can never silently fall back to pay-as-you-go API billing.

Nothing here promotes a subtask to READY_BENCHMARK. Results are labeled and are a
measurement of discrimination, not a validated comparative benchmark.
"""

from __future__ import annotations

from saber.baselines.claude_cli import CliInvocation, run_claude_cli
from saber.baselines.prompt import build_prompt, extract_answer_json
from saber.baselines.rules import naive_answer

__all__ = [
    "CliInvocation",
    "build_prompt",
    "extract_answer_json",
    "naive_answer",
    "run_claude_cli",
]
