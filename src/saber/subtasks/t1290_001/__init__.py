"""T1290.001 (MON, file) — compute five monthly report metrics from an alert CSV.

Source scorer: `(số ô đúng)/5` — each of five numeric cells is exact (`num/±0`); score is the
fraction correct. The verifier recomputes the five numbers from the raw rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from saber.domain.base import StrictModel
from saber.grading.primitives import fraction_correct, score_numeric
from saber.grading.results import ItemScore
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng, iso

_SEVERITIES = ("critical", "high", "medium", "low")
_METRIC_KEYS = (
    "total_alerts",
    "true_positives",
    "false_positives",
    "critical_high",
    "distinct_rules",
)


class T1290Output(StrictModel):
    metrics: dict[str, float] = Field(default_factory=dict)


class Subtask(SubtaskBase):
    SUBTASK_ID = "T1290.001"
    OutputModel = T1290Output
    VARIANTS = ("default",)

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        n = rng.randint(60, 160)
        rows: list[dict[str, Any]] = []
        rules = [f"RULE_{i:03d}" for i in range(rng.randint(5, 12))]
        for i in range(n):
            sev = rng.pick(_SEVERITIES)
            verdict = "TP" if rng.chance(0.35) else "FP"
            rows.append(
                {
                    "id": f"a{i}",
                    "ts": iso(rng.time(max_minutes=43200)),
                    "severity": sev,
                    "verdict": verdict,
                    "rule": rng.pick(rules),
                }
            )
        metrics = {
            "total_alerts": float(n),
            "true_positives": float(sum(r["verdict"] == "TP" for r in rows)),
            "false_positives": float(sum(r["verdict"] == "FP" for r in rows)),
            "critical_high": float(sum(r["severity"] in ("critical", "high") for r in rows)),
            "distinct_rules": float(len({r["rule"] for r in rows})),
        }
        csv = {
            "hv": "HV-06",
            "period": "30d",
            "columns": ["id", "ts", "severity", "verdict", "rule"],
            "rows": rows,
        }
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={"csv": csv, "required_metrics": list(_METRIC_KEYS)},
            sealed_truth={"metrics": metrics},
            evidence_ids=[r["id"] for r in rows],
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        return {"metrics": dict(truth["metrics"])}

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        flags: list[bool] = []
        detail: dict[str, Any] = {}
        for key in _METRIC_KEYS:
            s, d = score_numeric(answer.metrics.get(key), truth["metrics"][key], "±0")
            flags.append(s == 1.0)
            detail[key] = {"ok": s == 1.0, **d}
        score, frac_detail = fraction_correct(flags)
        comp = ItemScore(
            field="metrics", score=score, weight=1.0, detail={"cells": detail, **frac_detail}
        )
        return ScoreParts(
            components=[comp],
            raw_score=score,
            trace=[f"metrics {frac_detail['correct']}/5 correct -> {score:.3f}"],
        )

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        rows = public_inputs["csv"]["rows"]
        metrics = {
            "total_alerts": float(len(rows)),
            "true_positives": float(sum(r["verdict"] == "TP" for r in rows)),
            "false_positives": float(sum(r["verdict"] == "FP" for r in rows)),
            "critical_high": float(sum(r["severity"] in ("critical", "high") for r in rows)),
            "distinct_rules": float(len({r["rule"] for r in rows})),
        }
        return {"metrics": metrics}, []

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        truth = dict(bundle.sealed_truth["metrics"])
        three = dict(truth)
        three["total_alerts"] = truth["total_alerts"] + 1
        three["true_positives"] = truth["true_positives"] + 1
        return [
            GoldenCase("all_zero", {"metrics": dict.fromkeys(_METRIC_KEYS, 0.0)}, expected_max=0.8),
            GoldenCase("three_of_five", {"metrics": three}, expected_score=0.6),
        ]
