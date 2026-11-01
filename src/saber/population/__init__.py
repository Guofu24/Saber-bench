"""Live Gemini-driven agent population over the isolated cyber range (Phase H5).

Four role families, each an LLM agent that loads its operational skill from ``.claude/skills`` and
acts in the REAL loopback range:

* **client** (``client-user``) — benign background users/machines.
* **red** (``redteam-*``) — adversary emulation, choosing ONLY from an inert allowlist menu.
* **blue** (``soc-mon`` / ``soc-hunt`` / ``soc-ir``) — reads the real access-log telemetry and
  reports which lines are malicious.
* **orchestrator** (``soc-orchestrator``) — routes the case and keeps the shared case record.

The range (service + control plane) runs for real and derives ground truth SERVER-SIDE, independent
of any agent claim. Red/client agents can only emit pre-vetted inert menu actions — the code rejects
anything off-menu — so the independent-truth invariant of ``attack_registry`` is preserved. Results
are DEV_SIMULATION_ONLY: they show the living loop runs and measure blue detection against the
server-derived truth; nothing here is a validated benchmark.
"""

from __future__ import annotations

from saber.population.active_client import (
    ActiveClientReport,
    ActivityProfile,
    run_active_client,
    scripted_default_profile,
)
from saber.population.loop import (
    PopulationEpisode,
    run_forever,
    run_population,
    run_population_episode,
)
from saber.population.menus import FAMILY_MENUS, MenuAction, expand_actions, menu_for
from saber.population.office import OfficeEmitter

__all__ = [
    "FAMILY_MENUS",
    "ActiveClientReport",
    "ActivityProfile",
    "MenuAction",
    "OfficeEmitter",
    "PopulationEpisode",
    "expand_actions",
    "menu_for",
    "run_active_client",
    "run_forever",
    "run_population",
    "run_population_episode",
    "scripted_default_profile",
]
