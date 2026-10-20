"""Phase F — a minimal, genuinely executable local SOC lab.

A real HTTP service runs as a subprocess, a control plane drives real benign + bounded (inert)
security traffic at it over loopback, and the service's REAL access log is collected as telemetry.
Ground truth is derived by the control plane from the server-side log, independently of the agent.
Evidence is stored with SHA256 + timestamps. Nothing here fabricates telemetry, touches an external
system, or uses a destructive payload; all traffic is loopback-only with inert probe strings.

Two backends share this control plane:

* **process-local** (:mod:`saber.range.live.controlplane`) — runs on the host Python now; the
  "permitted runtime available" path, loopback-isolated.
* **container** (the ``cyber-range`` GitHub Actions workflow) — the same lab in a hardened Linux
  container for a stronger-isolation run on an authorized runner.
"""

from __future__ import annotations

from saber.range.live.bench import run_live_benchmark, write_live_benchmark
from saber.range.live.controlplane import LiveLab, run_episode
from saber.range.live.episode import LiveEpisode
from saber.range.live.ir_actions import (
    ALLOWLISTED_ACTIONS,
    ActionResult,
    quarantine_file,
    restore_file,
)
from saber.range.live.scenarios import SCENARIOS, scenario_ids

__all__ = [
    "ALLOWLISTED_ACTIONS",
    "SCENARIOS",
    "ActionResult",
    "LiveEpisode",
    "LiveLab",
    "quarantine_file",
    "restore_file",
    "run_episode",
    "run_live_benchmark",
    "scenario_ids",
    "write_live_benchmark",
]
