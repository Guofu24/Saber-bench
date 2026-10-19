"""Adapters that need real external infrastructure must fail closed (BLOCKED_INTEGRATION)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from saber.domain.errors import IntegrationBlocked
from saber.domain.query import ResolvedEventQuery
from saber.range.blocked import BlockedEmulationDriver, BlockedRangeController
from saber.telemetry.opensearch_store import OpenSearchEventStore


def test_opensearch_store_blocked_but_translates_query() -> None:
    store = OpenSearchEventStore(base_url="https://indexer.invalid", index_pattern="saber-events-*")
    q = ResolvedEventQuery(episode_id=uuid4(), as_of=datetime(2026, 10, 17, tzinfo=UTC))
    dsl = store.to_backend_query(q)
    # Translation is implemented and time/episode-guarded even though live search is blocked.
    terms = dsl["query"]["bool"]["must"]
    assert {"term": {"episode_id": str(q.episode_id)}} in terms
    assert any("occurred_at" in list(t.get("range", {})) for t in terms)
    with pytest.raises(IntegrationBlocked):
        store.search(q)
    with pytest.raises(IntegrationBlocked):
        store.count(q.episode_id)


def test_blocked_range_controller_fails_closed() -> None:
    rc = BlockedRangeController(lab_environment_id="lab-1")
    for call in (
        lambda: rc.health("m1"),
        lambda: rc.snapshot("m1"),
        lambda: rc.capture_state("m1"),
    ):
        with pytest.raises(IntegrationBlocked):
            call()


def test_blocked_emulation_lists_but_refuses_execution() -> None:
    drv = BlockedEmulationDriver()
    assert drv.list_allowlisted()
    with pytest.raises(IntegrationBlocked):
        drv.execute(drv.list_allowlisted()[0], approval_id="op:1", targets=["lab-ws-01"])
    with pytest.raises(IntegrationBlocked):
        drv.execute("arbitrary_profile", approval_id="op:1", targets=["lab-ws-01"])
    assert drv.status("run-1") == "INDETERMINATE"
