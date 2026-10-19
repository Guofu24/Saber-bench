"""Grading result DTOs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from saber.domain.base import Sha256Hex, StrictModel, SubtaskId, UnitInterval, UtcDatetime


class Validity(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"


GateMode = Literal["zero", "factor", "cap", "invalid", "per_element"]


class ItemScore(StrictModel):
    field: str
    score: UnitInterval
    weight: float | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class GateOutcome(StrictModel):
    name: str
    passed: bool
    mode: GateMode = "zero"
    factor: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str = ""


class PenaltyApplied(StrictModel):
    name: str
    count: int = Field(ge=0)
    per_item: float = Field(ge=0.0, le=1.0)
    deducted: float = Field(ge=0.0)


class ScoreResult(StrictModel):
    schema_version: Literal[1] = 1
    subtask_id: SubtaskId
    episode_id: UUID
    score: UnitInterval
    raw_score: UnitInterval
    validity: Validity = Validity.VALID
    invalid_reason: str | None = None
    components: list[ItemScore] = Field(default_factory=list)
    gates: list[GateOutcome] = Field(default_factory=list)
    caps_applied: list[str] = Field(default_factory=list)
    penalties_applied: list[PenaltyApplied] = Field(default_factory=list)
    scorer_version: str
    scorer_ref: str
    submission_sha256: Sha256Hex
    truth_sha256: Sha256Hex
    trace: list[str] = Field(default_factory=list)
    graded_at: UtcDatetime
    labels: list[str] = Field(default_factory=lambda: ["DEV_SIMULATION_ONLY"])
