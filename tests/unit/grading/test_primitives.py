"""B003 golden tests for scoring primitives (hand-computed expectations, ADR 0001)."""

from __future__ import annotations

import pytest

from saber.grading.canonical import (
    canon_account,
    canon_host,
    canon_ioc,
    canon_proc,
    canon_technique,
    canonicalizer_for,
)
from saber.grading.primitives import (
    accuracy,
    apply_gates,
    apply_penalty,
    cite_filter_elements,
    delta_fp_tp,
    fraction_correct,
    kendall_tau_b,
    macro_average,
    score_enum,
    score_numeric,
    score_order,
    score_set,
    score_set_delta,
    score_set_partial,
    technique_tactic_score,
    tpr_minus_fpr,
    verify_citations,
    weighted_sum,
)
from saber.grading.results import GateOutcome, Validity


def test_canonicalizers() -> None:
    assert canon_host("WS01.corp.local.") == "ws01"
    assert canon_host("10.0.0.5") == "10.0.0.5"
    assert canon_proc(r"C:\Windows\System32\svchost.exe") == "svchost.exe"
    assert canon_account(r"CORP\Alice") == "alice" and canon_account("bob@corp.local") == "bob"
    assert canon_technique("t1059.001") == "T1059.001"
    assert canon_ioc("hxxp://evil[.]com/") == "http://evil.com"
    ipport = canonicalizer_for("(ip,port)")
    assert (
        ipport({"ip": "10.0.0.1", "port": "443"})
        == ipport("10.0.0.1:443")
        == ipport(["10.0.0.1", 443])
    )


def test_enum() -> None:
    assert score_enum("tp", "TP")[0] == 1.0
    assert score_enum("FP", "TP")[0] == 0.0
    s, d = score_enum(None, "TP")
    assert s == 0.0 and d["abstained"]
    s, d = score_enum("maybe", "TP", valid_labels=["TP", "FP"])
    assert s == 0.0 and d["invalid_label"]
    assert score_enum("Winnti", "APT41", aliases={"Winnti": "APT41", "Barium": "APT41"})[0] == 1.0


def test_set_fbeta_and_empty_policy() -> None:
    canon = canonicalizer_for("host")
    perfect = score_set(["a", "b"], ["A", "b.corp"], canon=canon)
    assert perfect.score == 1.0 and perfect.fp == 0
    half = score_set(["a", "x"], ["a", "b"], canon=canon)
    assert half.precision == 0.5 and half.recall == 0.5 and half.score == 0.5
    assert score_set([], [], canon=canon).score == 1.0
    assert score_set(["a"], [], canon=canon).score == 0.0
    assert score_set([], ["a"], canon=canon).score == 0.0
    assert score_set(None, ["a"], canon=canon).abstained
    # duplicates collapse
    assert score_set(["a", "a", "a"], ["a", "b"], canon=canon).precision == 1.0
    f2 = score_set(["a", "b", "x", "y"], ["a", "b", "c"], canon=canon, beta=2.0)
    p, r = 0.5, 2 / 3
    assert f2.score == pytest.approx(5 * p * r / (4 * p + r))


def test_set_delta_formula() -> None:
    canon = canonicalizer_for("host")
    # M=4, M'=3, N'=1 → 3/4 − 1/4 = 0.5
    s = score_set_delta(["h1", "h2", "h3", "zz"], ["h1", "h2", "h3", "h4"], canon=canon)
    assert s.score == pytest.approx(0.5)
    # M=2, M'=1, N'=3 → 0.5 − 0.75 → max(0, ·) = 0
    assert score_set_delta(["h1", "x", "y", "z"], ["h1", "h2"], canon=canon).score == 0.0
    assert score_set_delta(["h1", "h2"], ["h1", "h2"], canon=canon).score == 1.0
    assert score_set_delta([], ["h1"], canon=canon).score == 0.0
    assert score_set_delta([], [], canon=canon).score == 1.0
    assert score_set_delta(["h9"], [], canon=canon).score == 0.0


def test_set_partial_credit() -> None:
    key = canonicalizer_for("(ip,port)")
    attr = canonicalizer_for("proc")
    truth = [
        {"ip": "1.1.1.1", "port": 443, "process": "evil.exe"},
        {"ip": "2.2.2.2", "port": 80, "process": "x.exe"},
    ]
    pred = [
        {"ip": "1.1.1.1", "port": 443, "process": "chrome.exe"},
        {"ip": "2.2.2.2", "port": 80, "process": "x.exe"},
    ]
    s = score_set_partial(
        pred,
        truth,
        key_canon=lambda e: key(e),
        attr_canon=lambda e: attr(e["process"]),
        partial=0.5,
    )
    assert (
        s.tp == 1.5 and s.precision == 0.75 and s.recall == 0.75 and s.score == pytest.approx(0.75)
    )


def test_order_kendall_and_variants() -> None:
    canon = canonicalizer_for("text")
    truth = ["e1", "e2", "e3", "e4"]
    assert score_order(["e1", "e2", "e3", "e4"], truth, canon=canon).score == 1.0
    rev = score_order(["e4", "e3", "e2", "e1"], truth, canon=canon)
    assert rev.tau == pytest.approx(-1.0) and rev.score == 0.0
    part = score_order(["e1", "e3", "e2", "e4"], truth, canon=canon)
    assert part.tau == pytest.approx(4 / 6) and part.score == pytest.approx(4 / 6)
    miss = score_order(["e1", "e2"], truth, canon=canon)
    assert miss.recall == 0.5 and miss.missing == ["e3", "e4"] and miss.score == 1.0
    combo = score_order(["e1", "e2"], truth, canon=canon, mode="tau+recall")
    assert combo.score == pytest.approx(0.75)
    assert score_order([], truth, canon=canon).score == 0.0
    assert score_order(["e1"], truth, canon=canon).tau is None
    assert kendall_tau_b([1, 2, 3], [1, 2, 3]) == 1.0
    assert kendall_tau_b([1], [1]) is None
    rho = score_order(["e1", "e2", "e3", "e4"], truth, canon=canon, mode="rho")
    assert rho.rho == pytest.approx(1.0)


