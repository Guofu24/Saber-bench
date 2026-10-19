"""Hand-written readers for source score items and aggregate formulas.

These never evaluate source text. They classify it into structured metadata so that
per-subtask scorers can be checked against the source contract.
"""

from __future__ import annotations

import re

from saber.catalog.models import (
    AggregateKind,
    CapRule,
    MixtureTerm,
    ParsedAggregate,
    ParsedScoreItem,
    PenaltyRule,
    ScoreItemKind,
)

_ITEM_RE = re.compile(r"^`?(?P<field>[^`·]+?)`?\s*·\s*(?P<kind>[^·]+?)\s*·\s*(?P<weight>.+?)\s*$")
_NUM_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)?)(?:/(?P<den>\d+))?(?:\s+(?P<note>.+))?$")
_GATE_FACTOR_RE = re.compile(r"^gate\s+(?P<num>0?\.\d+|1(?:\.0)?)$")
_CAP_ITEM_RE = re.compile(r"^cap\s+(?P<num>0?\.\d+|1(?:\.0)?)$")
_PENALTY_ITEM_RE = re.compile(r"^[−-](?P<num>0?\.\d+|1(?:\.0)?)/phần tử(?:\s+\S+)?$")


def _parse_weight(weight_raw: str, raw: str) -> dict[str, object]:
    """Return the weight-related fields for one score item token."""
    if weight_raw == "gate":
        return {"is_gate": True, "gate_mode": "zero"}
    if weight_raw == "gate/phần tử":
        return {"is_gate": True, "gate_mode": "per_element"}
    if m := _GATE_FACTOR_RE.match(weight_raw):
        return {"is_gate": True, "gate_mode": "factor", "gate_factor": float(m.group("num"))}
    if m := _CAP_ITEM_RE.match(weight_raw):
        return {"is_gate": True, "gate_mode": "cap", "gate_factor": float(m.group("num"))}
    if m := _PENALTY_ITEM_RE.match(weight_raw):
        return {"is_penalty": True, "penalty_per_item": float(m.group("num"))}
    if m := _NUM_RE.match(weight_raw):
        weight = float(m.group("num"))
        if m.group("den"):
            weight /= float(m.group("den"))
        return {"weight": weight, "weight_note": m.group("note")}
    raise ValueError(f"unparseable weight {weight_raw!r} in {raw!r}")


def parse_score_item(raw: str) -> ParsedScoreItem:
    match = _ITEM_RE.match(raw.strip())
    if not match:
        raise ValueError(f"unparseable score item: {raw!r}")
    field = match.group("field").strip()
    kind_raw = match.group("kind").strip()
    weight_fields = _parse_weight(match.group("weight").strip(), raw)

    beta: float | None = None
    tolerance: str | None = None
    subtype: str | None = None
    head, _, tail = kind_raw.partition("/")
    head = head.strip()
    tail = tail.strip() or None
    if head.startswith("enum"):
        kind = ScoreItemKind.ENUM
        paren = re.search(r"\((.*)\)", kind_raw)
        if paren:
            subtype = paren.group(1).strip()
        elif head == "enum3":
            subtype = "3-way"
        elif tail:
            subtype = tail
    elif head.startswith("setF2"):
        kind, beta, subtype = ScoreItemKind.SET, 2.0, tail
    elif head.startswith("set"):
        kind, beta, subtype = ScoreItemKind.SET, 1.0, tail
    elif head.startswith("order"):
        kind = ScoreItemKind.ORDER
        subtype = "recall" if "+recall" in head else tail
    elif head.startswith("num"):
        kind, tolerance = ScoreItemKind.NUMERIC, tail
    elif head == "cite":
        kind = ScoreItemKind.CITE
    elif head == "gate":
        kind = ScoreItemKind.GATE
    elif head.startswith("state"):
        kind, subtype = ScoreItemKind.STATE, tail
    elif head.startswith("exec"):
        kind, subtype = ScoreItemKind.EXEC, tail
    elif head.startswith("rule"):
        kind, subtype = ScoreItemKind.RULE, tail
    else:
        raise ValueError(f"unknown score item kind {kind_raw!r} in {raw!r}")
    return ParsedScoreItem.model_validate(
        {"field": field, "kind": kind, "subtype": subtype, "beta": beta, "tolerance": tolerance,
         "raw": raw, **weight_fields}
    )


_CAP_RE = re.compile(r"cap\s+(?P<cap>0?\.\d+|1(?:\.0)?)\s+nếu\s+(?P<cond>.+?)(?:;|$)")
_PENALTY_RE = re.compile(r"−\s*(?P<per>0?\.\d+)\s*×\s*\((?P<count>[^)]+)\)")
_GATE_RE = re.compile(r"×\s*(?:\[(?P<name>[^\]]+)\]|(?P<cite>CITE)|Π\[(?P<prod>[^\]]+)\])")
_MIX_RE = re.compile(r"(?P<w>0?\.\d+)\s*·\s*(?P<term>F2|F1|ρ|e|τ|max\(0, ρ\)|\[[^\]]+\])")


