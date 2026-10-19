"""Bounded query gateway (T009): the only Blue path to events.

Responsibilities enforced here, not trusted from the agent:
  * `episode_id` comes from the authenticated session, never the request.
  * `as_of` comes from the benchmark clock, never the request (the request DTO has no `as_of`).
  * page size, time range, filter fields and per-session scan/query budgets are capped.
  * continuation cursors are HMAC-signed and bound to (episode, as_of, query shape); a cursor
    minted for one episode cannot be replayed against another.
  * every denial is appended to an in-memory audit log with a typed reason.
Raw telemetry content is data: instructions embedded in a log field never change policy here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from saber.domain.errors import (
    BudgetExceeded,
    CrossEpisodeDenied,
    PolicyDenied,
    TimeLeakDenied,
    ValidationError,
)
from saber.domain.query import EventPage, EventQueryRequest, ResolvedEventQuery
from saber.telemetry.ports import EventStore

_DEV_CURSOR_KEY = b"saber-dev-cursor-key-not-a-secret"


@dataclass
class AuditEntry:
    episode_id: str
    decision: str
    reason: str
    at: str


@dataclass
class GatewaySession:
    """An authenticated, episode-scoped session with a fixed benchmark clock and budgets."""

    episode_id: UUID
    as_of: datetime
    max_queries: int = 50
    max_scanned: int = 5000
    queries_used: int = 0
    scanned_used: int = 0
    audit: list[AuditEntry] = field(default_factory=list)

    def _record(self, decision: str, reason: str) -> None:
        self.audit.append(AuditEntry(str(self.episode_id), decision, reason, _now()))


class QueryGateway:
    def __init__(
        self,
        store: EventStore,
        *,
        clock: Callable[[], datetime] | None = None,
        cursor_key: bytes = _DEV_CURSOR_KEY,
    ) -> None:
        self._store = store
        self._clock = clock
        self._key = cursor_key

    def open_session(
        self, episode_id: UUID, as_of: datetime, *, max_queries: int = 50, max_scanned: int = 5000
    ) -> GatewaySession:
        return GatewaySession(
            episode_id=episode_id, as_of=as_of, max_queries=max_queries, max_scanned=max_scanned
        )

    def search(self, session: GatewaySession, request: EventQueryRequest) -> EventPage:
        if session.queries_used >= session.max_queries:
            session._record("deny", "query quota exceeded")
            raise BudgetExceeded("per-session query quota exceeded")
        session.queries_used += 1

        # Reject any attempt to smuggle a client-supplied as_of / episode / raw DSL.
        extra = set(request.model_dump(exclude_unset=True)) - set(EventQueryRequest.model_fields)
        if extra:
            session._record("deny", f"unknown request fields: {sorted(extra)}")
            raise ValidationError(f"unknown query fields: {sorted(extra)}")

        # Reject a future window before constructing the resolved query (whose validator would
        # otherwise raise a generic error): the benchmark clock, not the agent, bounds visibility.
        if request.time_to is not None and request.time_to > session.as_of:
            session._record("deny", "time_to after as_of")
            raise TimeLeakDenied("requested window extends past the benchmark clock")
        if request.time_from is not None and request.time_from > session.as_of:
            session._record("deny", "time_from after as_of")
            raise TimeLeakDenied("requested window starts past the benchmark clock")

        inner_cursor = self._verify_cursor(session, request)
        resolved = ResolvedEventQuery(
            episode_id=session.episode_id,
            as_of=session.as_of,
            time_from=request.time_from,
            time_to=request.time_to,
            hosts=request.hosts,
            categories=request.categories,
            filters=request.filters,
            limit=request.limit,
            cursor=inner_cursor,
            order=request.order,
        )
        page = self._store.search(resolved)

        # Defence in depth: the store must never hand back a future or cross-episode event.
        for ev in page.events:
            if ev.episode_id != session.episode_id:
                session._record("deny", "store returned cross-episode event")
                raise CrossEpisodeDenied("backend returned an event from another episode")
            if ev.visible_at > session.as_of or ev.occurred_at > session.as_of:
                session._record("deny", "store returned future event")
                raise TimeLeakDenied("backend returned an event not yet visible")

        session.scanned_used += page.scanned
        if session.scanned_used > session.max_scanned:
            session._record("deny", "scan budget exceeded")
            raise BudgetExceeded("per-session scanned-record budget exceeded")

        signed = self._sign_cursor(session, request, page.next_cursor) if page.next_cursor else None
        session._record("allow", f"returned {len(page.events)} events")
        return page.model_copy(update={"next_cursor": signed})

    # -- cursor signing: bind continuation to (episode, as_of, query shape) ------------
    def _query_shape(self, session: GatewaySession, request: EventQueryRequest) -> str:
        shape = {
            "episode": str(session.episode_id),
            "as_of": session.as_of.isoformat(),
            "time_from": request.time_from.isoformat() if request.time_from else None,
            "time_to": request.time_to.isoformat() if request.time_to else None,
            "hosts": sorted(request.hosts),
            "categories": sorted(c.value for c in request.categories),
            "filters": [f.model_dump(mode="json") for f in request.filters],
            "order": request.order,
        }
        return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()

    def _sign_cursor(self, session: GatewaySession, request: EventQueryRequest, inner: str) -> str:
        shape = self._query_shape(session, request)
        body = json.dumps({"shape": shape, "inner": inner}).encode()
        mac = hmac.new(self._key, body, hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(
            json.dumps({"b": base64.urlsafe_b64encode(body).decode(), "m": mac}).encode()
        ).decode()

    def _verify_cursor(self, session: GatewaySession, request: EventQueryRequest) -> str | None:
        if not request.cursor:
            return None
        try:
            outer = json.loads(base64.urlsafe_b64decode(request.cursor.encode()).decode())
            body = base64.urlsafe_b64decode(outer["b"].encode())
            expected = hmac.new(self._key, body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, str(outer["m"])):
                raise ValueError("bad mac")
            payload = json.loads(body.decode())
        except (ValueError, KeyError, TypeError) as exc:
            session._record("deny", "invalid or tampered cursor")
            raise PolicyDenied("invalid pagination cursor") from exc
        if payload.get("shape") != self._query_shape(session, request):
            session._record("deny", "cursor does not match this episode/query")
            raise CrossEpisodeDenied("cursor was issued for a different episode or query")
        return str(payload["inner"])


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
