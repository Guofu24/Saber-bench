"""Deterministic in-memory EventStore for DEV: visibility-aware, paginated, episode-isolated."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from saber.domain.events import NormalizedEvent
from saber.domain.query import EventFilter, EventPage, FilterOperator, ResolvedEventQuery
from saber.telemetry.ports import ingest_order


def _get_field(event: NormalizedEvent, field: str) -> object:
    if field.startswith("attributes."):
        return event.attributes.get(field.split(".", 1)[1])
    if "." in field:
        head, tail = field.split(".", 1)
        sub = getattr(event, head, None)
        return getattr(sub, tail, None) if sub is not None else None
    return getattr(event, field, None)


def _as_str(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):  # StrEnum
        return str(value.value)
    return str(value)


def _matches(event: NormalizedEvent, flt: EventFilter) -> bool:
    actual = _get_field(event, flt.field)
    if flt.operator is FilterOperator.EQ:
        return _as_str(actual).lower() == _as_str(flt.value).lower()
    if flt.operator is FilterOperator.IN:
        values = flt.value if isinstance(flt.value, list) else [flt.value]
        return _as_str(actual).lower() in {_as_str(v).lower() for v in values}
    if flt.operator is FilterOperator.CONTAINS:
        return _as_str(flt.value).lower() in _as_str(actual).lower()
    # Remaining operators are GTE / LTE (numeric comparison).
    try:
        a, b = float(_as_str(actual)), float(_as_str(flt.value))
    except ValueError:
        return False
    return a >= b if flt.operator is FilterOperator.GTE else a <= b


class FakeEventStore:
    """Holds NormalizedEvents keyed by episode; enforces visibility and pagination on search."""

    def __init__(self, events: Iterable[NormalizedEvent] = ()) -> None:
        self._by_episode: dict[UUID, list[NormalizedEvent]] = defaultdict(list)
        for ev in events:
            self.add(ev)

    def add(self, event: NormalizedEvent) -> None:
        self._by_episode[event.episode_id].append(event)
        self._by_episode[event.episode_id].sort(key=ingest_order)

    def count(self, episode_id: UUID) -> int:
        return len(self._by_episode.get(episode_id, []))

    def search(self, query: ResolvedEventQuery) -> EventPage:
        events = self._by_episode.get(query.episode_id, [])
        scanned = 0
        selected: list[NormalizedEvent] = []
        hosts = {h.lower() for h in query.hosts}
        categories = {c for c in query.categories}
        start = _decode_cursor(query.cursor)
        ordered = events if query.order == "asc" else list(reversed(events))
        for ev in ordered:
            key = ingest_order(ev)
            # Visibility guard: the benchmark clock, not the agent, decides what is observable.
            if ev.visible_at > query.as_of or ev.occurred_at > query.as_of:
                continue
            if query.time_from and ev.occurred_at < query.time_from:
                continue
            if query.time_to and ev.occurred_at > query.time_to:
                continue
            if hosts and ev.host_id.lower() not in hosts:
                continue
            if categories and ev.category not in categories:
                continue
            if query.filters and not all(_matches(ev, f) for f in query.filters):
                continue
            if start is not None and not _after(key, start, query.order):
                continue
            scanned += 1
            selected.append(ev)
            if len(selected) > query.limit:
                break
        truncated = len(selected) > query.limit
        page = selected[: query.limit]
        next_cursor = _encode_cursor(ingest_order(page[-1])) if truncated and page else None
        return EventPage(
            events=page,
            next_cursor=next_cursor,
            as_of=query.as_of,
            scanned=len(page),
            truncated=truncated,
        )


def _encode_cursor(key: tuple[str, str, str]) -> str:
    import base64
    import json

    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str | None) -> tuple[str, str, str] | None:
    if not cursor:
        return None
    import base64
    import json

    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return (str(data[0]), str(data[1]), str(data[2]))
    except (ValueError, IndexError, TypeError):
        return None


def _after(key: tuple[str, str, str], start: tuple[str, str, str], order: str) -> bool:
    return key > start if order == "asc" else key < start
