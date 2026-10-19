"""Gold Evaluation Pilot v1 contract: independent verification, oracle, leakage, contamination."""

from __future__ import annotations

import json

import pytest

from saber.gold import load_pilot, pilot_ids

_LABEL_GIVEAWAY_KEYS = (
    "verdict",
    "label",
    "labels",
    "malicious",
    "is_malicious",
    "answer",
    "flagged",
    "truth",
    "gold",
    "fp_cause",
)


@pytest.mark.parametrize("subtask_id", pilot_ids())
def test_independent_verification_passes(subtask_id: str) -> None:
    p = load_pilot(subtask_id)
    for split in ("dev", "hidden"):
        for seed in (1, 2, 3):
            ep = p.build(split, seed)  # type: ignore[arg-type]
            v = p.independent_verify(ep)
            assert v.ok, (subtask_id, split, seed, v.detail)
            assert v.cross_checked_fields, (subtask_id, "no fields cross-checked")


@pytest.mark.parametrize("subtask_id", pilot_ids())
def test_gold_oracle_reaches_full_credit(subtask_id: str) -> None:
    p = load_pilot(subtask_id)
    for split in ("dev", "hidden"):
        ep = p.build(split, 1)  # type: ignore[arg-type]
        res = p.grade(ep, p.answer_from_gold(ep), agent_id="gold_oracle")
        assert abs(res.score - 1.0) < 1e-9, (subtask_id, split, res.score, res.trace)


@pytest.mark.parametrize("subtask_id", pilot_ids())
def test_no_label_giveaway_key_in_public(subtask_id: str) -> None:
    p = load_pilot(subtask_id)
    ep = p.build("dev", 1)  # type: ignore[arg-type]

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert str(k).lower() not in _LABEL_GIVEAWAY_KEYS, (subtask_id, k)
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(ep.public_inputs)


@pytest.mark.parametrize("subtask_id", pilot_ids())
def test_dev_hidden_are_distinct_instances(subtask_id: str) -> None:
    # This is a DISTINCT-INSTANCE check, NOT a blind-holdout guarantee: dev and hidden are
    # different deterministic draws (different artifact hash and no shared concrete sha256
    # identifier), but they draw from the SAME scenario templates/markers. A true blind holdout
    # (disjoint templates) is documented as future work in the manifest (splits_are_blind_holdout).
    p = load_pilot(subtask_id)
    dev = p.build("dev", 1)  # type: ignore[arg-type]
    hidden = p.build("hidden", 1)  # type: ignore[arg-type]
    assert dev.artifact_sha256 != hidden.artifact_sha256, subtask_id
    import re

    def hashes(ep: object) -> set[str]:
        return set(re.findall(r"\b[0-9a-f]{64}\b", json.dumps(ep.public_inputs)))  # type: ignore[attr-defined]

    assert not (hashes(dev) & hashes(hidden)), subtask_id


@pytest.mark.parametrize("subtask_id", pilot_ids())
def test_provenance_and_adjudication_recorded(subtask_id: str) -> None:
    p = load_pilot(subtask_id)
    ep = p.build("dev", 1)  # type: ignore[arg-type]
    prov = ep.provenance
    assert prov.builder and prov.method and prov.independent_derivation
    assert "GOLD_PILOT_V1" in prov.labels
    assert ep.artifact_sha256 == ep.model_copy().artifact_sha256


def test_twelve_pilots_cover_all_services() -> None:
    from saber.catalog import load_catalog

    cat = load_catalog()
    services = {cat.subtask(sid).service for sid in pilot_ids()}
    assert services == {"MON", "CNT", "HUNT", "IR"}
    assert len(pilot_ids()) == 12
