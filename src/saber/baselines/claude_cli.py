"""Controlled Claude Code CLI baseline runner (``claude -p``), subscription-only.

Design constraints (Phase C):

* **Subscription auth only.** The child environment has every API-key / alternate-
  provider variable removed, so the CLI uses the operator's claude.ai login or
  fails loudly. It can never silently switch to pay-as-you-go API billing.
* **No benchmark contamination.** The child runs in a caller-provided *empty* working
  directory with all filesystem / shell / network / search tools disallowed, so the
  model cannot read the pilot source or the sealed gold truth, and max-turns is
  bounded (default 1: a single answer, no tool loop).
* **Fail-safe parsing.** A timeout, a non-zero exit, or non-JSON stdout is captured as
  a structured failure, never raised. Latency, usage, model identity and permission
  denials are recorded for every call.

Cost figures reported by the CLI are LIST-price estimates and are informational only;
under subscription auth no pay-as-you-go charge is incurred.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

# Everything with a side effect or that could read the repo / sealed truth. The model
# gets none of these, so a gold episode must be solved purely from the prompt text.
DEFAULT_DISALLOWED_TOOLS: tuple[str, ...] = (
    "Bash",
    "Edit",
    "Write",
    "MultiEdit",
    "NotebookEdit",
    "Read",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "Task",
    "TodoWrite",
    "KillShell",
)

# Environment variables that would route the CLI to a non-subscription provider or a
# raw API key. Removed from the child environment so subscription auth is the only path.
_SCRUBBED_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
)


@dataclass
class CliInvocation:
    """Structured outcome of one ``claude -p`` call (never raises on model failure)."""

    ok: bool  # a parseable success envelope was returned (is_error may still be True)
    requested_model: str
    result_text: str = ""  # raw model output (the envelope's "result")
    is_error: bool = False
    model_used: str | None = None  # canonical model observed in modelUsage
    num_turns: int | None = None
    duration_ms: int | None = None
    total_cost_usd: float | None = None  # LIST price, informational (subscription auth)
    permission_denials: list[Any] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False
    returncode: int | None = None
    error_detail: str | None = None

    def tool_failures(self) -> int:
        """Count of signals that the call did not cleanly answer (denials, error, timeout)."""
        n = len(self.permission_denials)
        if self.is_error:
            n += 1
        if self.timed_out:
            n += 1
        return n


def subscription_env() -> dict[str, str]:
    """A copy of the environment with API-key / alternate-provider variables removed."""
    env = dict(os.environ)
    for key in _SCRUBBED_ENV_KEYS:
        env.pop(key, None)
    return env


def _primary_model(model_usage: dict[str, Any]) -> str | None:
    """The canonical model that produced the answer (most output tokens wins)."""
    best: str | None = None
    best_out = -1
    for mid, info in model_usage.items():
        out = int(info.get("outputTokens", 0)) if isinstance(info, dict) else 0
        if out > best_out:
            best_out = out
            canonical = info.get("canonicalModel") if isinstance(info, dict) else None
            best = str(canonical or mid)
    return best


def run_claude_cli(
    prompt: str,
    *,
    model: str,
    cwd: str,
    max_turns: int = 1,
    timeout_s: float = 120.0,
    disallowed_tools: tuple[str, ...] = DEFAULT_DISALLOWED_TOOLS,
    executable: str | None = None,
) -> CliInvocation:
    """Invoke ``claude -p`` once and return a structured, fail-safe result.

    ``cwd`` must be an existing, empty-ish directory that is NOT the repo root, so the
    model cannot read pilot source or sealed truth even if it attempted a file tool.
    """
    exe = executable or shutil.which("claude")
    if exe is None:
        return CliInvocation(
            ok=False,
            requested_model=model,
            error_detail="claude CLI not found on PATH (Phase C LLM baseline unavailable)",
        )
    argv = [
        exe,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--max-turns",
        str(max_turns),
        "--disallowed-tools",
        *disallowed_tools,
        "--model",
        model,
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - argv is fully constructed, no shell
            argv,
            input="",
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=subscription_env(),
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CliInvocation(
            ok=False,
            requested_model=model,
            timed_out=True,
            error_detail=f"claude CLI timed out after {timeout_s:.0f}s",
        )
    except OSError as exc:  # pragma: no cover - environment dependent
        return CliInvocation(
            ok=False, requested_model=model, error_detail=f"failed to launch claude: {exc}"
        )

    stdout = proc.stdout or ""
    try:
        env_json = json.loads(stdout)
    except json.JSONDecodeError:
        tail = (proc.stderr or "")[-400:]
        return CliInvocation(
            ok=False,
            requested_model=model,
            returncode=proc.returncode,
            error_detail=f"non-JSON stdout (rc={proc.returncode}); stderr tail: {tail}",
        )
    if not isinstance(env_json, dict):
        return CliInvocation(
            ok=False,
            requested_model=model,
            returncode=proc.returncode,
            error_detail="unexpected JSON shape (not an object)",
        )

    model_usage = env_json.get("modelUsage")
    model_usage = model_usage if isinstance(model_usage, dict) else {}
    usage = env_json.get("usage")
    denials = env_json.get("permission_denials")
    return CliInvocation(
        ok=True,
        requested_model=model,
        result_text=str(env_json.get("result", "")),
        is_error=bool(env_json.get("is_error", False)),
        model_used=_primary_model(model_usage),
        num_turns=env_json.get("num_turns"),
        duration_ms=env_json.get("duration_ms"),
        total_cost_usd=env_json.get("total_cost_usd"),
        permission_denials=list(denials) if isinstance(denials, list) else [],
        usage=usage if isinstance(usage, dict) else {},
        returncode=proc.returncode,
    )
