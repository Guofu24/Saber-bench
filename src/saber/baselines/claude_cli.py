"""Controlled Claude Code CLI baseline runner (``claude -p``).

Design constraints (Phase C):

* **Does not itself introduce API billing.** The child environment has every API-key /
  alternate-provider variable removed (:data:`_SCRUBBED_ENV_KEYS`), so this runner does
  not route the call to a pay-as-you-go key or to Bedrock/Vertex. It CANNOT, however,
  override the operator's own machine config: a user/enterprise ``apiKeyHelper`` or a
  settings ``env`` block, or stored console credentials, could still cause API billing.
  Per project policy those are the account operator's responsibility; this runner
  records the observed ``provider`` / ``cost_basis`` so a reviewer can audit the auth
  path, and never changes the operator's billing settings.
* **No benchmark contamination.** The child runs in a caller-provided *empty* working
  directory with all filesystem / shell / network / search tools disallowed AND
  ``--strict-mcp-config`` (so no operator-configured MCP server loads and reaches the
  repo or network), and max-turns is bounded (default 1: a single answer, no tool
  loop). The resolved executable is rejected if it lives in the current directory, so a
  planted ``claude`` in the repo cannot be run.
* **Fail-safe parsing.** A timeout, a non-zero exit, or non-JSON stdout is captured as
  a structured failure, never raised. Latency, usage, model identity and permission
  denials are recorded for every call.

Cost figures reported by the CLI are LIST-price estimates (``cost_basis="list"`` under
subscription auth) and are informational only.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
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
    provider: str | None = None  # e.g. "firstParty" (audit the auth/billing path)
    cost_basis: str | None = None  # e.g. "list" (informational cost, not a real charge)
    num_turns: int | None = None
    duration_ms: int | None = None
    total_cost_usd: float | None = None  # LIST price, informational
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


def _primary_model_info(model_usage: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Canonical model + provider + cost_basis of the entry that produced the answer."""
    best: tuple[str | None, str | None, str | None] = (None, None, None)
    best_out = -1
    for mid, info in model_usage.items():
        if not isinstance(info, dict):
            continue
        out = int(info.get("outputTokens", 0))
        if out > best_out:
            best_out = out
            canonical = info.get("canonicalModel")
            best = (str(canonical or mid), info.get("provider"), info.get("costBasis"))
    return best


def _terminate_tree(proc: subprocess.Popen[str]) -> None:
    """Kill the child process and its descendants (the claude CLI spawns a node subtree)."""
    try:
        if os.name == "nt":
            subprocess.run(  # noqa: S603,S607 - fixed taskkill argv, no shell
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
                timeout=15,
            )
        else:
            # getattr-guarded: killpg/getpgid/SIGKILL are POSIX-only (absent on Windows).
            killpg = getattr(os, "killpg", None)
            getpgid = getattr(os, "getpgid", None)
            sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
            if killpg is not None and getpgid is not None:
                killpg(getpgid(proc.pid), sigkill)
            else:  # pragma: no cover
                proc.kill()
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - best effort
        with contextlib.suppress(Exception):
            proc.kill()


def _resolve_executable(executable: str | None) -> tuple[str | None, str | None]:
    """Resolve the claude executable, rejecting one planted in the current directory.

    Returns ``(path, error)``. On Windows ``shutil.which`` searches the CWD first, so a
    repo-local ``claude.exe`` / ``claude.bat`` could otherwise be executed.
    """
    exe = executable or shutil.which("claude")
    if exe is None:
        return None, "claude CLI not found on PATH (Phase C LLM baseline unavailable)"
    try:
        resolved = Path(exe).resolve()
        if resolved.parent == Path.cwd().resolve():
            return None, f"refusing to run claude resolved inside the working directory: {resolved}"
    except OSError:  # pragma: no cover - path resolution is environment dependent
        pass
    return exe, None


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
    exe, resolve_err = _resolve_executable(executable)
    if exe is None:
        return CliInvocation(ok=False, requested_model=model, error_detail=resolve_err)
    argv = [
        exe,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--strict-mcp-config",  # ignore operator-configured MCP servers (no repo/network reach)
        "--max-turns",
        str(max_turns),
        "--disallowed-tools",
        *disallowed_tools,
        "--model",
        model,
    ]
    # Popen (not subprocess.run) so a timeout kills the whole `claude` child PROCESS TREE.
    # subprocess.run's timeout only signals the direct child; the CLI's node grandchildren keep the
    # stdout pipe open, so wall time overran the bound (observed 343 s against a 150 s timeout).
    popen_kwargs: dict[str, Any] = {}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True  # own process group for killpg
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv is fully constructed, no shell
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=subscription_env(),
            cwd=cwd,
            **popen_kwargs,
        )
    except OSError as exc:  # pragma: no cover - environment dependent
        return CliInvocation(
            ok=False, requested_model=model, error_detail=f"failed to launch claude: {exc}"
        )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        _terminate_tree(proc)
        with contextlib.suppress(Exception):
            proc.communicate(timeout=10)
        return CliInvocation(
            ok=False,
            requested_model=model,
            timed_out=True,
            error_detail=f"claude CLI timed out after {timeout_s:.0f}s (process tree killed)",
        )

    stdout = stdout or ""
    try:
        env_json = json.loads(stdout)
    except json.JSONDecodeError:
        tail = (stderr or "")[-400:]
        return CliInvocation(
            ok=False,
            requested_model=model,
            returncode=returncode,
            error_detail=f"non-JSON stdout (rc={returncode}); stderr tail: {tail}",
        )
    if not isinstance(env_json, dict):
        return CliInvocation(
            ok=False,
            requested_model=model,
            returncode=returncode,
            error_detail="unexpected JSON shape (not an object)",
        )

    model_usage = env_json.get("modelUsage")
    model_usage = model_usage if isinstance(model_usage, dict) else {}
    usage = env_json.get("usage")
    denials = env_json.get("permission_denials")
    model_used, provider, cost_basis = _primary_model_info(model_usage)
    return CliInvocation(
        ok=True,
        requested_model=model,
        result_text=str(env_json.get("result", "")),
        is_error=bool(env_json.get("is_error", False)),
        model_used=model_used,
        provider=provider,
        cost_basis=cost_basis,
        num_turns=env_json.get("num_turns"),
        duration_ms=env_json.get("duration_ms"),
        total_cost_usd=env_json.get("total_cost_usd"),
        permission_denials=list(denials) if isinstance(denials, list) else [],
        usage=usage if isinstance(usage, dict) else {},
        returncode=returncode,
    )
