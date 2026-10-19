"""T0397.002 (IR, file) — classify malicious persistence entries by location and type.

Source scorer: `F1 (đúng vị trí sai loại = 0.5 phần tử)` — an entry matched on location but with
the wrong persistence type earns half credit. Modelled with the partial-credit set primitive,
keyed on location, attribute = type.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field

from saber.domain.base import StrictModel
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng, iso

PersistType = Literal["run_key", "service", "scheduled_task", "wmi", "startup", "systemd"]
_BENIGN_LOCS = (
    ("run_key", r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run\OneDrive"),
    ("service", r"HKLM\System\CurrentControlSet\Services\Spooler"),
    ("scheduled_task", r"\Microsoft\Windows\UpdateOrchestrator\Refresh"),
    ("startup", r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\Teams.lnk"),
)
_MAL_LOCS = (
    ("run_key", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run\synthupd"),
    ("service", r"HKLM\System\CurrentControlSet\Services\synthsvc"),
    ("scheduled_task", r"\SynthLab\persist_task"),
    ("wmi", r"ROOT\subscription:CommandLineEventConsumer=synthConsumer"),
    ("startup", r"C:\Users\lab\AppData\Roaming\...\Startup\synth.lnk"),
    ("systemd", r"/etc/systemd/system/synth-agent.service"),
)


class PersistEntry(StrictModel):
    location: str
    type: PersistType


class T0397_002Output(StrictModel):
    entries: list[PersistEntry] = Field(default_factory=list)


def _key(e: Any) -> str:
    loc = e["location"] if isinstance(e, Mapping) else getattr(e, "location", "")
    return str(loc).replace("\\", "/").strip().lower()


def _attr(e: Any) -> str:
    typ = e["type"] if isinstance(e, Mapping) else getattr(e, "type", "")
    return str(typ).strip().lower()


class Subtask(SubtaskBase):
    SUBTASK_ID = "T0397.002"
    OutputModel = T0397_002Output
    VARIANTS = ("default", "dense")

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        m = rng.randint(4, 6) if variant == "dense" else rng.randint(2, 4)
        n_benign = rng.randint(6, 10)
        entries: list[dict[str, Any]] = []
        truth: list[dict[str, str]] = []
        chosen_mal = rng.sample(_MAL_LOCS, m)
        for typ, loc in chosen_mal:
            entries.append({"location": loc, "type": typ, "mtime": iso(rng.time())})
            truth.append({"location": loc, "type": typ})
        for _ in range(n_benign):
            typ, loc = rng.pick(_BENIGN_LOCS)
            entries.append({"location": loc, "type": typ, "mtime": iso(rng.time())})
        export = {
            "hv": "HV-16",
            "host": rng.hostname("ws"),
            "entries": rng.shuffle(entries),
            "note": "Registry/Service/Task/WMI/startup export; identify the malicious ones and their type.",
        }
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={"export": export},
            sealed_truth={"entries": truth, "m": m},
            evidence_ids=[_key(e) for e in entries],
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        return {"entries": [dict(e) for e in truth["entries"]]}

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        comp = self.set_partial_item(
            "entries",
            [e.model_dump() for e in answer.entries],
            truth["entries"],
            key_canon=_key,
            attr_canon=_attr,
            partial=0.5,
        )
        return ScoreParts(
            components=[comp],
            raw_score=comp.score,
            trace=[f"entries F1 partial -> {comp.score:.4f} ({comp.detail})"],
        )

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        truth = bundle.sealed_truth["entries"]
        if not truth:
            return []
        wrong_type = [
            {
                "location": truth[0]["location"],
                "type": "wmi" if truth[0]["type"] != "wmi" else "service",
            }
        ] + [dict(e) for e in truth[1:]]
        return [
            GoldenCase("empty", {"entries": []}, expected_score=0.0),
            GoldenCase(
                "right_loc_wrong_type", {"entries": wrong_type}, expected_min=0.5, expected_max=0.99
            ),
        ]
