"""Per-field synthetic generators + scorers keyed by parsed score-item kind.

Each generator returns a `FieldData` carrying: the agent-visible fragment (what the solver sees),
the sealed truth value (the gold answer for that field), and an `inferable` closure the rules
reference uses to recover the answer from the fragment (proving the label is not leaked verbatim
yet is derivable). A matching `score_field` applies the right tested primitive.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from saber.catalog.models import ParsedScoreItem, ScoreItemKind
from saber.grading.canonical import canonicalizer_for
from saber.grading.primitives import (
    score_enum,
    score_numeric,
    score_order,
    score_set,
    score_set_delta,
    verify_citations,
)
from saber.grading.results import GateOutcome, ItemScore
from saber.subtasks._hv.common import Rng

PyType = Any


@dataclass
class FieldData:
    name: str
    public: Any  # agent-visible fragment for this field
    truth: Any  # sealed gold value
    inferable: Any  # value the rules reference recovers from `public`
    py_type: str  # "str" | "list" | "dict" | "float"
    evidence_ids: list[str] = field(default_factory=list)


def clean_field(name: str) -> str:
    """Normalise a source field token like ``targeted[]`` or ``metrics{5}`` to an identifier."""
    base = re.sub(r"[\[\]{}]", "", name).strip()
    base = re.sub(r"\{.*\}", "", base)
    base = re.sub(r"[^0-9A-Za-z_]", "_", base).strip("_")
    return base or "answer"


def count_hint(name: str, default: int) -> int:
    m = re.search(r"\{(\d+)\}", name)
    return int(m.group(1)) if m else default


# --------------------------------------------------------------------------- enums

_ENUM_DOMAINS: dict[str, tuple[str, ...]] = {
    "TP/FP": ("TP", "FP"),
    "INCIDENT/SUSPICIOUS/NO_IMPACT": ("INCIDENT", "SUSPICIOUS", "NO_IMPACT"),
}
_GENERIC_ENUM = ("low", "medium", "high", "critical")
_SIGNAL_WORDS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel")


def _enum_domain(item: ParsedScoreItem) -> tuple[str, ...]:
    sub = (item.subtype or "").strip()
    if sub in _ENUM_DOMAINS:
        return _ENUM_DOMAINS[sub]
    if sub and "/" in sub:
        parts = tuple(p.strip() for p in sub.split("/") if p.strip())
        if len(parts) >= 2:
            return parts
    return _GENERIC_ENUM


def gen_enum(rng: Rng, item: ParsedScoreItem, name: str) -> FieldData:
    domain = _enum_domain(item)
    idx = rng.randint(0, len(domain) - 1)
    truth = domain[idx]
    # The label is inferable from a distinct signal token, never written as the label itself.
    signal = _SIGNAL_WORDS[idx % len(_SIGNAL_WORDS)]
    public = {
        "options": list(domain),
        "observed_signal": signal,
        "signal_map_hint": "each signal maps to one option by position",
    }
    return FieldData(name, public, truth, truth, "str")


def _enum_inferable(public: Any, item: ParsedScoreItem) -> str:
    domain = _enum_domain(item)
    signal = public.get("observed_signal") if isinstance(public, dict) else None
    if signal in _SIGNAL_WORDS:
        return domain[_SIGNAL_WORDS.index(signal) % len(domain)]
    return domain[0]


# A hard gate the agent must decide; non-ENUM gates use comply/violation. The correct value is
# derivable from a positional signal, never written verbatim, so the gate binds to a real decision.
GATE_DOMAIN = ("comply", "violation")


def _gate_domain(item: ParsedScoreItem) -> tuple[str, ...]:
    return _enum_domain(item) if item.kind is ScoreItemKind.ENUM else GATE_DOMAIN


def gen_gate(rng: Rng, item: ParsedScoreItem, name: str) -> FieldData:
    domain = _gate_domain(item)
    idx = rng.randint(0, len(domain) - 1)
    truth = domain[idx]
    signal = _SIGNAL_WORDS[idx % len(_SIGNAL_WORDS)]
    public = {
        "options": list(domain),
        "observed_signal": signal,
        "signal_map_hint": "each signal maps to one option by position; pick the option this signal selects",
    }
    return FieldData(name, public, truth, truth, "str")


def gate_inferable(public: Any, item: ParsedScoreItem) -> str:
    domain = _gate_domain(item)
    signal = public.get("observed_signal") if isinstance(public, dict) else None
    if signal in _SIGNAL_WORDS:
        return domain[_SIGNAL_WORDS.index(signal) % len(domain)]
    return domain[0]


# --------------------------------------------------------------------------- penalty items

# A penalty item (e.g. `level{} · enum · -0.5/phần tử sai`) classifies each of several elements;
# each element placed at the wrong level costs `penalty_per_item`. Modelled as a per-element dict.
_PENALTY_DOMAIN = ("tier1", "tier2", "tier3")


def gen_penalty(rng: Rng, item: ParsedScoreItem, name: str) -> FieldData:
    k = rng.randint(4, 8)
    elements = [f"elem-{i:02d}" for i in range(k)]
    truth: dict[str, str] = {}
    rows = []
    for e in elements:
        idx = rng.randint(0, len(_PENALTY_DOMAIN) - 1)
        truth[e] = _PENALTY_DOMAIN[idx]
        rows.append({"element": e, "observed_signal": _SIGNAL_WORDS[idx % len(_SIGNAL_WORDS)]})
    public = {
        "elements": rng.shuffle(rows),
        "levels": list(_PENALTY_DOMAIN),
        "note": "classify each element's level; each signal maps to one level by position",
    }
    return FieldData(name, public, truth, truth, "dict")


def penalty_inferable(public: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in public.get("elements", []):
        sig = row.get("observed_signal")
        if sig in _SIGNAL_WORDS:
            out[row["element"]] = _PENALTY_DOMAIN[_SIGNAL_WORDS.index(sig) % len(_PENALTY_DOMAIN)]
    return out


def penalty_mismatch_count(pred: Any, truth: Any) -> int:
    """Number of elements classified at the wrong level (missing counts as wrong)."""
    if not isinstance(truth, dict):
        return 0
    pred = pred if isinstance(pred, dict) else {}
    return sum(
        1 for k, v in truth.items() if str(pred.get(k, "")).strip().lower() != str(v).lower()
    )


# --------------------------------------------------------------------------- sets


def _elem(rng: Rng, subtype: str | None, i: int, malicious: bool) -> Any:
    st = (subtype or "").strip()
    tag = "bad" if malicious else "ok"
    if st in ("(ip,port)",):
        return {
            "ip": rng.external_ip() if malicious else rng.internal_ip(),
            "port": rng.randint(1, 65535),
        }
    if st in ("host",):
        return rng.hostname("bad" if malicious else "ws")
    if st in ("sha256", "hash"):
        return rng.sha256(f"{tag}{i}")
    if st in ("proc", "process"):
        return (
            f"evil{i}.exe" if malicious else rng.pick(("svchost.exe", "chrome.exe", "explorer.exe"))
        )
    if st in ("acct", "account"):
        return rng.username()
    if st in ("line",):
        return i
    return f"{tag}-{st or 'item'}-{i}"


_ANOMALY_THRESHOLD = 60


def gen_set(rng: Rng, item: ParsedScoreItem, name: str) -> FieldData:
    n = rng.randint(10, 20)
    m = rng.randint(2, max(2, n // 4))
    items: list[Any] = []
    truth: list[Any] = []
    for i in range(n - m):
        # Benign: low anomaly score. Membership is NOT marked; it must be derived from the score.
        items.append(
            {"value": _elem(rng, item.subtype, i, False), "anomaly_score": rng.randint(0, 45)}
        )
    for i in range(m):
        el = _elem(rng, item.subtype, 1000 + i, True)
        items.append({"value": el, "anomaly_score": rng.randint(70, 100)})
        truth.append(el)
    items = rng.shuffle(items)
    public = {
        "candidates": items,
        "anomaly_threshold": _ANOMALY_THRESHOLD,
        "note": f"an element is anomalous when anomaly_score >= {_ANOMALY_THRESHOLD}",
    }
    return FieldData(name, public, truth, truth, "list")


def _set_inferable(public: Any) -> list[Any]:
    thr = public.get("anomaly_threshold", _ANOMALY_THRESHOLD)
    return [c["value"] for c in public.get("candidates", []) if c.get("anomaly_score", 0) >= thr]


# --------------------------------------------------------------------------- order


def gen_order(rng: Rng, item: ParsedScoreItem, name: str) -> FieldData:
    k = rng.randint(6, 12)
    ids = [f"{clean_field(name)}-{i:02d}" for i in range(k)]
    # Distinct non-index sort values; the true order is recovered by sorting on occurred_at (the
    # ordering task itself), not by reading a key equal to the answer position.
    values = rng.sample(range(1000, 9999), k)
    truth_order = [e for _, e in sorted(zip(values, ids, strict=True))]
    events = rng.shuffle([{"id": e, "occurred_at": v} for e, v in zip(ids, values, strict=True)])
    public = {
        "events": events,
        "note": "order the events by their true time (occurred_at ascending)",
    }
    return FieldData(name, public, truth_order, truth_order, "list")


def _order_inferable(public: Any) -> list[str]:
    return [e["id"] for e in sorted(public.get("events", []), key=lambda e: e["occurred_at"])]


# --------------------------------------------------------------------------- numeric


def numeric_cells(item: ParsedScoreItem) -> int:
    """Number of metric cells from the RAW source field: {N} -> N, {} -> variable, else scalar."""
    m = re.search(r"\{(\d+)\}", item.field)
    if m:
        return int(m.group(1))
    if item.field.rstrip().endswith("{}"):
        return 4
    return 1


def is_dict_numeric(item: ParsedScoreItem) -> bool:
    return bool(re.search(r"\{\d*\}", item.field))


def is_interval_numeric(item: ParsedScoreItem) -> bool:
    return bool(item.tolerance and "iou" in item.tolerance.lower())


def gen_numeric(rng: Rng, item: ParsedScoreItem, name: str) -> FieldData:
    if is_interval_numeric(item):
        # Byte offsets, some of which "hit" a signature; the interval is derived as min..max hit,
        # not written verbatim.
        offsets = sorted(rng.sample(range(0, 800), rng.randint(8, 16)))
        hits = sorted(rng.sample(offsets, rng.randint(3, 6)))
        rows_iv = [{"offset": o, "signature_hit": o in hits} for o in offsets]
        interval: dict[str, int] = {"start": hits[0], "end": hits[-1]}
        ipub: dict[str, Any] = {
            "payload_bytes": rows_iv,
            "note": "report the byte interval (start=min, end=max) covering the signature_hit offsets",
        }
        return FieldData(name, ipub, interval, interval, "dict")
    if is_dict_numeric(item):
        cells = numeric_cells(item)
        rows: list[dict[str, int]] = [
            {"v": rng.randint(1, 100)} for _ in range(rng.randint(cells, cells + 5))
        ]
        truth_d: dict[str, float] = {
            f"m{j}": float(sum(r["v"] for r in rows) % (j + 7)) for j in range(cells)
        }
        dpub: dict[str, Any] = {
            "rows": rows,
            "compute": [f"m{j} = sum(v) mod {j + 7}" for j in range(cells)],
        }
        return FieldData(name, dpub, truth_d, truth_d, "dict")
    # Scalar: a real aggregate (count of rows over a threshold), not a copied value.
    rows_s = [{"v": rng.randint(1, 100)} for _ in range(rng.randint(8, 16))]
    truth_v = float(sum(1 for r in rows_s if r["v"] > 50))
    spub: dict[str, Any] = {"rows": rows_s, "compute": "value = count of rows with v > 50"}
    return FieldData(name, spub, truth_v, truth_v, "float")


def _numeric_inferable(public: Any, item: ParsedScoreItem) -> Any:
    if is_interval_numeric(item):
        hits = [r["offset"] for r in public.get("payload_bytes", []) if r.get("signature_hit")]
        return {"start": min(hits), "end": max(hits)} if hits else {"start": 0, "end": 0}
    rows = public.get("rows", [])
    if is_dict_numeric(item):
        cells = numeric_cells(item)
        return {f"m{j}": float(sum(r["v"] for r in rows) % (j + 7)) for j in range(cells)}
    return float(sum(1 for r in rows if r.get("v", 0) > 50))


# --------------------------------------------------------------------------- scoring


def score_field(
    item: ParsedScoreItem, name: str, pred: Any, truth: Any, *, weight: float | None
) -> ItemScore:
    kind = item.kind
    w = weight if weight is not None else item.weight
    if kind is ScoreItemKind.ENUM:
        s, d = score_enum(pred, truth, valid_labels=list(_enum_domain(item)))
        return ItemScore(field=name, score=s, weight=w, detail=d)
    if kind is ScoreItemKind.SET:
        canon = canonicalizer_for(item.subtype)
        res = score_set(pred, truth, canon=canon, beta=item.beta or 1.0)
        return ItemScore(field=name, score=res.score, weight=w, detail=res.detail())
    if kind is ScoreItemKind.ORDER:
        ores = score_order(
            pred, truth, canon=canonicalizer_for(item.subtype or "text"), mode="tau*recall"
        )
        return ItemScore(field=name, score=ores.score, weight=w, detail=ores.detail())
    if kind is ScoreItemKind.NUMERIC:
        if isinstance(truth, dict) and not is_interval_numeric(item):
            from saber.grading.primitives import fraction_correct

            flags = [
                score_numeric((pred or {}).get(k), v, item.tolerance)[0] == 1.0
                for k, v in truth.items()
            ]
            sc, d = fraction_correct(flags)
            return ItemScore(field=name, score=sc, weight=w, detail=d)
        s, d = score_numeric(pred, truth, item.tolerance)
        return ItemScore(field=name, score=s, weight=w, detail=d)
    # Fallback: treat as a set of strings.
    res = score_set(pred, truth, canon=canonicalizer_for(item.subtype))
    return ItemScore(field=name, score=res.score, weight=w, detail=res.detail())


def set_delta_field(item: ParsedScoreItem, name: str, pred: Any, truth: Any) -> ItemScore:
    res = score_set_delta(pred, truth, canon=canonicalizer_for(item.subtype))
    return ItemScore(field=name, score=res.score, weight=item.weight, detail=res.detail())


def cite_gate(citations: Any, valid_ids: set[str], *, name: str = "CITE") -> GateOutcome:
    res = verify_citations(citations, valid_ids)
    reason = "all citations resolve" if res.passed else f"unresolved={res.invalid[:3]}"
    return GateOutcome(name=name, passed=res.passed, mode="zero", reason=reason)


# Registry of (generator, inferable) by kind for the common families.
Generator = Callable[[Rng, ParsedScoreItem, str], FieldData]

GENERATORS: dict[ScoreItemKind, Generator] = {
    ScoreItemKind.ENUM: gen_enum,
    ScoreItemKind.SET: gen_set,
    ScoreItemKind.ORDER: gen_order,
    ScoreItemKind.NUMERIC: gen_numeric,
}


def infer_field(item: ParsedScoreItem, name: str, public: Any) -> Any:
    if item.kind is ScoreItemKind.ENUM:
        return _enum_inferable(public, item)
    if item.kind is ScoreItemKind.SET:
        return _set_inferable(public)
    if item.kind is ScoreItemKind.ORDER:
        return _order_inferable(public)
    if item.kind is ScoreItemKind.NUMERIC:
        return _numeric_inferable(public, item)
    return _set_inferable(public)
