"""AutoSubtask: compose a real scorer + synthetic fixture for any catalog subtask."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model

from saber.catalog.loader import default_catalog
from saber.catalog.models import (
    AggregateKind,
    CatalogSubtask,
    ParsedAggregate,
    ParsedScoreItem,
    ScoreItemKind,
)
from saber.domain.subtask import SubtaskSpecV1, ToolPolicy
from saber.grading.primitives import (
    macro_average,
    technique_tactic_score,
)
from saber.grading.results import GateOutcome, ItemScore
from saber.subtasks._auto import exec_state as es
from saber.subtasks._auto import fields as F
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng

_ATT_CK = {
    "T1059": "execution",
    "T1059.001": "execution",
    "T1047": "execution",
    "T1003": "credential-access",
    "T1053": "persistence",
    "T1105": "command-and-control",
}

# Aggregates whose fixture/scoring need a sandboxed corpus or a VM snapshot, not plain fields.
_EXEC_AGGS = {AggregateKind.TPR_MINUS_FPR, AggregateKind.DELTA_FP_TP}


class AutoSubtask(SubtaskBase):
    """Generic subtask driven by the frozen catalog record's parsed score contract.

    Subclasses set SUBTASK_ID; `auto_subtask_for(id)` builds one dynamically. The scorer composes
    the tested primitives per the parsed aggregate; fixtures are STRUCTURAL synthetic DEV data.
    """

    IS_AUTO = True

    def __init__(self) -> None:
        self._rec = default_catalog().subtask(self.SUBTASK_ID)
        self._items = list(self._rec.score_items)
        agg = self._rec.aggregate
        assert agg is not None
        self._agg: ParsedAggregate = agg
        self._field_names = [F.clean_field(i.field) for i in self._items]
        self._exec_mode = self._agg.kind in _EXEC_AGGS or any(
            i.kind is ScoreItemKind.EXEC for i in self._items
        )
        self._state_mode = any(i.kind is ScoreItemKind.STATE for i in self._items)
        # Each AutoSubtask is its own dynamically-created class (auto_subtask_for), so setting these
        # on the class is per-subtask, not shared global state.
        cls = type(self)
        if self._rec.environment == "vm":
            cls.TOOL_POLICY = ToolPolicy(
                allow=["read_fixture", "approved_lab_action"], state_mutation=self._state_mode
            )
        cls.OutputModel = _build_output_model(
            self.SUBTASK_ID,
            self._items,
            self._field_names,
            self._agg,
            self._exec_mode,
            self._state_mode,
        )

    # catalog binding (instance, since each AutoSubtask instance is a distinct subtask) ----------
    def record(self) -> CatalogSubtask:  # type: ignore[override]
        return self._rec

    def spec(self) -> SubtaskSpecV1:  # type: ignore[override]
        from saber.domain.subtask import spec_from_catalog
        from saber.grading import SCORER_VERSION

        return spec_from_catalog(
            self._rec,
            output_schema_ref=f"saber.subtasks._auto:{self.OutputModel.__name__}",
            scorer_ref=f"grader:{self.SUBTASK_ID}@{SCORER_VERSION}",
            tool_policy=self.TOOL_POLICY,
            timeouts=self.TIMEOUTS,
            adjudication_notes=[
                "auto-generated structural fixture; scorer bound to parsed source formula"
            ],
        )

    def output_schema(self) -> dict[str, Any]:  # type: ignore[override]
        return self.OutputModel.model_json_schema()

    # ---- fixture ------------------------------------------------------------------
    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        if self._exec_mode:
            return es.build_exec_fixture(self, rng, seed, variant)
        if self._state_mode:
            return es.build_state_fixture(self, rng, seed, variant)
        data: dict[str, Any] = {}
        truth: dict[str, Any] = {}
        evidence: list[str] = [rng.hexid("ev") for _ in range(4)]
        scored_names: list[str] = []
        for item, name in zip(self._items, self._field_names, strict=True):
            if _is_cite(item):
                continue
            if _is_gate(item):
                # A hard gate the agent must get right (comply vs violation, or the correct enum);
                # the correct value is derivable from a signal, never the literal answer.
                gfd = F.gen_gate(rng, item, name)
                truth[name] = gfd.truth
                data[_dk(name) + "_context"] = gfd.public
                continue
            gen = F.GENERATORS.get(item.kind, F.gen_set)
            fd = gen(rng, item, name)
            data[_dk(name)] = fd.public
            truth[name] = fd.truth
            scored_names.append(name)
        if any(_is_cite(i) for i in self._items):
            truth["_cite_refs"] = evidence[:2]
        # Field fragments live under "data" so a field named like a forbidden key (e.g. "labels")
        # never collides with the truth-key leak guard at the top level.
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={
                "scored_fields": scored_names or self._field_names,
                "data": data,
                "objective": self._rec.scenario_source,
            },
            sealed_truth=truth,
            evidence_ids=evidence,
            notes="STRUCTURAL synthetic DEV fixture (auto-generated); scorer bound to source formula.",
        )

    # ---- oracle / reference -------------------------------------------------------
    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        if self._exec_mode:
            return es.exec_answer_from_truth(self, truth)
        if self._state_mode:
            return es.state_answer_from_truth(self, truth)
        ans: dict[str, Any] = {}
        for item, name in zip(self._items, self._field_names, strict=True):
            if _is_cite(item):
                ans["citations"] = list(truth.get("_cite_refs", []))
            elif name in truth:
                ans[name] = truth[name]
        if "_cite_refs" in truth and "citations" not in ans:
            ans["citations"] = list(truth["_cite_refs"])
        return ans

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        if self._exec_mode:
            return es.exec_reference(self, public_inputs)
        if self._state_mode:
            return es.state_reference(self, public_inputs)
        ans: dict[str, Any] = {}
        data = public_inputs.get("data", {})
        for item, name in zip(self._items, self._field_names, strict=True):
            if _is_cite(item):
                ans["citations"] = list(_all_evidence(public_inputs))
            elif _is_gate(item):
                gctx = data.get(_dk(name) + "_context", {})
                ans[name] = F.gate_inferable(gctx, item)
            elif _dk(name) in data:
                ans[name] = F.infer_field(item, name, data[_dk(name)])
        return ans, list(_all_evidence(public_inputs))

    # ---- scoring ------------------------------------------------------------------
    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        if self._exec_mode:
            return es.exec_score(self, answer, truth, ctx)
        if self._state_mode:
            return es.state_score(self, answer, truth, ctx)
        comps: list[ItemScore] = []
        gates: list[GateOutcome] = []
        data = answer.model_dump()
        for item, name in zip(self._items, self._field_names, strict=True):
            if _is_cite(item):
                gates.append(F.cite_gate(data.get("citations"), ctx.evidence_ids, name=name))
            elif _is_gate(item):
                ok = str(data.get(name, "")).strip().lower() == str(truth.get(name, "")).lower()
                mode, factor = _gate_mode(item)
                gates.append(
                    GateOutcome(name=name, passed=ok, mode=mode, factor=factor, reason=item.field)
                )
            else:
                comps.append(self._score_one(item, name, data.get(name), truth.get(name)))
        return self._compose(comps, gates, truth)

    def _score_one(self, item: ParsedScoreItem, name: str, pred: Any, truth_val: Any) -> ItemScore:
        set_delta_agg = self._agg.kind is AggregateKind.SET_DELTA
        per_item_delta = "each component uses set_delta" in self._agg.notes
        if (set_delta_agg or per_item_delta) and item.kind is ScoreItemKind.SET:
            return F.set_delta_field(item, name, pred, truth_val)
        if self._agg.kind is AggregateKind.TECHNIQUE_TACTIC and item.kind is ScoreItemKind.ENUM:
            s, d = technique_tactic_score(pred, truth_val, _ATT_CK)
            return ItemScore(field=name, score=s, weight=item.weight, detail=d)
        return F.score_field(item, name, pred, truth_val, weight=item.weight)

    _FOLDED = {
        AggregateKind.FIXED_ITEM,
        AggregateKind.SET_DELTA,
        AggregateKind.FBETA,
        AggregateKind.KENDALL_TAU,
        AggregateKind.FRACTION_CORRECT,
        AggregateKind.TECHNIQUE_TACTIC,
        AggregateKind.ACCURACY,
        AggregateKind.MACRO_AVERAGE,
        AggregateKind.MIXTURE,
        AggregateKind.PRODUCT_GATES,
    }

    def _compose(
        self, comps: list[ItemScore], gates: list[GateOutcome], truth: Mapping[str, Any]
    ) -> ScoreParts:
        agg = self._agg
        if agg.kind is AggregateKind.ACCURACY:
            raw: float = sum(c.score for c in comps) / len(comps) if comps else 0.0
        elif agg.kind is AggregateKind.MACRO_AVERAGE:
            raw, _ = macro_average({c.field: c.score for c in comps})
        elif agg.kind is AggregateKind.FIXED_ITEM:
            # [A] (× [B] × ...): product of every scored factor, not just the first.
            raw = _product(c.score for c in comps) if comps else 0.0
        elif agg.kind is AggregateKind.PRODUCT_GATES:
            raw = _product(c.score for c in comps) if comps else 1.0
        elif agg.kind in (
            AggregateKind.SET_DELTA,
            AggregateKind.FBETA,
            AggregateKind.KENDALL_TAU,
            AggregateKind.FRACTION_CORRECT,
            AggregateKind.TECHNIQUE_TACTIC,
        ):
            raw = comps[0].score if comps else 0.0
        elif agg.kind is AggregateKind.MIXTURE:
            raw = sum((c.weight or 0.0) * c.score for c in comps)
        else:  # WEIGHTED_SUM and anything else -> weighted sum with normalised weights
            total_w = sum(c.weight or 0.0 for c in comps) or 1.0
            raw = sum((c.weight or 0.0) * c.score for c in comps) / (
                total_w if abs(total_w - 1.0) > 1e-6 else 1.0
            )
        # Source caps ("cap X nếu <dim> sai") -> a cap-gate that fails when the guarded dimension
        # is not fully correct; apply_gates then does min(score, cap).
        cap_gates = self._cap_gates(comps)
        # Source penalties ("- k x (count ...)") -> deduct k per extraneous element of the primary set.
        penalties = self._penalties(comps)
        if agg.kind in self._FOLDED:
            for c in comps:
                c.weight = None  # score already folded into raw; don't double-count via weighted()
        return ScoreParts(
            components=comps,
            gates=gates + cap_gates,
            penalties=penalties,
            raw_score=raw,
            trace=[f"{c.field}={c.score:.3f}" for c in comps]
            + [f"gate {g.name}={g.passed}" for g in gates + cap_gates],
        )

    def _cap_gates(self, comps: list[ItemScore]) -> list[GateOutcome]:
        out: list[GateOutcome] = []
        for cap in self._agg.caps:
            guarded = self._match_component(cap.condition, comps)
            passed = guarded.score >= 1.0 - 1e-9 if guarded is not None else False
            out.append(
                GateOutcome(
                    name=f"cap:{cap.condition[:40]}",
                    passed=passed,
                    mode="cap",
                    factor=cap.cap,
                    reason=f"cap {cap.cap} if '{cap.condition}'",
                )
            )
        return out

    def _penalties(self, comps: list[ItemScore]) -> list[tuple[str, int, float]]:
        out: list[tuple[str, int, float]] = []
        primary = next(
            (c for c in comps if "false_positives" in c.detail or "fp" in c.detail), None
        )
        for pen in self._agg.penalties:
            count = 0
            if primary is not None:
                count = int(
                    primary.detail.get("fp", len(primary.detail.get("false_positives", [])))
                )
            out.append((pen.count_of[:40], count, pen.per_item))
        return out

    def _match_component(self, condition: str, comps: list[ItemScore]) -> ItemScore | None:
        cond = condition.lower()
        for c in comps:
            tokens = [t for t in c.field.lower().replace("_", " ").split() if len(t) >= 3]
            if any(t in cond for t in tokens):
                return c
        return comps[0] if comps else None

    # ---- golden -------------------------------------------------------------------
    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        if self._exec_mode or self._state_mode:
            return es.golden_cases(self, bundle)
        cases: list[GoldenCase] = []
        empty: dict[str, Any] = {
            n: ([] if _is_list(i) else {} if _is_dict(i) else None)
            for i, n in zip(self._items, self._field_names, strict=True)
            if not _is_gate(i)
        }
        if any(_is_cite(i) for i in self._items):
            empty["citations"] = []
        # Empty answer: every scored component is empty/absent -> low score.
        cases.append(GoldenCase("empty_submission", empty, expected_max=0.6))

        # Nonempty-but-wrong: corrupt every scored field and every gate; must score strictly below
        # the oracle (this is what catches dropped factors / unbound gates / missing caps).
        oracle = self.answer_from_truth(bundle.sealed_truth)
        wrong = {k: _corrupt(k, v, self._items, self._field_names) for k, v in oracle.items()}
        cases.append(GoldenCase("all_fields_wrong", wrong, expected_max=0.5))

        # If any zero-mode hard gate exists, violating it alone must zero the whole score.
        gate_fields = [
            n
            for i, n in zip(self._items, self._field_names, strict=True)
            if _is_gate(i) and not _is_cite(i) and _gate_mode(i)[0] == "zero"
        ]
        if gate_fields:
            violated = dict(oracle)
            for n in gate_fields:
                violated[n] = "___violation___"
            cases.append(GoldenCase("hard_gate_violated", violated, expected_score=0.0))
        return cases


def _dk(name: str) -> str:
    """Namespace an input-fragment key so a field name never collides with a forbidden truth key."""
    return f"field__{name}"


def _corrupt(field: str, value: Any, items: list[ParsedScoreItem], names: list[str]) -> Any:
    """Return a deliberately wrong value of the same shape as `value` for a golden negative case."""
    if field == "citations":
        return ["___hallucinated___"]
    if isinstance(value, list):
        return []  # empty set/order -> wrong
    if isinstance(value, dict):
        # Shift far enough to fall outside every tolerance (±%, IoU interval, ±0 cells).
        return {
            k: (v * 3 + 1000 if isinstance(v, int | float) else "___x___") for k, v in value.items()
        }
    if isinstance(value, bool):
        return not value
    if isinstance(value, int | float):
        return value * 3 + 1000  # outside ±0 / ±% tolerance
    return "___wrong___"


def _product(values: Any) -> float:
    out = 1.0
    for v in values:
        out *= v
    return out


# Two-option domain for a non-ENUM hard gate: the agent must decide comply vs violation. Modelled
# like an enum (signal -> option by position) so it binds to a derivable decision, not a constant.
GATE_DOMAIN = ("comply", "violation")


def _is_cite(item: ParsedScoreItem) -> bool:
    return item.kind is ScoreItemKind.CITE


def _is_gate(item: ParsedScoreItem) -> bool:
    return item.is_gate or item.kind in (ScoreItemKind.GATE, ScoreItemKind.CITE)


def _gate_mode(item: ParsedScoreItem) -> tuple[Any, float | None]:
    if item.gate_mode == "factor":
        return "factor", item.gate_factor
    if item.gate_mode == "cap":
        return "cap", item.gate_factor
    return "zero", None


def _is_list(item: ParsedScoreItem) -> bool:
    return item.kind in (ScoreItemKind.SET, ScoreItemKind.ORDER)


def _is_dict(item: ParsedScoreItem) -> bool:
    return item.kind is ScoreItemKind.NUMERIC and (
        F.is_dict_numeric(item) or F.is_interval_numeric(item)
    )


def _all_evidence(public_inputs: Mapping[str, Any]) -> list[str]:
    # The runner passes evidence ids separately; the reference cites whatever the episode exposes.
    return []


def _build_output_model(
    sid: str,
    items: list[ParsedScoreItem],
    names: list[str],
    agg: ParsedAggregate,
    exec_mode: bool,
    state_mode: bool,
) -> type[BaseModel]:
    spec: dict[str, Any] = {}
    if exec_mode:
        spec["rule"] = (dict, {})
    elif state_mode:
        spec["actions"] = (list, [])
        spec["observations"] = (dict, {})
    else:
        for item, name in zip(items, names, strict=True):
            if _is_cite(item):
                continue
            if _is_gate(item):
                spec[name] = (str | None, None)
            elif item.kind in (ScoreItemKind.SET, ScoreItemKind.ORDER):
                spec[name] = (list, [])
            elif item.kind is ScoreItemKind.NUMERIC and (
                F.is_dict_numeric(item) or F.is_interval_numeric(item)
            ):
                spec[name] = (dict, {})
            elif item.kind is ScoreItemKind.NUMERIC:
                spec[name] = (float | None, None)
            else:
                spec[name] = (str | None, None)
    if any(_is_cite(i) for i in items):
        spec["citations"] = (list, [])
    model: type[BaseModel] = create_model(
        "Auto_" + sid.replace(".", "_"),
        __config__=ConfigDict(extra="forbid"),
        **spec,
    )
    return model


@cache
def auto_subtask_for(subtask_id: str) -> AutoSubtask:
    cls = type(
        "AutoSubtask_" + subtask_id.replace(".", "_"), (AutoSubtask,), {"SUBTASK_ID": subtask_id}
    )
    instance: AutoSubtask = cls()
    return instance
