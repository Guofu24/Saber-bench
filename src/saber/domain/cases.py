"""Finding and Case DTOs."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from saber.domain.base import HostId, StrictModel, UnitInterval, UtcDatetime


class Verdict(StrEnum):
    MALICIOUS = "malicious"
    BENIGN = "benign"
    UNKNOWN = "unknown"


class CaseStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class Finding(StrictModel):
    schema_version: Literal[1] = 1
    finding_id: UUID
    episode_id: UUID
    agent_id: str = Field(min_length=1, max_length=64)
    hypothesis: str = Field(min_length=1, max_length=4000)
    verdict: Verdict
    confidence: UnitInterval
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=500)
    affected_hosts: list[HostId] = Field(default_factory=list, max_length=500)
    attack_techniques: list[str] = Field(default_factory=list, max_length=100)
    observed_at: UtcDatetime
    rationale: str = Field(default="", max_length=8000)
    model_usage_ref: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _evidence_policy(self) -> Finding:
        if self.verdict is Verdict.MALICIOUS and not self.evidence_ids:
            raise ValueError("a malicious finding requires at least one evidence_id")
        if not self.evidence_ids and not self.rationale.strip():
            raise ValueError("benign/unknown findings without evidence must state a rationale")
        return self


class Case(StrictModel):
    schema_version: Literal[1] = 1
    case_id: UUID
    episode_id: UUID
    status: CaseStatus = CaseStatus.OPEN
    finding_ids: list[UUID] = Field(default_factory=list)
    timeline_event_ids: list[UUID] = Field(default_factory=list)
    assignee_agent: str | None = Field(default=None, max_length=64)
    created_at: UtcDatetime
    resolved_at: UtcDatetime | None = None
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _resolution(self) -> Case:
        if self.status is CaseStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved cases need resolved_at")
        if self.resolved_at is not None and self.resolved_at < self.created_at:
            raise ValueError("resolved_at precedes created_at")
        return self
