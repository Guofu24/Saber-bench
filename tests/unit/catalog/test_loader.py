"""B001: frozen catalog loads, verifies hash, parses every score item and aggregate."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from saber.catalog import AggregateKind, ScoreItemKind, load_catalog
from saber.catalog.parsing import parse_aggregate, parse_score_item
from saber.domain.errors import ValidationError


def test_catalog_counts_and_hash(repo_root: Path) -> None:
    cat = load_catalog(repo_root)
    assert len(cat.subtasks) == 175
    assert len(cat.tasks) == 55
    assert len(cat.artifacts) == 40
    assert cat.source_verified is True
    assert Counter(s.environment for s in cat.subtasks) == {"file": 110, "soc": 47, "vm": 18}
    assert Counter(s.service for s in cat.subtasks) == {"MON": 58, "CNT": 15, "HUNT": 39, "IR": 63}
    assert len(cat.catalog_digest) == 64


def test_every_item_and_aggregate_parsed(repo_root: Path) -> None:
    cat = load_catalog(repo_root)
    for s in cat.subtasks:
        assert s.score_items, s.id
        assert s.aggregate is not None, s.id
        assert len(s.score_items) == len(s.score_items_source)
    kinds = Counter(s.aggregate.kind for s in cat.subtasks if s.aggregate)
    assert kinds[AggregateKind.CUSTOM] == 0, kinds
    assert kinds[AggregateKind.WEIGHTED_SUM] >= 54
    assert kinds[AggregateKind.SET_DELTA] == 15


def test_weighted_sum_weights_total_one(repo_root: Path) -> None:
    cat = load_catalog(repo_root)
    off = []
    for s in cat.subtasks:
        if s.aggregate and s.aggregate.kind is AggregateKind.WEIGHTED_SUM:
            total = sum(i.weight or 0.0 for i in s.score_items if i.weight is not None)
            if abs(total - 1.0) > 1e-6:
                off.append((s.id, round(total, 3)))
    assert off == [], off


def test_parse_item_variants() -> None:
    i = parse_score_item("`targeted[]` · setF2/host · 0.7")
    assert i.kind is ScoreItemKind.SET and i.beta == 2.0 and i.subtype == "host" and i.weight == 0.7
    g = parse_score_item("`explain` · cite · gate")
    assert g.is_gate and g.kind is ScoreItemKind.CITE and g.weight is None and g.gate_mode == "zero"
    f = parse_score_item("`matrix_cell` · rule/HV-39 · gate 0.5")
    assert f.is_gate and f.gate_mode == "factor" and f.gate_factor == 0.5
    c = parse_score_item("`sla_marks` · rule/SLA · cap 0.5")
    assert c.gate_mode == "cap" and c.gate_factor == 0.5
    n = parse_score_item("`t0` · num/±5′ · 0.25")
    assert n.kind is ScoreItemKind.NUMERIC and n.tolerance == "±5′"
    fr = parse_score_item("`6 trường báo cáo` · enum/set · 1/6 mỗi")
    assert fr.weight == pytest.approx(1 / 6)
    pen = parse_score_item("`tiers` · enum3 · −0.5/phần tử sai")
    assert pen.is_penalty and pen.penalty_per_item == 0.5
    e = parse_score_item("`classification` · enum (INCIDENT/SUSPICIOUS/NO_IMPACT) · 0.35")
    assert e.subtype == "INCIDENT/SUSPICIOUS/NO_IMPACT"
    pe = parse_score_item("`evidence[]` · cite · gate/phần tử")
    assert pe.gate_mode == "per_element"
    with pytest.raises(ValueError):
        parse_score_item("garbage")


def test_parse_aggregate_variants() -> None:
    a = parse_aggregate("Σ wᵢ·sᵢ ; cap 0.30 nếu classification sai")
    assert a.kind is AggregateKind.WEIGHTED_SUM and a.caps[0].cap == 0.3
    b = parse_aggregate("F1 × [channel] × [deadline] × [không báo nhầm khách khác]")
    assert b.kind is AggregateKind.FBETA and b.beta == 1.0 and len(b.gates) == 3
    c = parse_aggregate("max(0, M′/M − N′/(N′+M′))")
    assert c.kind is AggregateKind.SET_DELTA
    d = parse_aggregate("(Σ wᵢ·sᵢ) × CITE")
    assert d.kind is AggregateKind.WEIGHTED_SUM and d.gates == ["CITE"]
    e = parse_aggregate("Π[4 điều kiện]")
    assert e.kind is AggregateKind.PRODUCT_GATES
    f = parse_aggregate("F1 (sai tiến trình = 0.5 phần tử)")
    assert f.partial_credit == 0.5
    g = parse_aggregate("Σ wᵢ·sᵢ − 0.1 × (số mục đòi thừa)")
    assert g.penalties[0].per_item == 0.1
    h = parse_aggregate("[severity] × (1.0 nếu ô đúng, 0.5 nếu sai ô)")
    assert h.kind is AggregateKind.FIXED_ITEM and h.partial_credit == 0.5
    m = parse_aggregate("0.7·F2 + 0.3·max(0, ρ)")
    assert m.kind is AggregateKind.MIXTURE and [t.weight for t in m.mixture] == [0.7, 0.3]


def test_tampered_source_refused(repo_root: Path, tmp_path: Path) -> None:
    shutil.copytree(repo_root / "catalog", tmp_path / "catalog")
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "nice_coverage_4dichvu_SOC_subtask.html").write_text("tampered", encoding="utf8")
    with pytest.raises(ValidationError):
        load_catalog(tmp_path)


def test_tampered_metadata_refused(repo_root: Path, tmp_path: Path) -> None:
    shutil.copytree(repo_root / "catalog", tmp_path / "catalog")
    meta = json.loads((tmp_path / "catalog/metadata.json").read_text(encoding="utf8"))
    meta["source_sha256"] = "0" * 64
    (tmp_path / "catalog/metadata.json").write_text(json.dumps(meta), encoding="utf8")
    with pytest.raises(ValidationError):
        load_catalog(tmp_path)


def test_lookup_helpers(repo_root: Path) -> None:
    cat = load_catalog(repo_root)
    s = cat.subtask("T1112.001")
    assert s.environment == "file" and s.input_hv_ids == ["HV-01"]
    assert cat.task("T1112").service == "MON"
    assert cat.artifact("HV-01").scope == "case_or_episode"
    with pytest.raises(ValidationError):
        cat.subtask("T001")
