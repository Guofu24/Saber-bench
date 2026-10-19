"""Shared helpers for per-subtask tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from saber.episodes import build_episode
from saber.episodes.builder import BuiltEpisode
from saber.episodes.runner import run_oracle, run_reference, run_stub
from saber.grading.results import Validity
from saber.subtasks import load_subtask
from saber.subtasks._framework import GoldenCase, SubtaskBase


def iter_variants_seeds(
    subtask: SubtaskBase, seeds: tuple[int, ...] = (1, 42)
) -> Iterator[tuple[str, int]]:
    for variant in subtask.VARIANTS:
        for seed in seeds:
            yield variant, seed


def check_subtask(subtask_id: str, *, seeds: tuple[int, ...] = (1, 42)) -> None:
    """Standard contract every implemented subtask must satisfy."""
    subtask = load_subtask(subtask_id)
    spec = subtask.spec()
    assert spec.id == subtask_id
    assert subtask.output_schema()["type"] == "object"
    for variant, seed in iter_variants_seeds(subtask, seeds):
        ep = build_episode(subtask_id, seed, variant)
        _check_build(ep)
        _check_oracle(subtask_id, ep)
        _check_determinism(subtask_id, seed, variant, ep)
        _check_cross_episode(subtask_id, ep)
        ref = run_reference(ep)
        if ref is not None:
            assert ref.score.validity is Validity.VALID
        for gc in subtask.golden_cases(ep.bundle):
            _check_golden(subtask, ep, gc)


def _check_build(ep: BuiltEpisode) -> None:
    from saber.domain.runs import BLUE_FORBIDDEN_FIELDS

    manifest = ep.manifest.model_dump(mode="json")
    for forbidden in BLUE_FORBIDDEN_FIELDS:
        assert f"'{forbidden}'" not in str(manifest), forbidden
    assert ep.manifest.episode_id == ep.bundle.episode_id
    assert len(ep.manifest.inputs) == len(ep.subtask.spec().inputs)


def _check_oracle(subtask_id: str, ep: BuiltEpisode) -> None:
    res = run_oracle(ep)
    assert res.score.validity is Validity.VALID, (subtask_id, res.score.invalid_reason)
    assert abs(res.score.score - 1.0) < 1e-9, (subtask_id, res.score.score, res.score.trace)
    assert res.score.scorer_version == "score_v1"
    assert res.score.submission_sha256 and res.score.truth_sha256


def _check_determinism(subtask_id: str, seed: int, variant: str, ep: BuiltEpisode) -> None:
    again = build_episode(subtask_id, seed, variant)
    assert again.bundle.episode_id == ep.bundle.episode_id
    assert again.truth_sha256 == ep.truth_sha256
    assert again.manifest.model_dump(mode="json") == ep.manifest.model_dump(mode="json")


def _check_cross_episode(subtask_id: str, ep: BuiltEpisode) -> None:
    from saber.domain.errors import CrossEpisodeDenied

    res = run_oracle(ep)
    tampered = res.submission.model_copy(update={"episode_id": _OTHER_UUID})
    with pytest.raises(CrossEpisodeDenied):
        ep.subtask.grade(
            tampered,
            ep.bundle.sealed_truth,
            episode_id=ep.bundle.episode_id,
            evidence_ids=ep.evidence_ids,
            truth_sha256=ep.truth_sha256,
        )


def _check_golden(subtask: SubtaskBase, ep: BuiltEpisode, gc: GoldenCase) -> None:
    if gc.answer is None:
        return
    res = run_stub(ep, gc.answer, gc.evidence_refs)
    s = res.score.score
    if gc.expected_score is not None:
        assert abs(s - gc.expected_score) < 1e-9, (gc.name, s, gc.expected_score, res.score.trace)
    if gc.expected_min is not None:
        assert s >= gc.expected_min - 1e-9, (gc.name, s)
    if gc.expected_max is not None:
        assert s <= gc.expected_max + 1e-9, (gc.name, s)
    if gc.expected_validity is not None:
        assert res.score.validity is gc.expected_validity, (gc.name, res.score.validity)
    if gc.expect_trace_contains:
        assert any(gc.expect_trace_contains in t for t in res.score.trace), (
            gc.name,
            res.score.trace,
        )


_OTHER_UUID = __import__("uuid").UUID("deadbeef-0000-4000-8000-000000000000")
