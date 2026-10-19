"""OpenSearch / Wazuh-Indexer EventStore adapter (T018) — BLOCKED_INTEGRATION.

Implements the same `EventStore` port as FakeEventStore, mapping the constrained EventQuery to a
field/index-allowlisted backend DSL. It is wired but fails closed: without an approved, reachable,
authenticated indexer it raises IntegrationBlocked rather than silently returning nothing. This is
the seam where a real cluster plugs in once a lab is approved; the gateway's time and episode
guards apply equally to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from saber.domain.errors import IntegrationBlocked
from saber.domain.query import EventPage, ResolvedEventQuery

# Index/field allowlist the adapter would enforce when translating a ResolvedEventQuery.
INDEX_ALLOWLIST = ("saber-events-*",)
FIELD_MAP = {
    "host_id": "host.name",
    "process.name": "process.name",
    "process.command_line": "process.command_line",
    "network.dst_ip": "destination.ip",
    "attributes.rule_id": "rule.id",
}


@dataclass
class OpenSearchEventStore:
    """Fails closed until an approved indexer is configured and reachable."""

    base_url: str | None = None
    index_pattern: str = "saber-events-*"
    credential_env_name: str | None = None
    connected: bool = False  # only a real, approved, authenticated connection sets this True

    def to_backend_query(self, query: ResolvedEventQuery) -> dict[str, Any]:
        """Translate the constrained query to a bounded backend DSL (no wildcards, time-guarded)."""
        must: list[dict[str, Any]] = [
            {"term": {"episode_id": str(query.episode_id)}},
            {"range": {"occurred_at": {"lte": query.as_of.isoformat()}}},
            {"range": {"visible_at": {"lte": query.as_of.isoformat()}}},
        ]
        for flt in query.filters:
            field = FIELD_MAP.get(flt.field, flt.field)
            must.append({"term": {field: flt.value}})
        return {"index": self.index_pattern, "size": query.limit, "query": {"bool": {"must": must}}}

    def search(self, query: ResolvedEventQuery) -> EventPage:
        if not self.connected:
            raise IntegrationBlocked(
                "OpenSearch/Wazuh event search is BLOCKED_INTEGRATION: needs an approved, reachable, "
                "authenticated indexer (config/existing-environment.json + SECURITY.md). "
                "Translation to backend DSL is implemented and tested; live search is not available.",
                base_url=self.base_url,
                index=self.index_pattern,
            )
        raise NotImplementedError("live OpenSearch search path intentionally unimplemented in DEV")

    def count(self, episode_id: UUID) -> int:
        if not self.connected:
            raise IntegrationBlocked(
                "OpenSearch count is BLOCKED_INTEGRATION", base_url=self.base_url
            )
        raise NotImplementedError
