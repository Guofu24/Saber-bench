"""Specialist router: maps a subtask's primary service to a specialist handler.

Architecturally this is where Monitor / Hunt / Content / IR specialists and shared case state
attach. In offline DEV each specialist delegates to a deterministic solver (rules-only reference
or the stub provider), so the routing and case-handoff shape is real while no LLM runs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from saber.episodes.builder import BuiltEpisode

SERVICE_TO_SPECIALIST = {
    "MON": "monitor",
    "HUNT": "hunt",
    "CNT": "content",
    "IR": "incident_response",
}

Solver = Callable[[BuiltEpisode], tuple[dict[str, Any], list[str]] | None]


@dataclass
class SpecialistRouter:
    """Routes an episode to the specialist for its service. `solver` produces the answer."""

    solver: Solver
    handled: dict[str, int] = field(default_factory=dict)

    def specialist_for(self, service: str) -> str:
        return SERVICE_TO_SPECIALIST.get(service, "monitor")

    def solve(self, episode: BuiltEpisode) -> tuple[str, dict[str, Any] | None, list[str]]:
        service = episode.subtask.spec().service.value
        specialist = self.specialist_for(service)
        self.handled[specialist] = self.handled.get(specialist, 0) + 1
        result = self.solver(episode)
        if result is None:
            return specialist, None, []
        answer, refs = result
        return specialist, answer, refs

    def coverage(self) -> Mapping[str, int]:
        return dict(self.handled)
