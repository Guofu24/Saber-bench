"""Telemetry: event store ports, a deterministic fake store, and the bounded query gateway.

The gateway is the only path by which a Blue agent reaches events. It binds episode identity and
the benchmark clock server-side, enforces visibility (`visible_at`/`occurred_at <= as_of`), caps
page size and scan budget, allowlists filter fields, and audits every denial. Real backends
(OpenSearch/Wazuh) are adapters behind the same `EventStore` port and are BLOCKED_INTEGRATION
until a lab is approved.
"""

from saber.telemetry.fake_store import FakeEventStore
from saber.telemetry.gateway import GatewaySession, QueryGateway
from saber.telemetry.ports import EventStore

__all__ = ["EventStore", "FakeEventStore", "GatewaySession", "QueryGateway"]
