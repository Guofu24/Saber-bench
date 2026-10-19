"""Domain ports (Protocols) for telemetry backends. Adapters implement these; domain depends on none."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from saber.domain.events import NormalizedEvent
from saber.domain.query import EventPage, ResolvedEventQuery


@runtime_checkable
class EventStore(Protocol):
    """A bounded, episode-scoped, time-aware event search backend.

    Implementations MUST honour the resolved query's `episode_id` and `as_of`: never return an
    event whose `visible_at` or `occurred_at` exceeds `as_of`, and never cross episodes. They
    return a page plus an opaque continuation token; unbounded reads are not part of the contract.
    """

    def search(self, query: ResolvedEventQuery) -> EventPage: ...

    def count(self, episode_id: UUID) -> int: ...


@runtime_checkable
class RawEvidenceStore(Protocol):
    """Immutable content-addressed blob store for raw evidence."""

    def put(self, data: bytes) -> str: ...

    def get(self, sha256: str) -> bytes: ...

    def exists(self, sha256: str) -> bool: ...


def ingest_order(event: NormalizedEvent) -> tuple[str, str, str]:
    """Stable sort key for deterministic pagination: (occurred_at, visible_at, event_id)."""
    return (event.occurred_at.isoformat(), event.visible_at.isoformat(), str(event.event_id))