def parse_aggregate(formula: str) -> ParsedAggregate:
    f = formula.strip()
    notes: list[str] = []
    gates = [m.group("name") or m.group("cite") or f"Π[{m.group('prod')}]" for m in _GATE_RE.finditer(f)]
    caps = [CapRule(condition=m.group("cond").strip(), cap=float(m.group("cap"))) for m in _CAP_RE.finditer(f)]
    penalties = [PenaltyRule(count_of=m.group("count").strip(), per_item=float(m.group("per"))) for m in _PENALTY_RE.finditer(f)]
    beta: float | None = None
    partial: float | None = None
    mixture: list[MixtureTerm] = []

    core = f.split(";")[0].strip()
    core_wo_gates = _GATE_RE.sub("", core).strip()
    core_wo_gates = re.sub(r"\s*×\s*$", "", core_wo_gates).strip()
    # strip trailing penalty text for classification
    core_wo_gates = _PENALTY_RE.sub("", core_wo_gates).strip()

    if re.search(r"M′/M\s*−\s*N′/\(N′\+M′\)", core_wo_gates) and "Σ" not in core_wo_gates:
        kind = AggregateKind.SET_DELTA
    elif core_wo_gates.startswith("Σ wᵢ·sᵢ") or core_wo_gates.startswith("(Σ wᵢ·sᵢ)"):
        kind = AggregateKind.WEIGHTED_SUM
        if "mỗi mục theo max(0, M′/M" in f:
            notes.append("each component uses set_delta")
        if "exploited nhân CITE" in f:
            gates.append("CITE:exploited")
    elif core_wo_gates.startswith("(0.35·s₁"):
        kind = AggregateKind.WEIGHTED_SUM
        notes.append("fixed 0.35/0.25 + group-specific items")
    elif re.match(r"^F[12]\b", core_wo_gates):
        kind = AggregateKind.FBETA
        beta = 2.0 if core_wo_gates.startswith("F2") else 1.0
        pm = re.search(r"=\s*(0?\.\d+)\s*phần tử", f)
        if pm:
            partial = float(pm.group(1))
    elif core_wo_gates.startswith("Kendall"):
        kind = AggregateKind.KENDALL_TAU
    elif core_wo_gates.startswith("accuracy"):
        kind = AggregateKind.ACCURACY
    elif core_wo_gates.startswith("macro-average"):
        kind = AggregateKind.MACRO_AVERAGE
        if "technique" in f:
            notes.append("technique 1.0 / tactic 0.5")
    elif core_wo_gates.startswith("Π["):
        kind = AggregateKind.PRODUCT_GATES
        gates.append(core_wo_gates)
    elif re.match(r"^\(số (ô|trường) đúng\)/\d+$", core_wo_gates) or core_wo_gates.startswith("tỉ lệ con số"):
        kind = AggregateKind.FRACTION_CORRECT
    elif core_wo_gates.startswith("max(0, TPR"):
        kind = AggregateKind.TPR_MINUS_FPR
    elif core_wo_gates.startswith("max(0, ΔFP%"):
        kind = AggregateKind.DELTA_FP_TP
    elif core_wo_gates.startswith("1.0 đúng technique"):
        kind = AggregateKind.TECHNIQUE_TACTIC
    elif core_wo_gates.startswith("recall"):
        kind = AggregateKind.FBETA
        beta = float("inf")
        notes.append("recall only")
    elif re.fullmatch(r"\[[^\]]+\](\s*×\s*\([^)]*\))?", core_wo_gates):
        kind = AggregateKind.FIXED_ITEM
        if "0.5 nếu sai ô" in f:
            partial = 0.5
    elif re.fullmatch(r"\[[^\]]+\]\s*×\s*\[[^\]]+\]", core):
        kind = AggregateKind.FIXED_ITEM
    elif _MIX_RE.search(core_wo_gates) and ("+" in core_wo_gates):
        kind = AggregateKind.MIXTURE
        for m in _MIX_RE.finditer(core_wo_gates):
            term = m.group("term")
            tk = {
                "F2": AggregateKind.FBETA, "F1": AggregateKind.FBETA, "ρ": AggregateKind.KENDALL_TAU,
                "max(0, ρ)": AggregateKind.KENDALL_TAU, "τ": AggregateKind.KENDALL_TAU,
                "e": AggregateKind.FIXED_ITEM,
            }.get(term, AggregateKind.FIXED_ITEM)  # fmt: skip
            mixture.append(MixtureTerm(weight=float(m.group("w")), kind=tk, note=term))
    else:
        kind = AggregateKind.CUSTOM
        notes.append("needs explicit scorer composition")
    return ParsedAggregate(
        kind=kind, source_formula=formula, gates=gates, caps=caps, penalties=penalties,
        mixture=mixture, partial_credit=partial, beta=beta, notes=notes,
    )  # fmt: skip
