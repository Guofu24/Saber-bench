"""Experiment runs and episodes, with explicit INVALID vs FAILED semantics."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from saber.domain.base import Sha256Hex, StrictModel, SubtaskId, UtcDatetime


class Track(StrEnum):
    DETECTION_ONLY = "DETECTION_ONLY"
    RESPONSE_ENABLED = "RESPONSE_ENABLED"


class RunStatus(StrEnum):
    CREATED = "CREATED"
    PREPARING = "PREPARING"
    READY = "READY"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALID = "INVALID"


_R = RunStatus
_FAIL = {_R.FAILED, _R.INVALID}
RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    _R.CREATED: frozenset({_R.PREPARING, *_FAIL}),
    _R.PREPARING: frozenset({_R.READY, *_FAIL}),
    _R.READY: frozenset({_R.RUNNING, *_FAIL}),
    _R.RUNNING: frozenset({_R.OBSERVING, *_FAIL}),
    _R.OBSERVING: frozenset({_R.EVALUATING, *_FAIL}),
    _R.EVALUATING: frozenset({_R.COMPLETED, *_FAIL}),
    _R.COMPLETED: frozenset(),
    _R.FAILED: frozenset(),
    _R.INVALID: frozenset(),
}
TERMINAL_RUN_STATES = frozenset({_R.COMPLETED, _R.FAILED, _R.INVALID})


class EpisodeStatus(StrEnum):
    CREATED = "CREATED"
    PREPARED = "PREPARED"
    RUNNING = "RUNNING"
    SUBMITTED = "SUBMITTED"
    GRADED = "GRADED"
    INVALID = "INVALID"
    FAILED = "FAILED"


_E = EpisodeStatus
_EFAIL = {_E.FAILED, _E.INVALID}
EPISODE_TRANSITIONS: dict[EpisodeStatus, frozenset[EpisodeStatus]] = {
    _E.CREATED: frozenset({_E.PREPARED, *_EFAIL}),
    _E.PREPARED: frozenset({_E.RUNNING, *_EFAIL}),
    _E.RUNNING: frozenset({_E.SUBMITTED, *_EFAIL}),
    _E.SUBMITTED: frozenset({_E.GRADED, *_EFAIL}),
    _E.GRADED: frozenset(),
    _E.INVALID: frozenset(),
    _E.FAILED: frozenset(),
}
TERMINAL_EPISODE_STATES = frozenset({_E.GRADED, _E.INVALID, _E.FAILED})


class AttackVerification(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    INDETERMINATE = "INDETERMINATE"
    NOT_APPLICABLE_BENIGN = "NOT_APPLICABLE_BENIGN"


class ExperimentRun(StrictModel):
    schema_version: Literal[1] = 1
    run_id: UUID
    experiment_config_hash: Sha256Hex
    baseline_id: str = Field(min_length=1, max_length=32)
    track: Track = Track.DETECTION_ONLY
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(default="", max_length=128)
    agent_architecture_version: str = Field(min_length=1, max_length=64)
    prompt_hashes: dict[str, Sha256Hex] = Field(default_factory=dict)
    code_commit: str = Field(default="unknown", max_length=64)
    rule_registry_hash: Sha256Hex | None = None
    provider_token_budget: int = Field(ge=0)
    tool_budget: int = Field(ge=0)
    wall_clock_budget_seconds: int = Field(ge=1)
    random_seed: int
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    status: RunStatus = RunStatus.CREATED
    idempotency_key: str = Field(min_length=1, max_length=128)


class Episode(StrictModel):
    """Control-plane episode record. Contains scenario_id; never serve this to Blue agents."""

    schema_version: Literal[1] = 1
    episode_id: UUID
    run_id: UUID
    subtask_id: SubtaskId
    scenario_id: UUID
    seed: int
    environment_snapshot_hash: Sha256Hex | None = None
    workload_profile_hash: Sha256Hex | None = None
    telemetry_health: Literal["ok", "degraded", "missing", "unknown"] = "unknown"
    attack_verification: AttackVerification = AttackVerification.INDETERMINATE
    result_ref: str | None = Field(default=None, max_length=512)
    status: EpisodeStatus = EpisodeStatus.CREATED
    invalid_reason: str | None = Field(default=None, max_length=512)
    created_at: UtcDatetime
    deadline_at: UtcDatetime | None = None


class BlueEpisodeView(StrictModel):
    """Agent-facing view: opaque episode id + public manifest pointer only."""

    schema_version: Literal[1] = 1
    episode_id: UUID
    subtask_id: SubtaskId
    public_manifest_ref: str = Field(min_length=1, max_length=512)
    deadline_at: UtcDatetime | None = None
    tool_budget: int = Field(ge=0)


BLUE_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "scenario_id", "seed", "attack_verification", "attack_success_verified", "is_malicious",
        "truth", "sealed_truth", "labels", "dataset_split", "run_snapshot_id",
    }
)  # fmt: skip
