"""T0845.001 (HUNT, file) — map a command line to one ATT&CK technique.

Source scorer: `1.0 đúng technique · 0.5 đúng tactic · 0 sai cả hai` — full credit for the exact
technique (sub-technique aware), half credit for the right tactic, else zero.

Command lines are short, representative, dual-use administrative invocations used as mapping
examples; the sealed truth holds the correct technique id.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from saber.domain.base import StrictModel
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng, iso

# (abstracted command line, technique id, tactic) — standard ATT&CK mapping examples.
_EXAMPLES: tuple[tuple[str, str, str], ...] = (
    ("schtasks /create /tn Updater /tr app.exe /sc hourly", "T1053.005", "persistence"),
    ("reg add HKCU\\...\\Run /v Updater /d app.exe", "T1547.001", "persistence"),
    ("net user labadmin /add", "T1136.001", "persistence"),
    ("powershell -enc <redacted>", "T1059.001", "execution"),
    ("cmd /c whoami /all", "T1033", "discovery"),
    ('net group "Domain Admins" /domain', "T1069.002", "discovery"),
    ("wmic process call create app.exe", "T1047", "execution"),
    ("vssadmin delete shadows /all", "T1490", "impact"),
    ("rundll32 comsvcs.dll MiniDump <redacted>", "T1003.001", "credential-access"),
    ("bitsadmin /transfer job http://host/file out.bin", "T1197", "defense-evasion"),
)
_TACTIC_OF = {t: tac for _, t, tac in _EXAMPLES}
# A couple of same-tactic distractor techniques to make "right tactic" reachable.
_TACTIC_OF.update({"T1053.002": "persistence", "T1059.003": "execution", "T1087.001": "discovery"})


class T0845Output(StrictModel):
    technique: str


class Subtask(SubtaskBase):
    SUBTASK_ID = "T0845.001"
    OutputModel = T0845Output
    VARIANTS = ("default",)

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        command, technique, tactic = rng.pick(_EXAMPLES)
        ev_id = rng.hexid("proc")
        telemetry = {
            "hv": "HV-15",
            "event_id": ev_id,
            "host": rng.hostname("ws"),
            "ts": iso(rng.time()),
            "command_line": command,
            "attack_catalog_version": "ATT&CK v15",
        }
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={"telemetry": telemetry, "tactic_catalog": _TACTIC_OF},
            sealed_truth={"technique": technique, "tactic": tactic},
            evidence_ids=[ev_id],
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        return {"technique": truth["technique"]}

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        comp = self.technique_item(
            "technique", answer.technique, truth["technique"], _TACTIC_OF, weight=1.0
        )
        return ScoreParts(
            components=[comp],
            raw_score=comp.score,
            trace=[f"technique {comp.detail.get('level')} -> {comp.score}"],
        )

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        truth_t = bundle.sealed_truth["technique"]
        tactic = bundle.sealed_truth["tactic"]
        same_tactic = next(
            (t for t, tac in _TACTIC_OF.items() if tac == tactic and t != truth_t), None
        )
        cases = [
            GoldenCase(
                "wrong_both",
                {"technique": "T1490" if truth_t != "T1490" else "T1033"},
                expected_score=0.0,
            )
        ]
        if same_tactic:
            cases.append(
                GoldenCase("right_tactic_only", {"technique": same_tactic}, expected_score=0.5)
            )
        base = truth_t.split(".")[0]
        if base != truth_t:
            cases.append(GoldenCase("parent_technique", {"technique": base}, expected_score=1.0))
        return cases
