"""Gold pilot T1406.001 (CNT, file) — author a YARA rule for a malware family (F1 over samples).

Artifact: byte samples — M from one family (sharing a stable config marker) and N clean files,
including a HARD NEGATIVE clean file carrying a similar-looking but different string. The solver
writes a YARA-subset rule; it is run over both sets and scored by sample-level F1. Ground truth
(which samples are family) is independently derived by checking the family marker's presence — a
route distinct from the rule the solver writes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.grading.execsandbox import run_yara_subset
from saber.grading.primitives import score_set
from saber.grading.results import ItemScore, ScoreResult
from saber.subtasks._hv.common import Rng

_MARKER = "cfg=SynthBeacon;v=3;"  # stable family config string shared by all family samples
_NEAR_MISS = "cfg=SynthBackup;v=3;"  # benign tool, similar shape, different name (hard negative)


def _family_sample(rng: Rng) -> bytes:
    pre = bytes(rng.randint(0, 255) for _ in range(rng.randint(16, 48)))
    post = bytes(rng.randint(0, 255) for _ in range(rng.randint(16, 48)))
    return pre + _MARKER.encode() + f"id={rng.hexid('', 4)}".encode() + post


def _clean_sample(rng: Rng, near_miss: bool) -> bytes:
    body = f"GoodApp build {rng.randint(1, 9)}.{rng.randint(0, 9)} ".encode()
    if near_miss:
        body += _NEAR_MISS.encode()
    else:
        body += bytes(rng.randint(32, 126) for _ in range(rng.randint(20, 60)))
    return bytes(rng.randint(0, 255) for _ in range(8)) + body


class Pilot(GoldPilot):
    SUBTASK_ID = "T1406.001"
    SOURCE_VERSIONS = {"engine": "saber-yara-subset", "family": "SynthBeacon"}
    OUTPUT_SPEC = (
        'JSON {"rule": {"name": "<id>", "strings": {"$a": {"kind": "text|hex|regex", '
        '"value": "...", "nocase": false}}, "condition": "any of them|all of them|$a"}}'
    )

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        m = rng.randint(3, 5)
        n = rng.randint(4, 7)
        samples: list[dict[str, Any]] = []
        family_idx: list[int] = []
        import base64

        for _ in range(m):
            b = _family_sample(rng)
            idx = len(samples)
            samples.append({"id": f"sample-{idx}", "b64": base64.b64encode(b).decode()})
            family_idx.append(idx)
        for j in range(n):
            b = _clean_sample(rng, near_miss=(j == 0))  # first clean is the near-miss hard negative
            samples.append({"id": f"sample-{len(samples)}", "b64": base64.b64encode(b).decode()})
        shuffled: list[dict[str, Any]] = rng.shuffle(samples)
        public = {
            "samples": shuffled,
            "objective": "Write a YARA-subset rule that matches the malware family samples and not the clean ones.",
        }
        # Truth = which samples the family GENERATOR produced (membership), independent of the
        # marker-scan route that independent_verify uses to re-derive and cross-check it.
        fam_ids = sorted(f"sample-{i}" for i in family_idx)
        gold_truth = {"family_ids": fam_ids, "m": len(fam_ids), "n": len(shuffled)}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored byte samples; family samples embed a stable config marker; clean samples do not (one near-miss carries a similar string)",
            independent_derivation="truth = family-generator membership; verify independently re-derives the family set by marker presence in the decoded bytes and must equal it",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "a clean sample contains 'cfg=SynthBackup;v=3;' (similar to the family marker 'cfg=SynthBeacon;v=3;')"
            ],
            adjudication_required=[],
        )
        return finalize(
            self.SUBTASK_ID,
            split,
            seed,
            public,
            gold_truth,
            prov,
            evidence_ids=[str(s["id"]) for s in shuffled],
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        import base64

        rederived = sorted(
            s["id"]
            for s in episode.public_inputs["samples"]
            if _MARKER.encode() in base64.b64decode(s["b64"])
        )
        if rederived == episode.gold_truth["family_ids"]:
            return VerificationResult(
                True, f"marker verifier matched {len(rederived)} family samples", ["family_ids"]
            )
        return VerificationResult(
            False, f"mismatch: gold={episode.gold_truth['family_ids']} derived={rederived}"
        )

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {
            "rule": {
                "name": "SynthBeacon",
                "strings": {"$a": {"kind": "text", "value": _MARKER, "nocase": False}},
                "condition": "$a",
            }
        }

    def grade(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        *,
        agent_id: str,
        evidence_refs: list[str] | None = None,
    ) -> ScoreResult:
        import base64

        samples = episode.public_inputs["samples"]
        blobs = [base64.b64decode(s["b64"]) for s in samples]
        rule = answer.get("rule") or {}
        res = run_yara_subset(rule, blobs)
        if not res.parse_ok:
            return self._result(
                episode,
                answer,
                0.0,
                components=[
                    ItemScore(
                        field="yara",
                        score=0.0,
                        weight=1.0,
                        detail={"parse_ok": False, "error": res.error},
                    )
                ],
                trace=["parse_ok=False"],
            )
        matched_ids = {samples[i]["id"] for i in res.matched}
        fam = set(episode.gold_truth["family_ids"])
        sr = score_set(sorted(matched_ids), sorted(fam), canon=str, beta=1.0)
        return self._result(
            episode,
            answer,
            sr.score,
            components=[ItemScore(field="yara", score=sr.score, weight=1.0, detail=sr.detail())],
            trace=[f"F1={sr.score:.3f}"],
        )
