"""Gold pilot T1112.002 (MON, file) — validate an alert (verdict + firing rule + affected asset).

Artifact: an alert plus raw telemetry ±60 min. The verdict (TP/FP) is independently derived from
whether the surrounding telemetry CORROBORATES the alert's claim (a malicious process chain and an
external connection ⇒ TP; a signed admin tool in an approved change window ⇒ FP). The rule and the
asset are observable facts in the alert. Scored by the source Σ wᵢ·sᵢ (verdict 0.5, rule 0.25,
asset 0.25) via the existing bespoke scorer.
"""

from __future__ import annotations

from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.subtasks._hv.common import Rng, iso

# (verdict, rule, corroborating telemetry lines, benign/attack narrative)
_TP = (
    (
        "SIGMA_OFFICE_SPAWNS_INTERPRETER",
        [
            "winword.exe -> powershell.exe (encoded command line)",
            "powershell.exe opened TCP to 203.0.113.44:443 (rare external host)",
        ],
    ),
    (
        "EDR_DROPPER",
        [
            "unsigned binary written to %TEMP%\\u7f2.exe (prevalence 1)",
            "u7f2.exe created Run key and beaconed to 198.51.100.9 every 60s",
        ],
    ),
)
_FP = (
    (
        "SIGMA_REMOTE_EXEC_TOOL",
        [
            "PsExec.exe signed by 'Microsoft' launched from admin subnet 10.20.0.0/24",
            "change ticket CHG-20471 linked; no external connection in window",
        ],
    ),
    (
        "SIEM_MASS_FILE_ACCESS",
        [
            "veeam-agent.exe (signed) read 4000 files during scheduled 02:00 backup window",
            "no process injection, no outbound connection",
        ],
    ),
)
_TP_SIGNALS = ("encoded command", "rare external host", "beaconed", "run key", "unsigned binary")
_FP_SIGNALS = (
    "signed by",
    "change ticket",
    "backup window",
    "no external connection",
    "no outbound connection",
)


class Pilot(GoldPilot):
    SUBTASK_ID = "T1112.002"
    SOURCE_VERSIONS = {"alert_schema": "HV-01", "log_schema": "HV-02"}
    OUTPUT_SPEC = 'JSON {"verdict": "TP"|"FP", "triggering_rule": "<rule name from the alert>", "affected_asset": "<hostname>"}'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        is_tp = rng.chance(0.5)
        rule, telem = rng.pick(_TP if is_tp else _FP)
        host = rng.hostname("ws")
        alert_id = rng.hexid("ALERT")
        t0 = rng.time()
        logs = [{"ts": iso(t0), "host": host, "detail": d} for d in telem]
        public = {
            "alert": {
                "hv": "HV-01",
                "alert_id": alert_id,
                "rule_name": rule,
                "host": host,
                "claim": "alert asserts malicious activity on this asset",
            },
            "logs": {"hv": "HV-02", "window": "+/-60min", "lines": logs},
            "objective": "Decide TP/FP from whether the telemetry corroborates the alert; name the firing rule and the affected asset.",
        }
        gold_truth = {
            "verdict": "TP" if is_tp else "FP",
            "triggering_rule": rule,
            "affected_asset": host,
        }
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored alert + corroborating/refuting telemetry; verdict follows the telemetry, not a label field",
            independent_derivation="verifier re-derives the verdict from telemetry signal words (TP: encoded/beacon/unsigned/rare host; FP: signed/change-ticket/backup-window/no external); must equal the authored verdict",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "FP cases are signed admin tools in approved windows that fire the same rules as TP cases"
            ],
            adjudication_required=[],
        )
        return finalize(
            self.SUBTASK_ID, split, seed, public, gold_truth, prov, evidence_ids=[alert_id]
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        text = " ".join(line["detail"].lower() for line in episode.public_inputs["logs"]["lines"])
        tp = sum(s in text for s in _TP_SIGNALS)
        fp = sum(s in text for s in _FP_SIGNALS)
        derived = "TP" if tp > fp else "FP"
        if derived == episode.gold_truth["verdict"]:
            return VerificationResult(True, f"telemetry-derived verdict={derived}", ["verdict"])
        return VerificationResult(
            False, f"derived {derived} != gold {episode.gold_truth['verdict']}"
        )

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return dict(episode.gold_truth)
