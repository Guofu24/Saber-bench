"""Partition keys by file position without exposing credentials or shifting boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from saber.agents.gemini import KeyPool
from saber.domain.errors import IntegrationBlocked
from saber.world.models import Team


@dataclass(repr=False)
class TeamKeyLayout:
    pool: KeyPool
    indices: dict[Team, list[int]]

    @classmethod
    def from_file(cls, path: Path, *, client_keys: int = 200, red_keys: int = 200) -> TeamKeyLayout:
        if not path.is_file():
            raise IntegrationBlocked(f"Gemini key pool file not found: {path}")
        entries = []
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            value = raw.strip()
            if not value or value.startswith("#"):
                continue
            head, sep, tail = value.partition("=")
            if sep and " " not in head and tail.strip():
                value = tail.strip()
            entries.append(value)
        # Silently deduplicating first would move the 200/400 boundaries; sharing a
        # duplicate between teams would defeat isolation. Reject either ambiguity.
        if len(set(entries)) != len(entries):
            raise ValueError(
                "Duplicate key entries in team pool; remove duplicates explicitly before partitioning."
            )
        return cls.from_pool(KeyPool(keys=entries), client_keys=client_keys, red_keys=red_keys)

    @classmethod
    def from_pool(
        cls, pool: KeyPool, *, client_keys: int = 200, red_keys: int = 200
    ) -> TeamKeyLayout:
        if min(client_keys, red_keys) <= 0:
            raise ValueError("Client/red allocations must be positive.")
        if len(pool.keys) <= client_keys + red_keys:
            raise ValueError(
                f"Team layout needs at least {client_keys + red_keys + 1} unique keys so blue has a pool."
            )
        if len(set(pool.keys)) != len(pool.keys):
            raise ValueError("Team layout requires unique keys.")
        return cls(
            pool=pool,
            indices={
                "client": list(range(client_keys)),
                "red": list(range(client_keys, client_keys + red_keys)),
                "blue": list(range(client_keys + red_keys, len(pool.keys))),
            },
        )

    def __repr__(self) -> str:
        return f"TeamKeyLayout(counts={self.counts()})"

    def counts(self) -> dict[str, int]:
        return {team: len(indices) for team, indices in self.indices.items()}
