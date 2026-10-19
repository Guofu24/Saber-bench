"""T1348.001 (MON, file) — list process names that masquerade as system binaries.

Source scenario: given N processes, M of which impersonate a system process name (for example a
look-alike of `svchost.exe`), list the masquerading processes. Source scorer:
`masquerading[]` (set/proc) with aggregate `max(0, M'/M - N'/(N'+M'))`.

Masquerading is modelled by look-alike names and/or a wrong image directory for a known system
binary. All data is synthetic and inert.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from saber.domain.base import StrictModel
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import SYSTEM_PROCESSES, Rng, iso


def _full_key(value: Any) -> str:
    """Masquerade identity is (name, image_path): keep both, normalise slashes and case."""
    return str(value).replace("\\", "/").strip().lower()


# Legitimate system image directories, keyed by process name (lower-cased basename).
_LEGIT_DIRS = {
    "svchost.exe": "C:/Windows/System32",
    "lsass.exe": "C:/Windows/System32",
    "csrss.exe": "C:/Windows/System32",
    "services.exe": "C:/Windows/System32",
    "explorer.exe": "C:/Windows",
    "winlogon.exe": "C:/Windows/System32",
    "spoolsv.exe": "C:/Windows/System32",
    "taskhostw.exe": "C:/Windows/System32",
}
_HOMOGLYPH = {"o": "0", "l": "1", "i": "1", "c": "с", "s": "ѕ"}


def _lookalike(rng: Rng, name: str) -> str:
    stem, _, ext = name.partition(".")
    chars = list(stem)
    swaps = [i for i, c in enumerate(chars) if c in _HOMOGLYPH]
    if swaps:
        i = rng.pick(swaps)
        chars[i] = _HOMOGLYPH[chars[i]]
    else:
        chars.insert(len(chars) // 2, rng.pick("x0z1"))
    return "".join(chars) + "." + ext


class ProcessEntry(StrictModel):
    pid: int
    name: str
    image_path: str


class T1348Output(StrictModel):
    masquerading: list[str] = Field(default_factory=list)


class Subtask(SubtaskBase):
    SUBTASK_ID = "T1348.001"
    OutputModel = T1348Output
    VARIANTS = ("default", "benign_only", "dense")

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        n_total = {"benign_only": rng.randint(12, 18), "dense": rng.randint(18, 24)}.get(
            variant, rng.randint(14, 22)
        )
        m_target = (
            0
            if variant == "benign_only"
            else (rng.randint(5, 8) if variant == "dense" else rng.randint(2, 4))
        )
        processes: list[dict[str, Any]] = []
        masquerading: list[str] = []
        pid = 1000
        # Benign legitimate system processes in correct directories.
        for _ in range(n_total - m_target):
            name = rng.pick(SYSTEM_PROCESSES)
            legit_dir = _LEGIT_DIRS.get(name.lower(), "C:/Windows/System32")
            processes.append({"pid": pid, "name": name, "image_path": f"{legit_dir}/{name}"})
            pid += 1
        # Masquerading: look-alike name, or correct name from a wrong (user-writable) directory.
        for _ in range(m_target):
            base = rng.pick(tuple(_LEGIT_DIRS))
            if rng.chance(0.6):
                fake = _lookalike(rng, base)
                path = f"C:/Users/{rng.username()}/AppData/Local/Temp/{fake}"
            else:
                fake = base  # right name, wrong place
                path = f"C:/Users/{rng.username()}/AppData/Roaming/{fake}"
            key = f"{fake}@{path}"
            processes.append({"pid": pid, "name": fake, "image_path": path})
            masquerading.append(key)
            pid += 1
        processes = rng.shuffle(processes)
        telemetry = {
            "hv": "HV-15",
            "captured_at": iso(rng.time()),
            "host": rng.hostname("ws"),
            "legit_system_dirs": _LEGIT_DIRS,
            "processes": processes,
        }
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={"telemetry": telemetry},
            sealed_truth={"masquerading": sorted(masquerading), "m": m_target, "n": n_total},
            evidence_ids=[f"proc-{p['pid']}" for p in processes],
            notes="Masquerading = look-alike name or legit name from a user-writable directory.",
            expected_reference_score=1.0 if m_target else 1.0,
        )

    def _elements(self, processes: list[dict[str, Any]], names_only: bool) -> list[str]:
        out = []
        for p in processes:
            out.append(p["name"] if names_only else f"{p['name']}@{p['image_path']}")
        return out

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        return {"masquerading": list(truth["masquerading"])}

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        comp = self.delta_item(
            "masquerading", answer.masquerading, truth["masquerading"], canon=_full_key
        )
        return ScoreParts(
            components=[comp],
            raw_score=comp.score,
            trace=[f"masquerading set-delta -> {comp.score:.4f} ({comp.detail})"],
        )

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        tele = public_inputs["telemetry"]
        legit = {k.lower(): v for k, v in tele["legit_system_dirs"].items()}
        found: list[str] = []
        for p in tele["processes"]:
            name_l = p["name"].lower()
            key = f"{p['name']}@{p['image_path']}"
            if name_l in legit:
                if not p["image_path"].lower().startswith(legit[name_l].lower()):
                    found.append(key)  # right name, wrong directory
            else:
                # look-alike of a known system process (one-edit distance on the stem)
                stem = name_l.split(".")[0]
                for known in legit:
                    kstem = known.split(".")[0]
                    if abs(len(stem) - len(kstem)) <= 1 and stem != kstem and _close(stem, kstem):
                        found.append(key)
                        break
        return {"masquerading": sorted(set(found))}, [f"proc-{p['pid']}" for p in tele["processes"]]

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        truth = bundle.sealed_truth["masquerading"]
        cases = [
            GoldenCase(
                "empty_answer", {"masquerading": []}, expected_score=1.0 if not truth else 0.0
            ),
        ]
        if truth:
            cases.append(
                GoldenCase(
                    "one_false_positive",
                    {"masquerading": truth + ["svchost.exe@C:/Windows/System32/svchost.exe"]},
                    expected_max=0.99,
                )
            )
            cases.append(
                GoldenCase(
                    "half_missed", {"masquerading": truth[: len(truth) // 2]}, expected_max=0.9
                )
            )
        return cases


def _close(a: str, b: str) -> bool:
    """True if a and b differ by a single substitution/insertion (cheap homoglyph check)."""
    if a == b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    longer, shorter = (a, b) if len(a) > len(b) else (b, a)
    if len(longer) - len(shorter) != 1:
        return False
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))
