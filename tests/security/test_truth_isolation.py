"""Security: sealed truth must not leak into agent-visible payloads; cross-episode denied."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saber.domain.errors import CrossEpisodeDenied, ValidationError
from saber.domain.runs import BLUE_FORBIDDEN_FIELDS
from saber.episodes import build_episode, write_episode
from saber.episodes.runner import run_oracle
from saber.subtasks import implemented_ids, load_subtask
from saber.subtasks._framework import assert_no_leak


@pytest.mark.security
def test_public_payload_has_no_truth_keys() -> None:
    for sid in implemented_ids():
        st = load_subtask(sid)
        for variant in st.VARIANTS:
            ep = build_episode(sid, variant=variant)
            public = ep.public_payload()
            assert_no_leak(public)
            text = json.dumps(public, default=str)
            # The sealed answer must never be byte-present in the public blob.
            for key in ("sealed_truth", "attack_verification", "scenario_id", "is_malicious"):
                assert f'"{key}"' not in text, (sid, variant, key)


# Subtasks where the agent must DECIDE a label (not merely report an observable fact). The decided
# label values must never be byte-present in the agent-visible payload.
_DECISION_FIELDS = {
    "T1112.001": ("verdict",),
    "T1112.002": ("verdict",),
    "T1112.003": ("classification", "claim_confirmed", "alert_claim"),
}


@pytest.mark.security
def test_decision_labels_not_byte_present_in_public() -> None:
    # Scan the agent-visible INPUTS only. The manifest's output schema legitimately lists the full
    # enum domain (e.g. both TP and FP) so the agent knows the valid answers; that is not a leak.
    for sid, fields in _DECISION_FIELDS.items():
        st = load_subtask(sid)
        for variant in st.VARIANTS:
            ep = build_episode(sid, variant=variant)
            inputs_text = json.dumps(ep.bundle.public_inputs, default=str)
            for field in fields:
                value = ep.bundle.sealed_truth[field]
                assert f'"{value}"' not in inputs_text, (sid, variant, field, value)


@pytest.mark.security
def test_decision_subtasks_are_discriminable_from_evidence() -> None:
    # The label must be INFERABLE from agent-visible evidence (B0 gets it right), proving it is
    # neither leaked verbatim nor unsolvable. Run the rules-only solver per class.
    for sid, fields in _DECISION_FIELDS.items():
        st = load_subtask(sid)
        for variant in st.VARIANTS:
            ep = build_episode(sid, variant=variant)
            solved = st.reference_solve(ep.bundle.public_inputs)
            assert solved is not None, sid
            answer, _ = solved
            for field in fields:
                assert answer[field] == ep.bundle.sealed_truth[field], (sid, variant, field)


@pytest.mark.security
def test_leak_guard_rejects_forbidden_key() -> None:
    assert "scenario_id" in BLUE_FORBIDDEN_FIELDS
    with pytest.raises(ValidationError):
        assert_no_leak({"inputs": [{"scenario_id": "x"}]})
    with pytest.raises(ValidationError):
        assert_no_leak({"labels": ["malicious"]})


@pytest.mark.security
def test_written_episode_separates_truth_from_public(tmp_path: Path) -> None:
    ep = build_episode("T1112.001", seed=1, variant="tp")
    write_episode(ep, tmp_path)
    public_dir = tmp_path / "public"
    sealed_dir = tmp_path / "sealed"
    # A Blue code path with only the public directory sees no truth file.
    assert not list(public_dir.rglob("*.sealed.json"))
    sealed = json.loads((sealed_dir / "truth.sealed.json").read_text(encoding="utf-8"))
    assert sealed["truth"]["verdict"] in {"TP", "FP"}
    manifest = json.loads((public_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "verdict" not in json.dumps(manifest["inputs"])


@pytest.mark.security
def test_cross_episode_submission_denied() -> None:
    ep_a = build_episode("T1112.001", seed=1, variant="tp")
    ep_b = build_episode("T1112.001", seed=2, variant="tp")
    res_b = run_oracle(ep_b)
    with pytest.raises(CrossEpisodeDenied):
        ep_a.subtask.grade(
            res_b.submission,
            ep_a.bundle.sealed_truth,
            episode_id=ep_a.bundle.episode_id,
            evidence_ids=ep_a.evidence_ids,
            truth_sha256=ep_a.truth_sha256,
        )


@pytest.mark.security
def test_hallucinated_citation_fails_gate() -> None:
    # A subtask whose aggregate includes a CITE gate would fail with fabricated references.
    # Pilot file tasks have no CITE gate, so this asserts the primitive behaviour directly.
    from saber.grading.primitives import verify_citations

    assert not verify_citations(["evidence-that-does-not-exist"], {"ev-1", "ev-2"}).passed
    assert verify_citations(["ev-1"], {"ev-1", "ev-2"}).passed
