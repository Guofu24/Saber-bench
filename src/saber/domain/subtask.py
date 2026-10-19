"""SubtaskSpecV1 (B002): the executable contract derived from one frozen catalog record."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from saber.catalog.models import (
    AggregateKind,
    CatalogSubtask,
    ParsedAggregate,
    ParsedScoreItem,
    ScoreItemKind,
)
from saber.domain.base import NiceId, Sha256Hex, StrictModel, SubtaskId, UtcDatetime


class Service(StrEnum):
    MON = "MON"
    CNT = "CNT"
    HUNT = "HUNT"
    IR = "IR"


class Environment(StrEnum):
    FILE = "file"
    SOC = "soc"
    VM = "vm"


class Visibility(StrEnum):
    BLUE = "blue"
    EVALUATOR = "evaluator"
    CONTROL = "control"


class GateSemantics(StrEnum):
    ZERO = "zero"
    CAP = "cap"
    INVALID = "invalid"


class ArtifactInputSpec(StrictModel):
    hv_id: str = Field(pattern=r"^HV-\d{2}$")
    description: str
    visibility: Visibility = Visibility.BLUE
    path: str | None = None
    sha256: Sha256Hex | None = None


class ToolPolicy(StrictModel):
    default: Literal["deny"] = "deny"
    allow: list[str] = Field(default_factory=lambda: ["read_fixture"])
    state_mutation: bool = False


class TimePolicy(StrictModel):
    observation_cutoff: UtcDatetime | None = None
    visibility_cutoff: UtcDatetime | None = None


class Timeouts(StrictModel):
    episode_seconds: int = Field(ge=1)
    tool_calls: int = Field(ge=0)
    source: Literal["default_by_environment", "subtask_specific"] = "default_by_environment"


DEFAULT_TIMEOUTS: dict[Environment, Timeouts] = {
    Environment.FILE: Timeouts(episode_seconds=600, tool_calls=10),
    Environment.SOC: Timeouts(episode_seconds=1800, tool_calls=60),
    Environment.VM: Timeouts(episode_seconds=1800, tool_calls=100),
}


class SubtaskSpecV1(StrictModel):
    schema_version: Literal[1] = 1
    id: SubtaskId
    nice_id: NiceId
    service: Service
    environment: Environment
    task_version: str = "1.0.0"
    source_sha256: Sha256Hex
    title_vi: str
    title_en: str
    scenario_source: str
    inputs: list[ArtifactInputSpec]
    output_hv_ids: list[str]
    output_is_unmaterialized: bool
    score_items: list[ParsedScoreItem]
    aggregate: ParsedAggregate
    output_schema_ref: str
    scorer_ref: str
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    time_policy: TimePolicy = Field(default_factory=TimePolicy)
    timeouts: Timeouts
    invalidity: list[str] = Field(default_factory=list)
    gate_semantics: dict[str, GateSemantics] = Field(default_factory=dict)
    adjudication_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistency(self) -> SubtaskSpecV1:
        if self.id.split(".")[0] != self.nice_id:
            raise ValueError("subtask id must start with nice_id")
        if self.aggregate.kind is AggregateKind.WEIGHTED_SUM:
            total = sum(i.weight or 0.0 for i in self.score_items if not i.is_gate)
            if abs(total - 1.0) > 1e-6 and not self.adjudication_notes:
                raise ValueError(
                    f"weighted-sum weights total {total:.3f} != 1.0 and no adjudication note"
                )
        if self.environment is Environment.VM:
            if "snapshot_contaminated" not in self.invalidity:
                raise ValueError("vm subtasks must declare snapshot_contaminated invalidity")
            if (
                self.tool_policy.state_mutation
                and "approved_lab_action" not in self.tool_policy.allow
            ):
                raise ValueError(
                    "state-mutating vm subtasks must allow only approved_lab_action tools"
                )
        if (
            self.environment is Environment.SOC
            and "missing_required_evidence" not in self.invalidity
        ):
            raise ValueError("soc subtasks must declare missing_required_evidence invalidity")
        for item in self.score_items:
            if item.is_gate and item.field not in self.gate_semantics:
                raise ValueError(f"gate item {item.field!r} lacks explicit gate semantics")
        return self

    @property
    def weighted_items(self) -> list[ParsedScoreItem]:
        return [i for i in self.score_items if not i.is_gate]

    @property
    def gate_items(self) -> list[ParsedScoreItem]:
        return [i for i in self.score_items if i.is_gate or i.kind is ScoreItemKind.GATE]


def default_gate_semantics(
    items: list[ParsedScoreItem], aggregate: ParsedAggregate
) -> dict[str, GateSemantics]:
    """Source gates multiply the score (× [gate]); default is ZERO unless a cap is declared."""
    out: dict[str, GateSemantics] = {}
    for item in items:
        if item.is_gate:
            out[item.field] = GateSemantics.ZERO
    for cap in aggregate.caps:
        out[f"cap:{cap.condition}"] = GateSemantics.CAP
    return out


def default_invalidity(environment: Environment) -> list[str]:
    base = ["missing_required_evidence", "schema_invalid_submission"]
    if environment is Environment.VM:
        base += ["snapshot_contaminated", "isolation_unverified"]
    if environment is Environment.SOC:
        base += ["data_source_unhealthy", "future_log_leak_detected"]
    return base


def spec_from_catalog(
    record: CatalogSubtask,
    *,
    output_schema_ref: str,
    scorer_ref: str,
    tool_policy: ToolPolicy | None = None,
    timeouts: Timeouts | None = None,
    adjudication_notes: list[str] | None = None,
) -> SubtaskSpecV1:
    if record.aggregate is None:
        raise ValueError("catalog record must carry a parsed aggregate")
    environment = Environment(record.environment)
    inputs = [
        ArtifactInputSpec(hv_id=hv, description=desc)
        for hv, desc in zip(record.input_hv_ids, _align_descriptions(record), strict=True)
    ]
    return SubtaskSpecV1(
        id=record.id,
        nice_id=record.nice_id,
        service=Service(record.service),
        environment=environment,
        source_sha256=record.source_sha256,
        title_vi=record.task_name_vi,
        title_en=record.task_name_en,
        scenario_source=record.scenario_source,
        inputs=inputs,
        output_hv_ids=list(record.output_hv_ids),
        output_is_unmaterialized=record.output_is_unmaterialized,
        score_items=list(record.score_items),
        aggregate=record.aggregate,
        output_schema_ref=output_schema_ref,
        scorer_ref=scorer_ref,
        tool_policy=tool_policy or ToolPolicy(),
        timeouts=timeouts or DEFAULT_TIMEOUTS[environment],
        invalidity=default_invalidity(environment),
        gate_semantics=default_gate_semantics(record.score_items, record.aggregate),
        adjudication_notes=adjudication_notes or [],
    )


def _align_descriptions(record: CatalogSubtask) -> list[str]:
    by_hv: dict[str, str] = {}
    for desc in record.input_descriptions_source:
        for hv in record.input_hv_ids:
            if hv in desc and hv not in by_hv:
                by_hv[hv] = desc
    return [by_hv.get(hv, hv) for hv in record.input_hv_ids]


class SubmissionEnvelope(StrictModel):
    """What a solver returns. `answer` is validated against the subtask output model by the runner."""

    schema_version: Literal[1] = 1
    episode_id: UUID
    subtask_id: SubtaskId
    agent_id: str = Field(min_length=1, max_length=64)
    answer: dict[str, Any]
    evidence_refs: list[str] = Field(default_factory=list, max_length=2000)
    abstain_reason: str | None = Field(default=None, max_length=1000)
    submitted_at: UtcDatetime
