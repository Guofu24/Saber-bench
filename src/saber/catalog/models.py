"""Typed views over catalog/*.json. Fields suffixed `_source` are verbatim from the HTML."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from saber.domain.base import NiceId, Sha256Hex, StrictModel, SubtaskId

Service = Literal["MON", "CNT", "HUNT", "IR"]
Environment = Literal["file", "soc", "vm"]


class ScoreItemKind(StrEnum):
    ENUM = "enum"
    SET = "set"
    ORDER = "order"
    NUMERIC = "numeric"
    CITE = "cite"
    GATE = "gate"
    STATE = "state"
    EXEC = "exec"
    RULE = "rule"


class AggregateKind(StrEnum):
    FIXED_ITEM = "fixed_item"
    WEIGHTED_SUM = "weighted_sum"
    SET_DELTA = "set_delta"
    FBETA = "fbeta"
    KENDALL_TAU = "kendall_tau"
    ACCURACY = "accuracy"
    MACRO_AVERAGE = "macro_average"
    PRODUCT_GATES = "product_gates"
    FRACTION_CORRECT = "fraction_correct"
    TPR_MINUS_FPR = "tpr_minus_fpr"
    DELTA_FP_TP = "delta_fp_tp"
    TECHNIQUE_TACTIC = "technique_tactic"
    MIXTURE = "mixture"
    CUSTOM = "custom"


class ParsedScoreItem(StrictModel):
    """Structured reading of one source item such as ``targeted[] · setF2/host · 0.7``."""

    field: str
    kind: ScoreItemKind
    subtype: str | None = None
    weight: float | None = Field(default=None, ge=0.0, le=1.0)
    is_gate: bool = False
    gate_mode: Literal["zero", "factor", "cap", "per_element"] | None = None
    gate_factor: float | None = Field(default=None, ge=0.0, le=1.0)
    is_penalty: bool = False
    penalty_per_item: float | None = Field(default=None, ge=0.0, le=1.0)
    beta: float | None = None
    tolerance: str | None = None
    weight_note: str | None = None
    raw: str


class CapRule(StrictModel):
    condition: str
    cap: float = Field(ge=0.0, le=1.0)


class PenaltyRule(StrictModel):
    count_of: str
    per_item: float = Field(ge=0.0, le=1.0)


class MixtureTerm(StrictModel):
    weight: float = Field(ge=0.0, le=1.0)
    kind: AggregateKind
    note: str = ""


class ParsedAggregate(StrictModel):
    kind: AggregateKind
    source_formula: str
    gates: list[str] = Field(default_factory=list)
    caps: list[CapRule] = Field(default_factory=list)
    penalties: list[PenaltyRule] = Field(default_factory=list)
    mixture: list[MixtureTerm] = Field(default_factory=list)
    partial_credit: float | None = None
    beta: float | None = None
    notes: list[str] = Field(default_factory=list)


class CatalogSubtask(StrictModel):
    id: SubtaskId
    nice_id: NiceId
    source_task_id: str
    service: Service
    service_name: str
    task_name_vi: str
    task_name_en: str
    environment: Environment
    systems: list[str]
    source_existing_count_raw: str
    scenario_source: str
    input_descriptions_source: list[str]
    input_hv_ids: list[str]
    output_descriptions_source: list[str]
    output_hv_ids: list[str]
    output_is_unmaterialized: bool
    score_items_source: list[str]
    score_aggregate_source: str
    group_source: str | None
    note_source: str
    score_implementation_status: str
    fixture_implementation_status: str
    source_sha256: Sha256Hex
    # Derived, structured readings (not source text):
    score_items: list[ParsedScoreItem] = Field(default_factory=list)
    aggregate: ParsedAggregate | None = None


class CatalogTask(StrictModel):
    nice_id: NiceId
    source_task_id: str
    service: Service
    task_name_vi: str
    task_name_en: str
    role_id: str
    role_name_vi: str
    source_review: str
    source_activity: str
    source_output: str
    source_sla: str
    benchmark_tier: str
    review_state: str
    source_product_dependency: bool
    subtask_ids: list[SubtaskId]


class CatalogArtifact(StrictModel):
    id: str = Field(pattern=r"^HV-\d{2}$")
    name: str
    scope: Literal["case_or_episode", "shared_environment", "per_period"]


class CatalogMetadata(StrictModel):
    source_file: str
    source_sha256: Sha256Hex
    nice_task_count: int
    subtask_count: int
    artifact_type_count: int
    environment_breakdown: dict[str, int]
    primary_service_breakdown: dict[str, dict[str, int]]
    dropped_tasks_count: int
