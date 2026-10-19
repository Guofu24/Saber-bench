"""Gold pilot T1387.002 (MON, file) — validate an IDS alert and locate the matching byte range.

Artifact: an IDS alert (with its signature content pattern) plus the session payload bytes of that
very session. The solver returns the verdict (TP/FP) and the byte interval [start,end) in the
payload where the signature actually matches. Ground truth is independently derived by searching
the payload for the signature's literal content — a route distinct from the solver — and TP/FP from
whether that content is genuinely present. Scored Σ wᵢ·sᵢ (verdict 0.6, payload_offset IoU≥0.8 0.4)
via the engine scorer. Hard negative: an FP alert whose signature text is absent from the payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.grading.primitives import score_enum, score_numeric
from saber.grading.results import ItemScore, ScoreResult
from saber.subtasks._hv.common import Rng

# (signature id, literal content the signature matches)
_SIGS = (
    ("ET WEB_SPECIFIC cmd.exe in URI", "cmd.exe"),
    ("ET MALWARE user-agent Synth", "User-Agent: SynthBot/1.0"),
    ("ET EXPLOIT /etc/passwd traversal", "../../../../etc/passwd"),
    ("ET SCAN sqlmap user-agent", "sqlmap/1.7"),
)
_FILLER = "GET /index.html HTTP/1.1\r\nHost: shop.example\r\nAccept: text/html\r\n"


class Pilot(GoldPilot):
    SUBTASK_ID = "T1387.002"
    SOURCE_VERSIONS = {"ids": "suricata-style-subset", "evidence": "session-payload"}
    OUTPUT_SPEC = 'JSON {"verdict": "TP"|"FP", "payload_offset": {"start": <int>, "end": <int>}} where offset is the byte range in the payload that matches the signature (start=end=0 if no match)'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        sig_id, content = rng.pick(_SIGS)
        is_tp = rng.chance(0.6)
        prefix = _FILLER + "X" * rng.randint(20, 80)
        if is_tp:
            payload = prefix + content + "\r\n" + ("Y" * rng.randint(10, 40))
            start = payload.index(content)
            offset = {"start": start, "end": start + len(content)}
            verdict = "TP"
        else:
            # Hard negative: the signature content is NOT present; alert is a false positive.
            payload = prefix + "Connection: keep-alive\r\n" + ("Y" * rng.randint(10, 40))
            offset = {"start": 0, "end": 0}
            verdict = "FP"
        public = {
            "alert": {"hv": "HV-21", "signature_id": sig_id, "matches_content": content},
            "payload": {"hv": "HV-24", "bytes_ascii": payload, "length": len(payload)},
            "objective": "Decide TP/FP and give the byte interval in the payload matching the signature (0,0 if absent).",
        }
        gold_truth = {"verdict": verdict, "payload_offset": offset}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored IDS alert + session payload; TP embeds the signature content, FP omits it",
            independent_derivation="verifier searches the payload for the signature's literal content (str.index); TP iff present and the interval equals the found span",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=["FP alert whose signature content is absent from the payload"],
            adjudication_required=[],
        )
        return finalize(
            self.SUBTASK_ID, split, seed, public, gold_truth, prov, evidence_ids=[sig_id]
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        content = episode.public_inputs["alert"]["matches_content"]
        payload = episode.public_inputs["payload"]["bytes_ascii"]
        idx = payload.find(content)
        if idx >= 0:
            derived = {"verdict": "TP", "payload_offset": {"start": idx, "end": idx + len(content)}}
        else:
            derived = {"verdict": "FP", "payload_offset": {"start": 0, "end": 0}}
        if derived == episode.gold_truth:
            return VerificationResult(
                True,
                f"payload search verified verdict={derived['verdict']}",
                ["verdict", "payload_offset"],
            )
        return VerificationResult(False, f"derived {derived} != gold {episode.gold_truth}")

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return dict(episode.gold_truth)

    def grade(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        *,
        agent_id: str,
        evidence_refs: list[str] | None = None,
    ) -> ScoreResult:
        # Faithful source formula Σ wᵢ·sᵢ: verdict (TP/FP exact, 0.6) + payload_offset (IoU≥0.8, 0.4).
        # The engine's generic enum domain rejects TP/FP, so this pilot scores verdict directly.
        gt = episode.gold_truth
        vs, vd = score_enum(answer.get("verdict"), gt["verdict"], valid_labels=["TP", "FP"])
        os_, od = score_numeric(answer.get("payload_offset"), gt["payload_offset"], "IoU≥0.8")
        comps = [
            ItemScore(field="verdict", score=vs, weight=0.6, detail=vd),
            ItemScore(field="payload_offset", score=os_, weight=0.4, detail=od),
        ]
        score = 0.6 * vs + 0.4 * os_
        return self._result(
            episode,
            answer,
            score,
            components=comps,
            trace=[f"verdict={vs}", f"payload_offset={os_}"],
        )
