"""Archetype-engine robustness: scoring fails closed on malformed input and stays sandboxed."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from saber.catalog import load_catalog
from saber.domain.subtask import SubmissionEnvelope
from saber.episodes import build_episode
from saber.episodes.runner import run_oracle
from saber.grading.results import ScoreResult
from saber.subtasks import bespoke_ids, load_subtask


def _state_subtask_id() -> str:
    cat = load_catalog()
    bespoke = set(bespoke_ids())
    for s in cat.subtasks:
        if s.id in bespoke:
            continue
        st = load_subtask(s.id)
        if getattr(st, "_state_mode", False):
            return s.id
    raise AssertionError("no engine state-mode subtask found")


def _grade_raw(subtask_id: str, answer: dict) -> ScoreResult:
    st = load_subtask(subtask_id)
    ep = build_episode(subtask_id, 1, st.VARIANTS[0])
    sub = SubmissionEnvelope(
        episode_id=ep.bundle.episode_id,
        subtask_id=subtask_id,
        agent_id="adversary",
        answer=answer,
        submitted_at=datetime.now(UTC),
    )
    return st.grade(
        sub,
        ep.bundle.sealed_truth,
        episode_id=ep.bundle.episode_id,
        evidence_ids=ep.evidence_ids,
        truth_sha256=ep.truth_sha256,
        public_inputs=ep.bundle.public_inputs,
    )


@pytest.mark.security
def test_state_mode_malformed_actions_fail_closed() -> None:
    sid = _state_subtask_id()
    for bad in (
        {"actions": [{"op": "chmod", "path": "/x"}], "observations": {}},
        {"actions": ["notadict"], "observations": {}},
        {"actions": [], "observations": {"suspicious": 5}},
        {"actions": [{"op": "remove"}], "observations": {}},
    ):
        res = _grade_raw(sid, bad)
        assert isinstance(res, ScoreResult)
        assert res.score == 0.0, (bad, res.trace)
        assert res.scorer_version == "score_v1"


@pytest.mark.security
def test_state_oracle_still_full_credit() -> None:
    sid = _state_subtask_id()
    ep = build_episode(sid, 1, load_subtask(sid).VARIANTS[0])
    assert abs(run_oracle(ep).score.score - 1.0) < 1e-9


@pytest.mark.security
def test_exec_engine_only_uses_subprocess_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    # The archetype exec path must never route agent content to the in-process filter/yara engines.
    import saber.subtasks._auto.exec_state as es

    called = {"filter": 0, "yara": 0}

    def _boom_filter(*a: object, **k: object) -> object:
        called["filter"] += 1
        raise AssertionError("evaluate_filter must not be reached by the engine")

    def _boom_yara(*a: object, **k: object) -> object:
        called["yara"] += 1
        raise AssertionError("run_yara_subset must not be reached by the engine")

    monkeypatch.setattr("saber.grading.execsandbox.evaluate_filter", _boom_filter, raising=False)
    monkeypatch.setattr("saber.grading.execsandbox.run_yara_subset", _boom_yara, raising=False)

    cat = load_catalog()
    bespoke = set(bespoke_ids())
    exec_ids = [
        s.id
        for s in cat.subtasks
        if s.id not in bespoke and getattr(load_subtask(s.id), "_exec_mode", False)
    ]
    assert exec_ids, "expected engine exec-mode subtasks"
    for sid in exec_ids[:4]:
        ep = build_episode(sid, 1, load_subtask(sid).VARIANTS[0])
        run_oracle(ep)
    assert called == {"filter": 0, "yara": 0}
    assert es  # module imported
