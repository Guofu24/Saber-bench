"""T1112.001 (MON, file) — validate a network alert as true or false positive.

Source scenario: given one alert plus the alerted file, answer whether the alert is correct
(TP) or a false positive (FP). Source scorer: `[verdict]` (single enum item, exact match).

The DEV fixture presents abstracted alert features (no runnable payloads). Hard false positives
are legitimate admin/IT activity that commonly trips signatures; true positives are attack-shaped
but inert. The TP/FP label lives only in sealed truth.
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
from saber.subtasks._hv.common import INERT_FAMILIES, Rng, iso

Verdict = Literal["TP", "FP"]


class T1112Output(StrictModel):
    verdict: Verdict


# (description, verdict, rule_name, severity, feature-profile) — features are abstracted booleans.
_TEMPLATES: tuple[tuple[str, Verdict, str, str, dict[str, Any]], ...] = (
    (
        "Office document spawned a scripting host that reached an external host",
        "TP",
        "SIGMA_OFFICE_SPAWNS_INTERPRETER",
        "high",
        {
            "parent_is_office": True,
            "child_is_interpreter": True,
            "encoded_arguments": True,
            "external_network": True,
            "file_signed": False,
            "org_prevalence": "rare",
        },
    ),
    (
        "Unsigned binary dropped in a temp directory with low prevalence and outbound beacon",
        "TP",
        "EDR_SUSPICIOUS_DROPPER",
        "high",
        {
            "dropped_in_temp": True,
            "file_signed": False,
            "org_prevalence": "rare",
            "periodic_outbound": True,
            "autoruns_entry": True,
        },
    ),
    (
        "IT administrator ran a remote-execution utility during an approved change window",
        "FP",
        "SIGMA_REMOTE_EXEC_TOOL",
        "medium",
        {
            "tool_is_admin_utility": True,
            "source_in_admin_subnet": True,
            "file_signed": True,
            "signer": "trusted-it-vendor",
            "change_ticket_present": True,
            "org_prevalence": "common",
        },
    ),
    (
        "Backup agent opened many files quickly, matching a mass-access heuristic",
        "FP",
        "SIEM_MASS_FILE_ACCESS",
        "medium",
        {
            "process_is_backup_agent": True,
            "file_signed": True,
            "signer": "backup-vendor",
            "scheduled_window": True,
            "org_prevalence": "common",
        },
    ),
    (
        "Security scanner probed internal hosts, matching a port-scan rule",
        "FP",
        "NSM_PORT_SCAN",
        "low",
        {"source_is_known_scanner": True, "scanner_whitelisted": True, "org_prevalence": "common"},
    ),
)


class Subtask(SubtaskBase):
    SUBTASK_ID = "T1112.001"
    OutputModel = T1112Output
    VARIANTS = ("tp", "fp")

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        want = {"tp": "TP", "fp": "FP"}.get(variant)
        pool = [t for t in _TEMPLATES if want is None or t[1] == want]
        desc, verdict, rule_name, severity, features = rng.pick(pool)
        host = rng.hostname("ws")
        user = rng.username()
        alert_id = rng.hexid("ALERT")
        file_ctx = {
            "path": f"C:/Users/{user}/Downloads/{rng.hexid('obj', 4)}.bin"
            if verdict == "TP"
            else f"C:/Program Files/{rng.pick(('Backup', 'ITTools', 'Scanner'))}/agent.exe",
            "sha256": rng.sha256("file"),
            "signed": bool(features.get("file_signed")),
            "signer": features.get("signer"),
            "org_prevalence": features.get("org_prevalence", "unknown"),
            # Every alerted file carries an AV heuristic tag (that is why it fired); a benign PUA
            # tool gets one too, so the tag is NOT a label tell and must not be bijective with TP/FP.
            "heuristic_family": rng.pick(INERT_FAMILIES),
        }
        alert = {
            "hv": "HV-01",
            "alert_id": alert_id,
            "created_at": iso(rng.time()),
            "rule_name": rule_name,
            "severity": severity,
            "host": host,
            "user": user,
            "description": desc,
            "features": features,
            "alerted_file": file_ctx,
        }
        public_inputs = {"alert": alert}
        sealed = {"verdict": verdict, "rationale": desc}
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs=public_inputs,
            sealed_truth=sealed,
            evidence_ids=[alert_id],
            notes="Abstracted alert features; TP inert/attack-shaped, FP legitimate admin activity.",
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        return {"verdict": truth["verdict"]}

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        comp = self.enum_item(
            "verdict", answer.verdict, truth["verdict"], valid_labels=["TP", "FP"], weight=1.0
        )
        return ScoreParts(
            components=[comp],
            raw_score=comp.score,
            trace=[f"verdict pred={answer.verdict} truth={truth['verdict']} -> {comp.score}"],
        )

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        """B0 heuristic: unsigned + rare + attack-shaped features -> TP, else FP."""
        f = public_inputs["alert"]["features"]
        tp_signals = sum(
            bool(f.get(k))
            for k in (
                "encoded_arguments",
                "external_network",
                "periodic_outbound",
                "dropped_in_temp",
                "autoruns_entry",
            )
        )
        benign_signals = sum(
            bool(f.get(k))
            for k in (
                "tool_is_admin_utility",
                "change_ticket_present",
                "scanner_whitelisted",
                "process_is_backup_agent",
                "scheduled_window",
            )
        )
        verdict = "TP" if tp_signals > benign_signals else "FP"
        return {"verdict": verdict}, [public_inputs["alert"]["alert_id"]]

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        other = "FP" if bundle.sealed_truth["verdict"] == "TP" else "TP"
        return [
            GoldenCase("wrong_verdict", {"verdict": other}, expected_score=0.0),
            GoldenCase(
                "invalid_label",
                {"verdict": "MAYBE"},
                expected_score=0.0,
                expect_trace_contains="schema_invalid_submission",
            ),
        ]
