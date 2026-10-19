"""Scoring primitives. Pure functions; every result carries an auditable detail dict."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from saber.grading.canonical import Canonicalizer, canon_text, canonical_set
from saber.grading.results import GateOutcome, PenaltyApplied, Validity

# --------------------------------------------------------------------------- enum


def score_enum(
    pred: Any,
    truth: Any,
    *,
    aliases: Mapping[str, str] | None = None,
    valid_labels: Collection[str] | None = None,
    canon: Canonicalizer = canon_text,
) -> tuple[float, dict[str, Any]]:
    """Exact match after canonicalisation and alias folding. Abstain/invalid → 0."""
    alias_map = {canon(k): canon(v) for k, v in (aliases or {}).items()}
    t = alias_map.get(canon(truth), canon(truth))
    if pred is None or (isinstance(pred, str) and not pred.strip()):
        return 0.0, {"abstained": True, "truth": t}
    p = alias_map.get(canon(pred), canon(pred))
    detail: dict[str, Any] = {"pred": p, "truth": t}
    if valid_labels is not None:
        allowed = {alias_map.get(canon(v), canon(v)) for v in valid_labels}
        if p not in allowed:
            detail["invalid_label"] = True
            return 0.0, detail
    return (1.0 if p == t else 0.0), detail


# --------------------------------------------------------------------------- sets


@dataclass
class SetScore:
    tp: float
    fp: int
    fn: int
    precision: float
    recall: float
    score: float
    beta: float
    formula: str
    pred_size: int
    truth_size: int
    matched: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    abstained: bool = False

    def detail(self) -> dict[str, Any]:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "precision": round(self.precision, 6),
            "recall": round(self.recall, 6), "beta": self.beta, "formula": self.formula,
            "pred_size": self.pred_size, "truth_size": self.truth_size,
            "false_positives": sorted(self.false_positives)[:50], "missed": sorted(self.missed)[:50],
            "abstained": self.abstained,
        }  # fmt: skip


def _fbeta(precision: float, recall: float, beta: float) -> float:
    if precision == 0.0 and recall == 0.0:
        return 0.0
    if math.isinf(beta):
        return recall
    b2 = beta * beta
    return (1 + b2) * precision * recall / (b2 * precision + recall)


def _empty_policy(pred: set[str], truth: set[str]) -> float | None:
    """ADR 0001: both empty → 1.0; truth empty & pred non-empty → 0.0; else None (compute)."""
    if not truth:
        return 1.0 if not pred else 0.0
    if not pred:
        return 0.0
    return None


def score_set(pred: Any, truth: Any, *, canon: Canonicalizer, beta: float = 1.0) -> SetScore:
    p = canonical_set(pred, canon)
    t = canonical_set(truth, canon)
    tp_set = p & t
    fp_set = p - t
    fn_set = t - p
    precision = len(tp_set) / len(p) if p else 0.0
    recall = len(tp_set) / len(t) if t else 0.0
    fixed = _empty_policy(p, t)
    score = fixed if fixed is not None else _fbeta(precision, recall, beta)
    return SetScore(
        tp=float(len(tp_set)), fp=len(fp_set), fn=len(fn_set), precision=precision, recall=recall,
        score=score, beta=beta, formula=f"F{beta:g}" if not math.isinf(beta) else "recall",
        pred_size=len(p), truth_size=len(t), matched=sorted(tp_set), false_positives=sorted(fp_set),
        missed=sorted(fn_set), abstained=pred is None,
    )  # fmt: skip


def score_set_delta(pred: Any, truth: Any, *, canon: Canonicalizer) -> SetScore:
    """Source: max(0, M′/M − N′/(N′+M′)). M=|truth|, M′=|pred∩truth|, N′=|pred∖truth|."""
    p = canonical_set(pred, canon)
    t = canonical_set(truth, canon)
    m_hit = len(p & t)
    n_fp = len(p - t)
    fixed = _empty_policy(p, t)
    if fixed is not None:
        score = fixed
    else:
        second = n_fp / (n_fp + m_hit) if (n_fp + m_hit) else 0.0
        score = max(0.0, m_hit / len(t) - second)
    precision = m_hit / len(p) if p else 0.0
    recall = m_hit / len(t) if t else 0.0
    return SetScore(
        tp=float(m_hit), fp=n_fp, fn=len(t - p), precision=precision, recall=recall, score=score,
        beta=1.0, formula="max(0, M'/M - N'/(N'+M'))", pred_size=len(p), truth_size=len(t),
        matched=sorted(p & t), false_positives=sorted(p - t), missed=sorted(t - p), abstained=pred is None,
    )  # fmt: skip


def score_set_partial(
    pred: Iterable[Any] | None,
    truth: Iterable[Any],
    *,
    key_canon: Canonicalizer,
    attr_canon: Canonicalizer,
    partial: float = 0.5,
    beta: float = 1.0,
) -> SetScore:
    """Fβ where an element matched on key but wrong on attribute counts `partial` toward TP."""
    truth_map: dict[str, str] = {}
    for item in truth:
        truth_map[key_canon(item)] = attr_canon(item)
    pred_map: dict[str, str] = {}
    for item in pred or []:
        k = key_canon(item)
        if k:
            pred_map.setdefault(k, attr_canon(item))
    p_keys, t_keys = set(pred_map), set(truth_map)
    fixed = _empty_policy(p_keys, t_keys)
    tp_w = 0.0
    matched: list[str] = []
    for k in p_keys & t_keys:
        credit = 1.0 if pred_map[k] == truth_map[k] else partial
        tp_w += credit
        matched.append(f"{k}:{credit:g}")
    fp_set, fn_set = p_keys - t_keys, t_keys - p_keys
    precision = tp_w / len(p_keys) if p_keys else 0.0
    recall = tp_w / len(t_keys) if t_keys else 0.0
    score = fixed if fixed is not None else _fbeta(precision, recall, beta)
    return SetScore(
        tp=tp_w, fp=len(fp_set), fn=len(fn_set), precision=precision, recall=recall, score=score,
        beta=beta, formula=f"F{beta:g} partial={partial}", pred_size=len(p_keys), truth_size=len(t_keys),
        matched=sorted(matched), false_positives=sorted(fp_set), missed=sorted(fn_set), abstained=pred is None,
    )  # fmt: skip


# --------------------------------------------------------------------------- order


def kendall_tau_b(x: Sequence[float], y: Sequence[float]) -> float | None:
    n = len(x)
    if n != len(y) or n < 2:
        return None
    concordant = discordant = ties_x = ties_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = x[i] - x[j]
            dy = y[i] - y[j]
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif (dx > 0) == (dy > 0):
                concordant += 1
            else:
                discordant += 1
    denom = math.sqrt((concordant + discordant + ties_x) * (concordant + discordant + ties_y))
    if denom == 0:
        return None
    return (concordant - discordant) / denom


def spearman_rho(x: Sequence[float], y: Sequence[float]) -> float | None:
    n = len(x)
    if n != len(y) or n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    vx = math.sqrt(sum((a - mx) ** 2 for a in x))
    vy = math.sqrt(sum((b - my) ** 2 for b in y))
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


@dataclass
class OrderScore:
    tau: float | None
    rho: float | None
    recall: float
    common: int
    missing: list[str]
    extra: list[str]
    score: float
    formula: str

    def detail(self) -> dict[str, Any]:
        return {
            "tau": None if self.tau is None else round(self.tau, 6),
            "rho": None if self.rho is None else round(self.rho, 6),
            "recall": round(self.recall, 6), "common": self.common, "missing": self.missing[:50],
            "extra": self.extra[:50], "formula": self.formula,
        }  # fmt: skip


def score_order(
    pred: Sequence[Any] | None,
    truth: Sequence[Any],
    *,
    canon: Canonicalizer,
    mode: str = "tau",
    truth_ranks: Mapping[str, float] | None = None,
) -> OrderScore:
    """Kendall τ-b (or Spearman ρ) over common elements; score = max(0, stat).

    mode: "tau" → max(0,τ); "rho" → max(0,ρ); "tau+recall" → 0.5·max(0,τ) + 0.5·recall.
    `truth_ranks` lets the truth carry tied ranks (simultaneous events).
    """
    t_keys = [canon(v) for v in truth]
    t_index: dict[str, float] = {}
    for i, k in enumerate(t_keys):
        t_index.setdefault(
            k, float(truth_ranks[k]) if truth_ranks and k in truth_ranks else float(i)
        )
    p_keys: list[str] = []
    for v in pred or []:
        k = canon(v)
        if k and k not in p_keys:
            p_keys.append(k)
    common = [k for k in p_keys if k in t_index]
    missing = [k for k in t_index if k not in p_keys]
    extra = [k for k in p_keys if k not in t_index]
    recall = len(common) / len(t_index) if t_index else (1.0 if not p_keys else 0.0)
    x = [float(i) for i, _ in enumerate(common)]
    y = [t_index[k] for k in common]
    tau = kendall_tau_b(x, y)
    rho = spearman_rho(x, y)
    stat = rho if mode == "rho" else tau
    base = max(0.0, stat) if stat is not None else 0.0
    if len(common) == len(t_index) == 1 and not extra:
        base = 1.0  # single element in correct, complete order
    if mode == "tau+recall":
        score = 0.5 * base + 0.5 * recall
        formula = "0.5*max(0,tau) + 0.5*recall"
    else:
        score = base
        formula = f"max(0,{mode})"
    return OrderScore(
        tau=tau,
        rho=rho,
        recall=recall,
        common=len(common),
        missing=missing,
        extra=extra,
        score=score,
        formula=formula,
    )


# --------------------------------------------------------------------------- numeric

_TOL_RE = re.compile(r"^±\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>′|'|pp|%|m|min)?$")
_IOU_RE = re.compile(r"^IoU\s*[≥>=]+\s*(?P<num>0?\.\d+|1(?:\.0)?)$")


def _as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip().rstrip("%")
        try:
            return float(text)
        except ValueError:
            return None
    return None


def score_numeric(pred: Any, truth: Any, tolerance: str | None) -> tuple[float, dict[str, Any]]:
    """Tolerance tokens per ADR 0001: ±0, ±5′, ±0.5pp, ±20%, IoU≥0.8."""
    tol = (tolerance or "±0").strip()
    if pred is None:
        return 0.0, {"abstained": True}
    if m := _IOU_RE.match(tol):
        return _score_iou(pred, truth, float(m.group("num")))
    m = _TOL_RE.match(tol)
    if not m:
        return 0.0, {"error": f"unknown tolerance {tol!r}"}
    num = float(m.group("num"))
    unit = m.group("unit") or ""
    if unit in {"′", "'", "m", "min"}:
        p_dt, t_dt = _as_dt(pred), _as_dt(truth)
        if p_dt is None or t_dt is None:
            pf, tf = _as_float(pred), _as_float(truth)
            if pf is None or tf is None:
                return 0.0, {"type_error": True, "tolerance": tol}
            diff = abs(pf - tf)
        else:
            diff = abs((p_dt - t_dt).total_seconds()) / 60.0
        ok = diff <= num + 1e-9
        return (1.0 if ok else 0.0), {"diff_minutes": round(diff, 3), "tolerance": tol}
    pf, tf = _as_float(pred), _as_float(truth)
    if pf is None or tf is None:
        return 0.0, {"type_error": True, "tolerance": tol}
    # "%" is relative to truth; "" and "pp" are absolute differences
    allowed = abs(tf) * num / 100.0 if unit == "%" else num
    diff = abs(pf - tf)
    ok = diff <= allowed + 1e-9
    return (1.0 if ok else 0.0), {
        "diff": round(diff, 6),
        "allowed": round(allowed, 6),
        "tolerance": tol,
    }


def _score_iou(pred: Any, truth: Any, threshold: float) -> tuple[float, dict[str, Any]]:
    def interval(v: Any) -> tuple[float, float] | None:
        if isinstance(v, Mapping):
            a, b = v.get("start"), v.get("end")
        elif isinstance(v, Sequence) and not isinstance(v, str) and len(v) == 2:
            a, b = v[0], v[1]
        else:
            return None
        da, db = _as_dt(a), _as_dt(b)
        if da and db:
            return (da.timestamp(), db.timestamp())
        fa, fb = _as_float(a), _as_float(b)
        if fa is None or fb is None:
            return None
        return (fa, fb)

    p, t = interval(pred), interval(truth)
    if p is None or t is None:
        return 0.0, {"type_error": True, "tolerance": f"IoU>={threshold}"}
    inter = max(0.0, min(p[1], t[1]) - max(p[0], t[0]))
    union = max(p[1], t[1]) - min(p[0], t[0])
    iou = inter / union if union > 0 else (1.0 if p == t else 0.0)
    return (1.0 if iou >= threshold - 1e-9 else 0.0), {"iou": round(iou, 6), "threshold": threshold}


# --------------------------------------------------------------------------- citations


@dataclass
class CiteResult:
    valid: list[str]
    invalid: list[str]
    passed: bool

    def detail(self) -> dict[str, Any]:
        return {
            "valid": len(self.valid),
            "invalid": sorted(self.invalid)[:50],
            "passed": self.passed,
        }


def verify_citations(refs: Iterable[str] | None, valid_ids: Collection[str]) -> CiteResult:
    """CITE gate: ≥1 ref and zero unresolvable refs (hallucinated evidence fails the gate)."""
    valid_set = {str(v) for v in valid_ids}
    seen: list[str] = []
    for r in refs or []:
        key = str(r).strip()
        if key and key not in seen:
            seen.append(key)
    good = [r for r in seen if r in valid_set]
    bad = [r for r in seen if r not in valid_set]
    return CiteResult(valid=good, invalid=bad, passed=bool(good) and not bad)


def cite_filter_elements(
    elements: Iterable[Any],
    refs_of: Callable[[Any], Iterable[str] | None],
    valid_ids: Collection[str],
) -> tuple[list[Any], list[Any]]:
    """Per-element citation gate: returns (supported, unsupported) elements."""
    valid_set = {str(v) for v in valid_ids}
    supported: list[Any] = []
    unsupported: list[Any] = []
    for el in elements:
        refs = [str(r) for r in (refs_of(el) or [])]
        if refs and all(r in valid_set for r in refs):
            supported.append(el)
        else:
            unsupported.append(el)
    return supported, unsupported


# --------------------------------------------------------------------------- composition


def weighted_sum(parts: Iterable[tuple[float, float]]) -> float:
    total = 0.0
    for weight, score in parts:
        total += weight * score
    return min(1.0, max(0.0, total))


def apply_gates(
    score: float, gates: Iterable[GateOutcome]
) -> tuple[float, Validity, str | None, list[str]]:
    """Apply gate outcomes in order; returns (score, validity, invalid_reason, trace)."""
    trace: list[str] = []
    validity = Validity.VALID
    reason: str | None = None
    for g in gates:
        if g.passed:
            trace.append(f"gate {g.name}: passed")
            continue
        if g.mode == "zero":
            score = 0.0
            trace.append(f"gate {g.name}: FAILED → score 0 ({g.reason})")
        elif g.mode == "factor":
            factor = g.factor if g.factor is not None else 0.0
            score *= factor
            trace.append(f"gate {g.name}: FAILED → score × {factor} ({g.reason})")
        elif g.mode == "cap":
            cap = g.factor if g.factor is not None else 0.0
            score = min(score, cap)
            trace.append(f"gate {g.name}: FAILED → cap {cap} ({g.reason})")
        elif g.mode == "invalid":
            validity = Validity.INVALID
            reason = reason or f"{g.name}: {g.reason}"
            trace.append(f"gate {g.name}: FAILED → episode INVALID ({g.reason})")
        else:  # per_element handled upstream; record only
            trace.append(f"gate {g.name}: FAILED (per-element, applied upstream)")
    return min(1.0, max(0.0, score)), validity, reason, trace


def apply_penalty(
    score: float, name: str, count: int, per_item: float
) -> tuple[float, PenaltyApplied]:
    deducted = min(score, count * per_item)
    return max(0.0, score - count * per_item), PenaltyApplied(
        name=name, count=count, per_item=per_item, deducted=deducted
    )


def accuracy(
    pairs: Iterable[tuple[Any, Any]], *, canon: Canonicalizer = canon_text
) -> tuple[float, dict[str, Any]]:
    items = list(pairs)
    if not items:
        return 0.0, {"n": 0, "empty": True}
    correct = sum(1 for p, t in items if p is not None and canon(p) == canon(t))
    return correct / len(items), {"n": len(items), "correct": correct}


def macro_average(group_scores: Mapping[str, float | None]) -> tuple[float, dict[str, Any]]:
    present = {k: v for k, v in group_scores.items() if v is not None}
    if not present:
        return 0.0, {"groups": 0, "empty": True}
    return sum(present.values()) / len(present), {
        "groups": len(present),
        "per_group": {k: round(v, 6) for k, v in present.items()},
    }


def fraction_correct(flags: Iterable[bool]) -> tuple[float, dict[str, Any]]:
    items = list(flags)
    if not items:
        return 0.0, {"n": 0, "empty": True}
    return sum(1 for f in items if f) / len(items), {
        "n": len(items),
        "correct": sum(1 for f in items if f),
    }


def tpr_minus_fpr(tp: int, fn: int, fp: int, tn: int) -> tuple[float, dict[str, Any]]:
    tpr = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return max(0.0, tpr - fpr), {
        "tpr": round(tpr, 6),
        "fpr": round(fpr, 6),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
    }


def delta_fp_tp(
    fp_before: int, fp_after: int, tp_before: int, tp_after: int
) -> tuple[float, dict[str, Any]]:
    """Source: max(0, ΔFP% − ΔTP_lost%). 80% FP cut with 10% TP lost → 0.70."""
    d_fp = (fp_before - fp_after) / fp_before if fp_before else 0.0
    d_tp_lost = (tp_before - tp_after) / tp_before if tp_before else 0.0
    d_fp = max(0.0, min(1.0, d_fp))
    d_tp_lost = max(0.0, min(1.0, d_tp_lost))
    return max(0.0, d_fp - d_tp_lost), {
        "delta_fp_pct": round(d_fp, 6),
        "delta_tp_lost_pct": round(d_tp_lost, 6),
    }


def technique_tactic_score(
    pred: Any, truth: Any, tactic_of: Mapping[str, str]
) -> tuple[float, dict[str, Any]]:
    """1.0 exact technique (sub-technique aware), 0.5 same tactic, else 0."""
    from saber.grading.canonical import canon_technique

    if pred is None:
        return 0.0, {"abstained": True}
    p, t = canon_technique(pred), canon_technique(truth)
    if p == t or (p.split(".")[0] == t and "." not in t) or (t.split(".")[0] == p and "." not in p):
        return 1.0, {"pred": p, "truth": t, "level": "technique"}
    tp_ = tactic_of.get(p) or tactic_of.get(p.split(".")[0])
    tt_ = tactic_of.get(t) or tactic_of.get(t.split(".")[0])
    if tp_ and tt_ and tp_ == tt_:
        return 0.5, {"pred": p, "truth": t, "level": "tactic", "tactic": tt_}
    return 0.0, {"pred": p, "truth": t, "level": "none"}
