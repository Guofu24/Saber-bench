"""Shared machinery for subtask modules: fixtures, public manifest, grading composition."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from saber.catalog import CatalogSubtask
from saber.catalog.loader import default_catalog
from saber.catalog.models import ScoreItemKind
from saber.domain.base import StrictModel, SubtaskId, UtcDatetime, deterministic_uuid
from saber.domain.errors import CrossEpisodeDenied, ValidationError
from saber.domain.runs import BLUE_FORBIDDEN_FIELDS
from saber.domain.subtask import (
    SubmissionEnvelope,
    SubtaskSpecV1,
    Timeouts,
    ToolPolicy,
    spec_from_catalog,
)
from saber.grading import SCORER_VERSION
from saber.grading.canonical import canonicalizer_for
from saber.grading.primitives import (
    apply_gates,
    apply_penalty,
    score_enum,
    score_numeric,
    score_order,
    score_set,
    score_set_delta,
    verify_citations,
)
from saber.grading.results import GateOutcome, ItemScore, PenaltyApplied, ScoreResult, Validity

DEV_FIXTURE_LABEL = "DEV_FIXTURE"


def canonical_json(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def assert_no_leak(obj: Any, *, path: str = "$") -> None:
    """Reject evaluator-only keys anywhere inside an agent-visible structure."""
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            if str(key) in BLUE_FORBIDDEN_FIELDS:
                raise ValidationError(
                    f"agent-visible payload leaks forbidden key {key!r} at {path}"
                )
            assert_no_leak(value, path=f"{path}.{key}")
    elif isinstance(obj, list | tuple):
        for i, value in enumerate(obj):
            assert_no_leak(value, path=f"{path}[{i}]")


class ManifestInput(StrictModel):
    hv_id: str = Field(pattern=r"^HV-\d{2}$")
    description: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicManifest(StrictModel):
    """Agent-visible episode description. Contains no labels, seed, or scenario family."""

    schema_version: Literal[1] = 1
    episode_id: UUID
    subtask_id: SubtaskId
    service: str
    environment: str
    task_version: str
    instructions: str
    inputs: list[ManifestInput]
    output_schema_ref: str
    output_schema: dict[str, Any]
    tool_policy: ToolPolicy
    budget_tool_calls: int = Field(ge=0)
    deadline_at: UtcDatetime
    provenance_tags: list[str] = Field(default_factory=lambda: [DEV_FIXTURE_LABEL])


class FixtureBundle(StrictModel):
    """Output of a module's fixture builder. `sealed_truth` is evaluator-only."""

    subtask_id: SubtaskId
    seed: int
    variant: str
    episode_id: UUID
    public_inputs: dict[str, Any]
    sealed_truth: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    expected_reference_score: float | None = 1.0
    labels: list[str] = Field(default_factory=lambda: [DEV_FIXTURE_LABEL])


@dataclass
class GradeContext:
    evidence_ids: set[str]
    spec: SubtaskSpecV1
    public_inputs: dict[str, Any] | None = None


@dataclass
class ScoreParts:
    components: list[ItemScore] = field(default_factory=list)
    gates: list[GateOutcome] = field(default_factory=list)
    penalties: list[tuple[str, int, float]] = field(default_factory=list)
    raw_score: float | None = None
    trace: list[str] = field(default_factory=list)

    def weighted(self) -> float:
        total = 0.0
        for c in self.components:
            if c.weight is not None:
                total += c.weight * c.score
        return min(1.0, max(0.0, total))


@dataclass
class GoldenCase:
    name: str
    answer: dict[str, Any] | None
    evidence_refs: list[str] = field(default_factory=list)
    expected_score: float | None = None
    expected_min: float | None = None
    expected_max: float | None = None
    expected_validity: Validity = Validity.VALID
    expect_trace_contains: str | None = None


def item(
    field_name: str, score: float, weight: float | None, detail: Mapping[str, Any] | None = None
) -> ItemScore:
    return ItemScore(
        field=field_name, score=min(1.0, max(0.0, score)), weight=weight, detail=dict(detail or {})
    )


