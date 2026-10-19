"""Parametrized contract tests over ALL 175 catalog subtasks (bespoke modules + engine).

Each subtask must: load, build a deterministic episode, have its evaluator oracle reach full
credit and stay VALID, keep the agent-visible payload free of truth keys, reject a cross-episode
submission, and score an empty submission no higher than a correct one. This is the execution
evidence that every subtask is runnable, not a placeholder.
"""

from __future__ import annotations

import pytest

from saber.catalog import load_catalog
from saber.domain.errors import CrossEpisodeDenied
from saber.episodes import build_episode
from saber.episodes.runner import run_oracle, run_reference, run_stub
from saber.subtasks import load_subtask

_ALL_IDS = [s.id for s in load_catalog().subtasks]


@pytest.mark.parametrize("subtask_id", _ALL_IDS)
def test_subtask_oracle_full_credit_and_valid(subtask_id: str) -> None:
    st = load_subtask(subtask_id)
    for seed in (1, 42):
        ep = build_episode(subtask_id, seed, st.VARIANTS[0])
        res = run_oracle(ep)
        assert res.score.validity.value == "VALID", (subtask_id, seed, res.score.invalid_reason)
        assert abs(res.score.score - 1.0) < 1e-9, (
            subtask_id,
            seed,
            res.score.score,
            res.score.trace[:4],
        )
        assert res.score.scorer_version == "score_v1"


@pytest.mark.parametrize("subtask_id", _ALL_IDS)
def test_subtask_deterministic(subtask_id: str) -> None:
    a = build_episode(subtask_id, 7, load_subtask(subtask_id).VARIANTS[0])
    b = build_episode(subtask_id, 7, load_subtask(subtask_id).VARIANTS[0])
    assert a.bundle.episode_id == b.bundle.episode_id
    assert a.truth_sha256 == b.truth_sha256
    assert a.manifest.model_dump(mode="json") == b.manifest.model_dump(mode="json")


@pytest.mark.parametrize("subtask_id", _ALL_IDS)
def test_subtask_no_truth_key_in_public(subtask_id: str) -> None:
    st = load_subtask(subtask_id)
    ep = build_episode(subtask_id, 3, st.VARIANTS[0])
    import json

    blob = json.dumps(ep.public_payload()["inputs"], default=str)
    for key in ("sealed_truth", "scenario_id", "attack_verification", "is_malicious"):
        assert f'"{key}"' not in blob, (subtask_id, key)


@pytest.mark.parametrize("subtask_id", _ALL_IDS)
def test_subtask_cross_episode_denied(subtask_id: str) -> None:
    st = load_subtask(subtask_id)
    ep_a = build_episode(subtask_id, 1, st.VARIANTS[0])
    ep_b = build_episode(subtask_id, 2, st.VARIANTS[0])
    res_b = run_oracle(ep_b)
    with pytest.raises(CrossEpisodeDenied):
        ep_a.subtask.grade(
            res_b.submission,
            ep_a.bundle.sealed_truth,
            episode_id=ep_a.bundle.episode_id,
            evidence_ids=ep_a.evidence_ids,
            truth_sha256=ep_a.truth_sha256,
        )


@pytest.mark.parametrize("subtask_id", _ALL_IDS)
def test_empty_not_better_than_oracle(subtask_id: str) -> None:
    st = load_subtask(subtask_id)
    ep = build_episode(subtask_id, 5, st.VARIANTS[0])
    oracle = run_oracle(ep).score.score
    for gc in st.golden_cases(ep.bundle):
        if gc.answer is None:
            continue
        res = run_stub(ep, gc.answer, gc.evidence_refs)
        if gc.expected_score is not None:
            assert abs(res.score.score - gc.expected_score) < 1e-9, (
                subtask_id,
                gc.name,
                res.score.score,
            )
        if gc.expected_max is not None:
            assert res.score.score <= gc.expected_max + 1e-9, (subtask_id, gc.name, res.score.score)
        assert res.score.score <= oracle + 1e-9, (subtask_id, gc.name)


def test_every_catalog_subtask_is_implemented() -> None:
    from saber.subtasks import implemented_ids

    assert set(implemented_ids()) == set(_ALL_IDS)
    assert len(_ALL_IDS) == 175


def test_gate_multipliers_have_backing_gate_items() -> None:
    # Invariant: a source formula that multiplies by a hard gate (× [X] / × CITE / Π[...]) must have
    # a gate-marked score item backing it, so the engine (which binds gates from per-item is_gate)
    # never leaves a hard gate always-pass. FIXED_ITEM products ([A] × [B]) are excluded: there the
    # bracketed terms are scored factors, handled by the product, not gates.
    import re

    from saber.catalog.models import AggregateKind, ScoreItemKind

    bad = []
    for s in load_catalog().subtasks:
        if s.aggregate and s.aggregate.kind is AggregateKind.FIXED_ITEM:
            continue
        f = s.score_aggregate_source
        has_gate_mult = bool(
            re.search(r"×\s*\[", f) or "× CITE" in f or "Π[" in f or "nhân CITE" in f
        )
        has_gate_item = any(
            i.is_gate or i.kind in (ScoreItemKind.GATE, ScoreItemKind.CITE) for i in s.score_items
        )
        if has_gate_mult and not has_gate_item:
            bad.append((s.id, f))
    assert not bad, bad


def test_reference_baseline_runs_where_present() -> None:
    # Spot-check that the rules reference is wired for a sample across families (not all have one).
    present = 0
    for sid in ("T1085.001", "T1347.001", "T0167.001", "T1053.001"):
        ep = build_episode(sid, 1, load_subtask(sid).VARIANTS[0])
        if run_reference(ep) is not None:
            present += 1
    assert present >= 1
