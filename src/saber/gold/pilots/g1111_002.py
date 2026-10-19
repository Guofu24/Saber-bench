"""Gold pilot T1111.002 (CNT, file) — tune a noisy rule and diagnose the false-positive cause.

Artifact: a noisy detection rule plus the alerts it produced; M are false positives that share a
benign attribute (e.g. source is the signed backup agent), the rest are true positives. The solver
returns (a) a suppression filter and (b) the FP root cause in {rule_logic, data_quality,
environment_change}. Ground truth labels come from an independent benign-attribute check; the cause
is derivable from the rule text (a missing exclusion ⇒ rule_logic). Scored Σ wᵢ·sᵢ: filter
effectiveness max(0, ΔFP% − ΔTP_lost%) (0.7) + cause enum (0.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.grading.execsandbox import evaluate_filter
from saber.grading.primitives import delta_fp_tp, score_enum
from saber.grading.results import ItemScore, ScoreResult
from saber.subtasks._hv.common import Rng

_CAUSES = ("rule_logic", "data_quality", "environment_change")


class Pilot(GoldPilot):
    SUBTASK_ID = "T1111.002"
    SOURCE_VERSIONS = {"artifact": "rule+alert-replay"}
    OUTPUT_SPEC = (
        'JSON {"filter": {"all_of": [{"field": "<f>", "op": "eq|contains|in|regex", "value": <v>}]}, '
        '"fp_cause": "rule_logic|data_quality|environment_change"}'
    )

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        backup_acct = "svc-veeam-backup"
        rule = {
            "id": "RULE_MASS_FILE_ACCESS",
            "logic": "alert when a process reads > 1000 files in 10 min",
            "known_exclusions": [],  # missing the backup-agent exclusion -> rule_logic cause
        }
        n_fp = rng.randint(5, 8)
        n_tp = rng.randint(3, 5)
        alerts: list[dict[str, Any]] = []
        for i in range(n_fp):
            alerts.append(
                {
                    "id": f"a{i}",
                    "process": {"name": "veeam-agent.exe"},
                    "account": backup_acct,
                    "files_read": rng.randint(1200, 5000),
                    "signed": True,
                    "verdict": "FP",
                }
            )
        for j in range(n_tp):
            alerts.append(
                {
                    "id": f"a{n_fp + j}",
                    "process": {"name": rng.pick(("ransom.exe", "wiper.exe"))},
                    "account": rng.username(),
                    "files_read": rng.randint(1100, 9000),
                    "signed": False,
                    "verdict": "TP",
                }
            )
        alerts = rng.shuffle(alerts)
        public = {
            "rule": rule,
            "alerts": [
                {k: v for k, v in a.items() if k != "verdict"} for a in alerts
            ],  # hide the verdict label
            "objective": "Write a filter that suppresses the false positives without losing true positives, and name the FP root cause.",
        }
        gold_truth = {
            "fp_ids": sorted(str(a["id"]) for a in alerts if a["verdict"] == "FP"),
            "tp_ids": sorted(str(a["id"]) for a in alerts if a["verdict"] == "TP"),
            "fp_cause": "rule_logic",
            "_alerts": [dict(a) for a in alerts],  # retained for grading (sealed)
        }
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored noisy mass-file-access rule + alerts; FPs are the signed backup agent; rule lacks the exclusion",
            independent_derivation="FP set re-derived from the benign attribute (signed backup account); cause=rule_logic because the rule has no backup exclusion",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "TP ransomware reads many files too; filtering purely on file-count would lose TPs"
            ],
            adjudication_required=[
                "the single-label FP cause can be multi-factor in reality; owner to confirm the primary cause taxonomy"
            ],
        )
        return finalize(
            self.SUBTASK_ID,
            split,
            seed,
            public,
            gold_truth,
            prov,
            evidence_ids=[str(a["id"]) for a in alerts],
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        alerts = episode.gold_truth["_alerts"]
        # Independent: FP iff signed AND backup service account; cause rule_logic iff no exclusion.
        rederived_fp = sorted(
            a["id"] for a in alerts if a.get("signed") and "backup" in a.get("account", "")
        )
        cause = (
            "rule_logic"
            if not episode.public_inputs["rule"]["known_exclusions"]
            else "data_quality"
        )
        if rederived_fp == episode.gold_truth["fp_ids"] and cause == episode.gold_truth["fp_cause"]:
            return VerificationResult(
                True,
                f"benign-attribute verifier matched {len(rederived_fp)} FPs; cause={cause}",
                ["fp_ids", "fp_cause"],
            )
        return VerificationResult(
            False,
            f"derived fp={rederived_fp} cause={cause} vs gold fp={episode.gold_truth['fp_ids']} cause={episode.gold_truth['fp_cause']}",
        )

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {
            "filter": {
                "all_of": [
                    {"field": "account", "op": "contains", "value": "backup"},
                    {"field": "signed", "op": "eq", "value": True},
                ]
            },
            "fp_cause": "rule_logic",
        }

    def grade(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        *,
        agent_id: str,
        evidence_refs: list[str] | None = None,
    ) -> ScoreResult:
        alerts = episode.gold_truth["_alerts"]
        fp_ids = set(episode.gold_truth["fp_ids"])
        tp_ids = set(episode.gold_truth["tp_ids"])
        expr = answer.get("filter") or {}
        flags, parse_ok = evaluate_filter(expr, alerts)
        if not parse_ok:
            filt_score, detail = 0.0, {"parse_ok": False}
        else:
            suppressed = {alerts[i]["id"] for i, f in enumerate(flags) if f}
            fp_removed = len(suppressed & fp_ids)
            tp_lost = len(suppressed & tp_ids)
            filt_score, detail = delta_fp_tp(
                fp_before=len(fp_ids),
                fp_after=len(fp_ids) - fp_removed,
                tp_before=len(tp_ids),
                tp_after=len(tp_ids) - tp_lost,
            )
        cs, cd = score_enum(
            answer.get("fp_cause"), episode.gold_truth["fp_cause"], valid_labels=list(_CAUSES)
        )
        score = 0.7 * filt_score + 0.3 * cs
        comps = [
            ItemScore(field="filter", score=filt_score, weight=0.7, detail=detail),
            ItemScore(field="fp_cause", score=cs, weight=0.3, detail=cd),
        ]
        return self._result(
            episode,
            answer,
            score,
            components=comps,
            trace=[f"filter={filt_score:.3f}", f"fp_cause={cs}"],
        )