def test_numeric_tolerances() -> None:
    assert score_numeric(5, 5, "±0")[0] == 1.0 and score_numeric(5, 6, "±0")[0] == 0.0
    assert score_numeric("2026-10-17T09:04:00Z", "2026-10-17T09:00:00Z", "±5′")[0] == 1.0
    assert score_numeric("2026-10-17T09:06:00Z", "2026-10-17T09:00:00Z", "±5′")[0] == 0.0
    assert score_numeric("2026-10-17T16:00:00+07:00", "2026-10-17T09:00:00Z", "±0′")[0] == 1.0
    assert (
        score_numeric(90.4, 90.0, "±0.5pp")[0] == 1.0
        and score_numeric(91.0, 90.0, "±0.5pp")[0] == 0.0
    )
    assert score_numeric(118, 100, "±20%")[0] == 1.0 and score_numeric(121, 100, "±20%")[0] == 0.0
    assert score_numeric({"start": 0, "end": 10}, {"start": 1, "end": 10}, "IoU≥0.8")[0] == 1.0
    assert score_numeric({"start": 0, "end": 10}, {"start": 5, "end": 10}, "IoU≥0.8")[0] == 0.0
    s, d = score_numeric("abc", 1, "±0")
    assert s == 0.0 and d["type_error"]
    assert score_numeric(None, 1, "±0")[1]["abstained"]


def test_citations() -> None:
    valid = {"ev-1", "ev-2"}
    assert verify_citations(["ev-1"], valid).passed
    assert not verify_citations([], valid).passed
    bad = verify_citations(["ev-1", "ev-999"], valid)
    assert not bad.passed and bad.invalid == ["ev-999"]
    sup, unsup = cite_filter_elements(
        [{"t": "T1", "refs": ["ev-1"]}, {"t": "T2", "refs": []}, {"t": "T3", "refs": ["nope"]}],
        lambda e: e["refs"],
        valid,
    )
    assert [e["t"] for e in sup] == ["T1"] and [e["t"] for e in unsup] == ["T2", "T3"]


def test_gates_caps_penalties() -> None:
    score, validity, reason, trace = apply_gates(0.8, [GateOutcome(name="vip", passed=True)])
    assert score == 0.8 and validity is Validity.VALID
    score, *_ = apply_gates(0.8, [GateOutcome(name="vip", passed=False, reason="isolated VIP")])
    assert score == 0.0
    score, *_ = apply_gates(
        0.8, [GateOutcome(name="cell", passed=False, mode="factor", factor=0.5)]
    )
    assert score == pytest.approx(0.4)
    score, *_ = apply_gates(0.8, [GateOutcome(name="cls", passed=False, mode="cap", factor=0.3)])
    assert score == pytest.approx(0.3)
    score, validity, reason, _ = apply_gates(
        0.8, [GateOutcome(name="snap", passed=False, mode="invalid", reason="contaminated")]
    )
    assert validity is Validity.INVALID and reason and "contaminated" in reason
    s, pen = apply_penalty(0.9, "extra", 3, 0.1)
    assert s == pytest.approx(0.6) and pen.deducted == pytest.approx(0.3)
    assert apply_penalty(0.2, "extra", 5, 0.1)[0] == 0.0
    assert weighted_sum([(0.5, 1.0), (0.25, 0.0), (0.25, 1.0)]) == 0.75


def test_aggregates() -> None:
    assert accuracy([("a", "A"), ("b", "c")])[0] == 0.5
    assert accuracy([])[0] == 0.0
    assert macro_average({"g1": 1.0, "g2": 0.0, "g3": None})[0] == 0.5
    assert fraction_correct([True, False, True, True, False])[0] == pytest.approx(0.6)
    assert tpr_minus_fpr(tp=45, fn=5, fp=1000, tn=199_000)[0] == pytest.approx(0.9 - 1000 / 200_000)
    assert tpr_minus_fpr(0, 0, 5, 5)[0] == 0.0
    # Source T1111.003: cut FP by 80% while losing 10% TP → 0.70
    assert delta_fp_tp(fp_before=100, fp_after=20, tp_before=50, tp_after=45)[0] == pytest.approx(
        0.70
    )
    assert delta_fp_tp(100, 100, 50, 50)[0] == 0.0
    assert delta_fp_tp(100, 0, 50, 0)[0] == 0.0


def test_technique_tactic() -> None:
    tactic_of = {
        "T1059": "execution",
        "T1059.001": "execution",
        "T1047": "execution",
        "T1003": "credential-access",
    }
    assert technique_tactic_score("T1059.001", "T1059.001", tactic_of)[0] == 1.0
    assert technique_tactic_score("T1059", "T1059.001", tactic_of)[0] == 1.0
    assert technique_tactic_score("T1047", "T1059.001", tactic_of)[0] == 0.5
    assert technique_tactic_score("T1003", "T1059.001", tactic_of)[0] == 0.0
    assert technique_tactic_score(None, "T1059.001", tactic_of)[0] == 0.0
