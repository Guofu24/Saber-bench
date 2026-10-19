"""Gold pilot base: episode model, provenance, independent-verification contract, grading."""

from __future__ import annotations

import hashlib
import importlib
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import Field

from saber.domain.base import StrictModel, SubtaskId, UtcDatetime, deterministic_uuid
from saber.domain.subtask import SubmissionEnvelope
from saber.grading.results import ScoreResult
from saber.subtasks import load_subtask
from saber.subtasks._framework import SubtaskBase, sha256_of

Split = Literal["dev", "hidden"]


class Provenance(StrictModel):
    """How a gold artifact was produced, for reproducibility and audit."""

    builder: str  # dotted path of the builder that produced it
    method: str  # one-line description of how the artifact + truth were constructed
    independent_derivation: str  # how the truth was re-derived by a different route
    source_versions: dict[str, str] = Field(default_factory=dict)  # ATT&CK ver, format refs, etc.
    hard_negatives: list[str] = Field(
        default_factory=list
    )  # what benign/ambiguous traps are present
    adjudication_required: list[str] = Field(
        default_factory=list
    )  # labels/conventions needing a human
    labels: list[str] = Field(
        default_factory=lambda: [
            "GOLD_PILOT_V1",
            "SYNTHETIC_DOMAIN_FAITHFUL",
            "DEV_SIMULATION_ONLY",
        ]
    )


class GoldEpisode(StrictModel):
    """One gold evaluation episode: a realistic artifact + sealed, independently-derived truth."""

    schema_version: Literal[1] = 1
    subtask_id: SubtaskId
    split: Split
    episode_id: UUID
    public_inputs: dict[str, Any]  # agent-visible artifact (realistic)
    gold_truth: dict[str, Any]  # sealed; shape matches the subtask's scorer
    evidence_ids: list[str] = Field(default_factory=list)
    provenance: Provenance
    artifact_sha256: str
    created_at: UtcDatetime

    def public_payload_text(self) -> str:
        return sha256_of(self.public_inputs)


@dataclass
class VerificationResult:
    ok: bool
    detail: str
    cross_checked_fields: list[str] = field(default_factory=list)


class GoldPilot(ABC):
    """A curated gold evaluation pilot for one file-mode subtask."""

    SUBTASK_ID: ClassVar[str]
    SOURCE_VERSIONS: ClassVar[dict[str, str]] = {}
    # One-line description of the exact JSON object the solver must return (keys + value shapes),
    # used to build the LLM baseline prompt. Must match what grade() consumes.
    OUTPUT_SPEC: ClassVar[str] = ""

    def subtask(self) -> SubtaskBase:
        return load_subtask(self.SUBTASK_ID)

    def instructions(self) -> str:
        from saber.catalog.loader import default_catalog

        rec = default_catalog().subtask(self.SUBTASK_ID)
        return rec.scenario_source

    def episode_id_for(self, split: Split, seed: int) -> UUID:
        return deterministic_uuid("GOLD", self.SUBTASK_ID, split, str(seed))

    @abstractmethod
    def build(self, split: Split, seed: int) -> GoldEpisode: ...

    @abstractmethod
    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        """Re-derive/validate the gold truth from the artifact by a route distinct from the solver's.

        Must NOT reuse the structural generator's inference. Returns ok=True only when the
        independently-derived truth agrees with the sealed gold truth.
        """

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        """The correct answer in the subtask's output shape (for the gold oracle check)."""
        return dict(episode.gold_truth)

    def grade(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        *,
        agent_id: str,
        evidence_refs: list[str] | None = None,
    ) -> ScoreResult:
        st = self.subtask()
        sub = SubmissionEnvelope(
            episode_id=episode.episode_id,
            subtask_id=self.SUBTASK_ID,
            agent_id=agent_id,
            answer=dict(answer),
            evidence_refs=evidence_refs or [],
            submitted_at=datetime.now(UTC),
        )
        return st.grade(
            sub,
            episode.gold_truth,
            episode_id=episode.episode_id,
            evidence_ids=episode.evidence_ids,
            truth_sha256=sha256_of(episode.gold_truth),
            public_inputs=episode.public_inputs,
        )

    def _result(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        score: float,
        *,
        components: Any = (),
        gates: Any = (),
        trace: Any = (),
    ) -> ScoreResult:
        """Build a ScoreResult for a pilot with a faithful custom scorer (exact source formula)."""
        from saber.grading import SCORER_VERSION
        from saber.grading.results import ScoreResult as _SR

        s = min(1.0, max(0.0, score))
        return _SR(
            subtask_id=self.SUBTASK_ID,
            episode_id=episode.episode_id,
            score=s,
            raw_score=s,
            components=list(components),
            gates=list(gates),
            scorer_version=SCORER_VERSION,
            scorer_ref=f"gold:{self.SUBTASK_ID}@{SCORER_VERSION}",
            submission_sha256=sha256_of(dict(answer)),
            truth_sha256=sha256_of(episode.gold_truth),
            trace=list(trace),
            graded_at=datetime.now(UTC),
            labels=["GOLD_PILOT_V1"],
        )


def _artifact_hash(public_inputs: Mapping[str, Any]) -> str:
    return hashlib.sha256(sha256_of(public_inputs).encode()).hexdigest()


def finalize(
    subtask_id: str,
    split: Split,
    seed: int,
    public_inputs: dict[str, Any],
    gold_truth: dict[str, Any],
    provenance: Provenance,
    evidence_ids: list[str],
) -> GoldEpisode:
    return GoldEpisode(
        subtask_id=subtask_id,
        split=split,
        episode_id=deterministic_uuid("GOLD", subtask_id, split, str(seed)),
        public_inputs=public_inputs,
        gold_truth=gold_truth,
        evidence_ids=evidence_ids,
        provenance=provenance,
        artifact_sha256=_artifact_hash(public_inputs),
        created_at=datetime(2026, 10, 19, tzinfo=UTC),
    )


_PILOT_IDS = [
    "T1112.002",
    "T1348.002",
    "T1387.002",
    "T0020.001",
    "T1406.001",
    "T1111.002",
    "T2013.001",
    "T1102.002",
    "T0167.002",
    "T0173.002",
    "T0397.002",
    "T1324.002",
]


def pilot_ids() -> list[str]:
    return list(_PILOT_IDS)


def load_pilot(subtask_id: str) -> GoldPilot:
    mod_name = "g" + subtask_id[1:].replace(".", "_")
    mod = importlib.import_module(f"saber.gold.pilots.{mod_name}")
    cls = mod.Pilot
    instance: GoldPilot = cls()
    if subtask_id != instance.SUBTASK_ID:
        raise ValueError(f"pilot module declares {instance.SUBTASK_ID}, expected {subtask_id}")
    return instance
