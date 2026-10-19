"""T002 contract tests: strictness, timezone handling, evidence policy, forbidden payloads."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from saber.domain.base import deterministic_uuid
from saber.domain.cases import Finding, Verdict
from saber.domain.events import EventCategory, EventSource, NormalizedEvent
from saber.domain.query import EventFilter, EventQueryRequest, FilterOperator, ResolvedEventQuery
from saber.domain.responses import ActionKind, ActionTarget, ResponseAction
from saber.domain.rules import DetectionRuleProposal, RuleKind
from saber.domain.runs import (
    BLUE_FORBIDDEN_FIELDS,
    RUN_TRANSITIONS,
    BlueEpisodeView,
    Episode,
    RunStatus,
)

T0 = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
SHA = "a" * 64


def make_event(**over: object) -> NormalizedEvent:
    base = dict(
        event_id=uuid4(), episode_id=uuid4(), occurred_at=T0, ingested_at=T0 + timedelta(seconds=2),
        visible_at=T0 + timedelta(seconds=3), host_id="workstation-01", source=EventSource.WINDOWS_SYSMON,
        category=EventCategory.PROCESS_ACTIVITY, action="process_start", raw_ref="file://dev/raw/1",
        raw_sha256=SHA, normalizer_version="1.0.0", process={"name": "powershell.exe"},
    )  # fmt: skip
    base.update(over)
    return NormalizedEvent.model_validate(base)


def test_event_json_roundtrip() -> None:
    ev = make_event()
    again = NormalizedEvent.model_validate_json(ev.model_dump_json())
    assert again == ev
    assert json.loads(ev.model_dump_json())["schema_version"] == 1


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(occurred_at=datetime(2026, 10, 17, 9, 0))


def test_non_utc_normalized_to_utc() -> None:
    from datetime import timezone

    plus7 = timezone(timedelta(hours=7))
    ev = make_event(occurred_at=datetime(2026, 10, 17, 16, 0, tzinfo=plus7))
    assert ev.occurred_at == T0


def test_visible_before_ingested_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(visible_at=T0 - timedelta(seconds=1))


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(attack_label="malicious")


def test_bad_sha_rejected() -> None:
    with pytest.raises(ValidationError):
        make_event(raw_sha256="zz")


def test_filter_allowlist_and_operators() -> None:
    EventFilter(field="process.name", operator=FilterOperator.EQ, value="cmd.exe")
    with pytest.raises(ValidationError):
        EventFilter(field="__internal.attack_label", operator=FilterOperator.EQ, value=1)
    with pytest.raises(ValidationError):
        EventFilter(field="process.name", operator=FilterOperator.CONTAINS, value="x")
    with pytest.raises(ValidationError):
        EventFilter(field="host_id", operator=FilterOperator.IN, value=[])
    with pytest.raises(ValidationError):
        EventQueryRequest(limit=10_000)
    with pytest.raises(ValidationError):
        EventQueryRequest.model_validate({"raw_dsl": {"query": {"match_all": {}}}})
    with pytest.raises(ValidationError):
        EventQueryRequest.model_validate({"sql": "select * from events"})


def test_query_window_and_future_denied() -> None:
    with pytest.raises(ValidationError):
        EventQueryRequest(time_from=T0, time_to=T0 - timedelta(minutes=1))
    with pytest.raises(ValidationError):
        EventQueryRequest(time_from=T0, time_to=T0 + timedelta(days=40))
    assert "as_of" not in EventQueryRequest.model_fields
    with pytest.raises(ValidationError):
        EventQueryRequest.model_validate({"as_of": T0.isoformat()})
    with pytest.raises(ValidationError):
        ResolvedEventQuery(
            episode_id=uuid4(), as_of=T0, time_from=T0, time_to=T0 + timedelta(minutes=5)
        )


def test_finding_rules() -> None:
    with pytest.raises(ValidationError):
        Finding(finding_id=uuid4(), episode_id=uuid4(), agent_id="monitor", hypothesis="h",
                verdict=Verdict.MALICIOUS, confidence=0.9, observed_at=T0)  # fmt: skip
    with pytest.raises(ValidationError):
        Finding(finding_id=uuid4(), episode_id=uuid4(), agent_id="monitor", hypothesis="h",
                verdict=Verdict.MALICIOUS, confidence=1.5, evidence_ids=[uuid4()], observed_at=T0)  # fmt: skip
    ok = Finding(finding_id=uuid4(), episode_id=uuid4(), agent_id="monitor", hypothesis="h",
                 verdict=Verdict.BENIGN, confidence=0.2, observed_at=T0, rationale="admin change window")  # fmt: skip
    assert ok.evidence_ids == []


def test_response_action_has_no_command_surface() -> None:
    now = T0
    good = ResponseAction(action_id=uuid4(), episode_id=uuid4(), kind=ActionKind.ISOLATE_LAB_HOST,
                          target=ActionTarget(host_id="lab-ws-01"), reason="C2 beacon", created_at=now,
                          expires_at=now + timedelta(hours=1))  # fmt: skip
    assert good.mode.value == "dry_run"
    with pytest.raises(ValidationError):
        ResponseAction.model_validate({**good.model_dump(), "command": "rm -rf /"})
    with pytest.raises(ValidationError):
        ActionTarget(path="/tmp/x; rm -rf /")
    with pytest.raises(ValidationError):
        ActionTarget(account="$(whoami)")
    with pytest.raises(ValidationError):
        ResponseAction(action_id=uuid4(), episode_id=uuid4(), kind=ActionKind.BLOCK_LAB_ADDRESS,
                       target=ActionTarget(address="10.0.0.5"), reason="x", created_at=now,
                       expires_at=now + timedelta(hours=1))  # missing layer  # fmt: skip
    with pytest.raises(ValidationError):
        ResponseAction(action_id=uuid4(), episode_id=uuid4(), kind=ActionKind.ISOLATE_LAB_HOST,
                       target=ActionTarget(host_id="lab-ws-01"), reason="x", created_at=now, expires_at=now)  # fmt: skip


def test_rule_hash_enforced() -> None:
    content = "title: t\ndetection: {}"
    with pytest.raises(ValidationError):
        DetectionRuleProposal(rule_version_id=uuid4(), rule_kind=RuleKind.SIGMA, content=content,
                              content_sha256=SHA, author_agent="content", created_at=T0)  # fmt: skip
    DetectionRuleProposal(rule_version_id=uuid4(), rule_kind=RuleKind.SIGMA, content=content,
                          content_sha256=hashlib.sha256(content.encode()).hexdigest(),
                          author_agent="content", created_at=T0)  # fmt: skip


def test_blue_view_has_no_truth_fields() -> None:
    assert not (set(BlueEpisodeView.model_fields) & BLUE_FORBIDDEN_FIELDS)
    assert "attack_success_verified" not in BlueEpisodeView.model_fields
    assert "scenario_id" in Episode.model_fields  # control-plane only


def test_run_transitions_terminal() -> None:
    assert RUN_TRANSITIONS[RunStatus.COMPLETED] == frozenset()
    assert RunStatus.INVALID in RUN_TRANSITIONS[RunStatus.RUNNING]
    assert RunStatus.COMPLETED not in RUN_TRANSITIONS[RunStatus.RUNNING]


def test_deterministic_uuid_stable() -> None:
    assert deterministic_uuid("T1112.001", "42") == deterministic_uuid("T1112.001", "42")
    assert deterministic_uuid("T1112.001", "42") != deterministic_uuid("T1112.001", "43")