class SubtaskBase(ABC):
    SUBTASK_ID: ClassVar[str]
    OutputModel: ClassVar[type[BaseModel]]
    TASK_VERSION: ClassVar[str] = "1.0.0"
    TOOL_POLICY: ClassVar[ToolPolicy | None] = None
    TIMEOUTS: ClassVar[Timeouts | None] = None
    ADJUDICATION_NOTES: ClassVar[list[str]] = []
    VARIANTS: ClassVar[tuple[str, ...]] = ("default",)

    @classmethod
    def record(cls) -> CatalogSubtask:
        return default_catalog().subtask(cls.SUBTASK_ID)

    @classmethod
    def spec(cls) -> SubtaskSpecV1:
        module = cls.__module__
        return spec_from_catalog(
            cls.record(),
            output_schema_ref=f"{module}:{cls.OutputModel.__name__}",
            scorer_ref=f"grader:{cls.SUBTASK_ID}@{SCORER_VERSION}",
            tool_policy=cls.TOOL_POLICY,
            timeouts=cls.TIMEOUTS,
            adjudication_notes=list(cls.ADJUDICATION_NOTES),
        )

    @classmethod
    def output_schema(cls) -> dict[str, Any]:
        return cls.OutputModel.model_json_schema()

    @classmethod
    def episode_id_for(cls, seed: int, variant: str) -> UUID:
        return deterministic_uuid(cls.SUBTASK_ID, cls.TASK_VERSION, str(seed), variant)

    @abstractmethod
    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle: ...

    @abstractmethod
    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def score_parts(
        self, answer: BaseModel, truth: Mapping[str, Any], ctx: GradeContext
    ) -> ScoreParts: ...

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        """Rules-only oracle over agent-visible inputs (B0 baseline). None if not provided."""
        return None

    def perfect_evidence_refs(self, bundle: FixtureBundle) -> list[str]:
        return list(bundle.evidence_ids)

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        return []

    def grade(
        self,
        submission: SubmissionEnvelope,
        truth: Mapping[str, Any],
        *,
        episode_id: UUID,
        evidence_ids: Iterable[str],
        truth_sha256: str,
        public_inputs: Mapping[str, Any] | None = None,
        graded_at: datetime | None = None,
    ) -> ScoreResult:
        if submission.episode_id != episode_id:
            raise CrossEpisodeDenied("submission episode_id does not match the graded episode")
        if submission.subtask_id != self.SUBTASK_ID:
            raise ValidationError(
                f"submission is for {submission.subtask_id}, grader is {self.SUBTASK_ID}"
            )
        spec = self.spec()
        ctx = GradeContext(
            evidence_ids={str(e) for e in evidence_ids},
            spec=spec,
            public_inputs=dict(public_inputs or {}),
        )
        sub_hash = sha256_of(
            {
                "answer": submission.answer,
                "evidence_refs": submission.evidence_refs,
                "abstain": submission.abstain_reason,
            }
        )
        now = graded_at or datetime.now(UTC)
        base = dict(
            subtask_id=self.SUBTASK_ID, episode_id=episode_id, scorer_version=SCORER_VERSION,
            scorer_ref=spec.scorer_ref, submission_sha256=sub_hash, truth_sha256=truth_sha256, graded_at=now,
        )  # fmt: skip
        try:
            answer = self.OutputModel.model_validate(submission.answer)
        except PydanticValidationError as exc:
            trace = [
                "schema_invalid_submission: "
                + "; ".join(str(e.get("msg", "")) for e in exc.errors()[:5])
            ]
            return ScoreResult(score=0.0, raw_score=0.0, trace=trace, **base)
        parts = self.score_parts(answer, truth, ctx)
        raw = parts.raw_score if parts.raw_score is not None else parts.weighted()
        raw = min(1.0, max(0.0, raw))
        score = raw
        penalties: list[PenaltyApplied] = []
        trace = list(parts.trace)
        for name, count, per_item in parts.penalties:
            score, applied = apply_penalty(score, name, count, per_item)
            penalties.append(applied)
            trace.append(f"penalty {name}: {count} x {per_item} -> -{applied.deducted:.3f}")
        score, validity, invalid_reason, gate_trace = apply_gates(score, parts.gates)
        trace.extend(gate_trace)
        caps = [g.name for g in parts.gates if not g.passed and g.mode == "cap"]
        return ScoreResult(
            score=score, raw_score=raw, validity=validity, invalid_reason=invalid_reason,
            components=parts.components, gates=parts.gates, caps_applied=caps,
            penalties_applied=penalties, trace=trace, **base,
        )  # fmt: skip

    def _item(self, field_name: str) -> Any:
        for it in self.record().score_items:
            if it.field.rstrip("[]{}") == field_name.rstrip("[]{}") or it.field == field_name:
                return it
        raise ValidationError(f"{self.SUBTASK_ID}: field {field_name!r} is not a source score item")

    def _weight(self, field_name: str) -> float | None:
        it = self._item(field_name)
        weight: float | None = it.weight
        return weight

    def enum_item(
        self,
        field_name: str,
        pred: Any,
        truth: Any,
        *,
        aliases: Mapping[str, str] | None = None,
        valid_labels: Iterable[str] | None = None,
        weight: float | None = None,
    ) -> ItemScore:
        s, d = score_enum(
            pred, truth, aliases=aliases, valid_labels=list(valid_labels) if valid_labels else None
        )
        return item(field_name, s, weight if weight is not None else self._weight(field_name), d)

    def set_item(
        self,
        field_name: str,
        pred: Any,
        truth: Any,
        *,
        subtype: str | None = None,
        beta: float | None = None,
        weight: float | None = None,
        canon: Callable[[Any], str] | None = None,
    ) -> ItemScore:
        it = self._item(field_name)
        fn = canon or canonicalizer_for(subtype or it.subtype)
        res = score_set(pred, truth, canon=fn, beta=beta if beta is not None else (it.beta or 1.0))
        return item(
            field_name, res.score, weight if weight is not None else it.weight, res.detail()
        )

    def delta_item(
        self,
        field_name: str,
        pred: Any,
        truth: Any,
        *,
        subtype: str | None = None,
        weight: float | None = None,
        canon: Callable[[Any], str] | None = None,
    ) -> ItemScore:
        it = self._item(field_name)
        fn = canon or canonicalizer_for(subtype or it.subtype)
        res = score_set_delta(pred, truth, canon=fn)
        return item(
            field_name, res.score, weight if weight is not None else it.weight, res.detail()
        )

    def order_item(
        self,
        field_name: str,
        pred: Any,
        truth: Any,
        *,
        mode: str = "tau",
        subtype: str | None = None,
        weight: float | None = None,
        canon: Callable[[Any], str] | None = None,
    ) -> ItemScore:
        it = self._item(field_name)
        fn = canon or canonicalizer_for(subtype or it.subtype or "text")
        res = score_order(pred, truth, canon=fn, mode=mode)
        return item(
            field_name, res.score, weight if weight is not None else it.weight, res.detail()
        )

    def set_partial_item(
        self,
        field_name: str,
        pred: Any,
        truth: Any,
        *,
        key_canon: Callable[[Any], str],
        attr_canon: Callable[[Any], str],
        partial: float = 0.5,
        beta: float | None = None,
        weight: float | None = None,
    ) -> ItemScore:
        from saber.grading.primitives import score_set_partial

        it = self._item(field_name)
        res = score_set_partial(
            pred or [], truth, key_canon=key_canon, attr_canon=attr_canon,
            partial=partial, beta=beta if beta is not None else (it.beta or 1.0),
        )  # fmt: skip
        return item(
            field_name, res.score, weight if weight is not None else it.weight, res.detail()
        )

    def technique_item(
        self,
        field_name: str,
        pred: Any,
        truth: Any,
        tactic_of: Mapping[str, str],
        *,
        weight: float | None = None,
    ) -> ItemScore:
        from saber.grading.primitives import technique_tactic_score

        s, d = technique_tactic_score(pred, truth, tactic_of)
        return item(field_name, s, weight if weight is not None else self._weight(field_name), d)

    def numeric_item(
        self,
        field_name: str,
        pred: Any,
        truth: Any,
        *,
        tolerance: str | None = None,
        weight: float | None = None,
    ) -> ItemScore:
        it = self._item(field_name)
        s, d = score_numeric(pred, truth, tolerance or it.tolerance)
        return item(field_name, s, weight if weight is not None else it.weight, d)

    def cite_gate(
        self, refs: Iterable[str] | None, ctx: GradeContext, *, name: str = "CITE"
    ) -> GateOutcome:
        res = verify_citations(refs, ctx.evidence_ids)
        reason = (
            "all citations resolve"
            if res.passed
            else f"unresolved={res.invalid[:3]} valid={len(res.valid)}"
        )
        return GateOutcome(name=name, passed=res.passed, mode="zero", reason=reason)

    @staticmethod
    def gate(
        name: str,
        passed: bool,
        reason: str,
        *,
        mode: Literal["zero", "factor", "cap", "invalid", "per_element"] = "zero",
        factor: float | None = None,
    ) -> GateOutcome:
        return GateOutcome(name=name, passed=passed, mode=mode, factor=factor, reason=reason)

    def source_gate_items(self) -> list[Any]:
        return [i for i in self.record().score_items if i.is_gate or i.kind is ScoreItemKind.GATE]
