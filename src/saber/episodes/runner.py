"""Run a submission against a built episode and grade it.

Two built-in solvers for DEV: a truth-reading "oracle" (proves the scorer awards full credit on
the intended answer) and the subtask's rules-only reference (`reference_solve`, the B0 baseline).
Neither is a model; real agent solvers plug in later via the orchestration layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from saber.domain.subtask import SubmissionEnvelope
from saber.episodes.builder import BuiltEpisode
from saber.grading.results import ScoreResult


@dataclass(frozen=True)
class EpisodeResult:
    episode: BuiltEpisode
    submission: SubmissionEnvelope
    score: ScoreResult


def _envelope(
    episode: BuiltEpisode, agent_id: str, answer: dict[str, Any], evidence_refs: list[str]
) -> SubmissionEnvelope:
    return SubmissionEnvelope(
        episode_id=episode.bundle.episode_id,
        subtask_id=episode.subtask.SUBTASK_ID,
        agent_id=agent_id,
        answer=answer,
        evidence_refs=evidence_refs,
        submitted_at=datetime.now(UTC),
    )


def grade_submission(
    episode: BuiltEpisode, submission: SubmissionEnvelope, *, graded_at: datetime | None = None
) -> ScoreResult:
    return episode.subtask.grade(
        submission,
        episode.bundle.sealed_truth,
        episode_id=episode.bundle.episode_id,
        evidence_ids=episode.evidence_ids,
        truth_sha256=episode.truth_sha256,
        public_inputs=episode.bundle.public_inputs,
        graded_at=graded_at,
    )


def run_oracle(episode: BuiltEpisode, *, graded_at: datetime | None = None) -> EpisodeResult:
    """Solve from sealed truth (evaluator-side sanity check that the scorer can reach full credit)."""
    subtask = episode.subtask
    answer = subtask.answer_from_truth(episode.bundle.sealed_truth)
    refs = subtask.perfect_evidence_refs(episode.bundle)
    sub = _envelope(episode, "oracle", answer, refs)
    return EpisodeResult(
        episode=episode, submission=sub, score=grade_submission(episode, sub, graded_at=graded_at)
    )


def run_reference(
    episode: BuiltEpisode, *, graded_at: datetime | None = None
) -> EpisodeResult | None:
    """Solve from agent-visible inputs only (B0 rules-only baseline). None if not provided."""
    solved = episode.subtask.reference_solve(episode.bundle.public_inputs)
    if solved is None:
        return None
    answer, refs = solved
    sub = _envelope(episode, "rules_baseline", answer, refs)
    return EpisodeResult(
        episode=episode, submission=sub, score=grade_submission(episode, sub, graded_at=graded_at)
    )


def run_stub(
    episode: BuiltEpisode,
    answer: dict[str, Any],
    evidence_refs: list[str] | None = None,
    *,
    graded_at: datetime | None = None,
) -> EpisodeResult:
    sub = _envelope(episode, "stub", answer, evidence_refs or [])
    return EpisodeResult(
        episode=episode, submission=sub, score=grade_submission(episode, sub, graded_at=graded_at)
    )
