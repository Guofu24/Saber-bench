"""T1112.002 (MON, file) — verdict plus triggering rule and affected asset.

Source scorer: `Σ wᵢ·sᵢ` over verdict (0.5), triggering_rule (0.25), affected_asset (0.25).
Adds raw log context (HV-02) so the solver can name the firing rule and asset.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from saber.domain.base import StrictModel
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng, iso

Verdict = Literal["TP", "FP"]
# (rule, verdict, raw-log evidence lines). The verdict must be INFERRED from the evidence lines,
# never read from a label field. TP lines show attack-shaped behaviour; FP lines show the benign
# cause (approved change, whitelisted scanner) that explains why the rule fired.
_TEMPLATES: tuple[tuple[str, Verdict, tuple[str, ...]], ...] = (
    (
        "SIGMA_OFFICE_SPAWNS_INTERPRETER",
        "TP",
        (
            "winword.exe spawned an interpreter with encoded arguments",
            "interpreter opened an external connection to a rare host",
        ),
    ),
    (
        "EDR_SUSPICIOUS_DROPPER",
        "TP",
        (
            "unsigned binary written to a user temp directory",
            "binary created an autorun entry and beaconed outbound",
        ),
    ),
    (
        "SIGMA_REMOTE_EXEC_TOOL",
        "FP",
        (
            "remote-exec utility signed by a trusted IT vendor",
            "source host is in the admin subnet and an approved change ticket is linked",
        ),
    ),
    (
        "SIEM_MASS_FILE_ACCESS",
        "FP",
        (
            "process is the signed backup agent",
            "activity occurred inside the scheduled backup window",
        ),
    ),
    (
        "NSM_PORT_SCAN",
        "FP",
        (
            "source is a whitelisted vulnerability scanner",
            "scan matches the scheduled monthly sweep",
        ),
    ),
)
_TP_MARKERS = (
    "encoded arguments",
    "unsigned binary",
    "beaconed",
    "autorun",
    "external connection to a rare host",
)
_FP_MARKERS = (
    "trusted IT vendor",
    "approved change ticket",
    "backup agent",
    "whitelisted",
    "scheduled",
)


class T1112_002Output(StrictModel):
    verdict: Verdict
    triggering_rule: str
    affected_asset: str


class Subtask(SubtaskBase):
    SUBTASK_ID = "T1112.002"
    OutputModel = T1112_002Output
    VARIANTS = ("tp", "fp")

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        want: Verdict | None = {"tp": "TP", "fp": "FP"}.get(variant)  # type: ignore[assignment]
        pool = [t for t in _TEMPLATES if want is None or t[1] == want]
        rule, verdict, evidence = rng.pick(pool)
        host = rng.hostname("ws")
        alert_id = rng.hexid("ALERT")
        t0 = rng.time()
        raw = [{"ts": iso(t0), "host": host, "rule": rule, "event": "alert_raised", "asset": host}]
        raw += [
            {"ts": iso(t0), "host": host, "event": "context", "detail": line} for line in evidence
        ]
        alert = {"hv": "HV-01", "alert_id": alert_id, "rule_name": rule, "host": host}
        logs = {"hv": "HV-02", "window": "+/-60min", "lines": raw}
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={"alert": alert, "logs": logs},
            sealed_truth={"verdict": verdict, "triggering_rule": rule, "affected_asset": host},
            evidence_ids=[alert_id],
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "verdict": truth["verdict"],
            "triggering_rule": truth["triggering_rule"],
            "affected_asset": truth["affected_asset"],
        }

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        comps = [
            self.enum_item("verdict", answer.verdict, truth["verdict"], valid_labels=["TP", "FP"]),
            self.enum_item("triggering_rule", answer.triggering_rule, truth["triggering_rule"]),
            self.enum_item("affected_asset", answer.affected_asset, truth["affected_asset"]),
        ]
        return ScoreParts(components=comps, trace=[f"{c.field}={c.score}" for c in comps])

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        alert = public_inputs["alert"]
        text = " ".join(line.get("detail", "") for line in public_inputs["logs"]["lines"]).lower()
        tp_hits = sum(m in text for m in _TP_MARKERS)
        fp_hits = sum(m in text for m in _FP_MARKERS)
        verdict = "TP" if tp_hits > fp_hits else "FP"
        return {
            "verdict": verdict,
            "triggering_rule": alert["rule_name"],
            "affected_asset": alert["host"],
        }, [alert["alert_id"]]

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        t = bundle.sealed_truth
        other = "FP" if t["verdict"] == "TP" else "TP"
        return [
            GoldenCase(
                "verdict_only",
                {"verdict": t["verdict"], "triggering_rule": "WRONG", "affected_asset": "nope"},
                expected_score=0.5,
            ),
            GoldenCase(
                "wrong_verdict_right_rest",
                {
                    "verdict": other,
                    "triggering_rule": t["triggering_rule"],
                    "affected_asset": t["affected_asset"],
                },
                expected_score=0.5,
            ),
        ]
