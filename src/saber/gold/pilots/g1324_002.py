"""Gold pilot T1324.002 (IR, file) — order evidence by volatility and state how to preserve each.

Artifact: a list of evidence types present in an incident. The solver returns the collection order
(most volatile first) AND a preservation method per type. Ground truth order is the canonical order
of volatility (RFC 3227): RAM → network connections → processes → disk → logs → archived; the
preservation method per type comes from a documented table. Scored Σ wᵢ·sᵢ: order (tau*recall, 0.6)
+ preservation method accuracy (0.4). Method conventions are queued for adjudication.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.grading.primitives import accuracy, score_order
from saber.grading.results import ItemScore, ScoreResult
from saber.subtasks._hv.common import Rng

# Canonical order of volatility (most volatile first) and a documented preservation method per type.
_VOLATILITY = [
    "ram",
    "network_connections",
    "processes",
    "disk_images",
    "local_logs",
    "archived_logs",
]
# type -> canonical preservation-method TOKEN (a closed vocabulary). The solver must MAP each
# evidence type to its method itself; the type->method mapping is NOT given in public_inputs
# (only the vocabulary is), so the preservation component is not free to copy.
_METHOD = {
    "ram": "live_memory_acquisition",
    "network_connections": "snapshot_connections",
    "processes": "capture_process_state",
    "disk_images": "forensic_disk_image",
    "local_logs": "copy_preserve_timestamps",
    "archived_logs": "export_from_central_store",
}
_METHOD_VOCAB = sorted(set(_METHOD.values()))


class Pilot(GoldPilot):
    SUBTASK_ID = "T1324.002"
    SOURCE_VERSIONS = {"order_standard": "RFC3227-order-of-volatility"}
    OUTPUT_SPEC = 'JSON {"collection_order": ["<type>", ... most volatile first], "preservation": {"<type>": "<method token from the provided vocabulary>", ...}}'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        present = rng.sample(_VOLATILITY, rng.randint(5, 6))
        order_truth = [
            t for t in _VOLATILITY if t in present
        ]  # canonical order restricted to present
        preservation = {t: _METHOD[t] for t in present}
        public = {
            "evidence_types": rng.shuffle(list(present)),
            "objective": "Order the evidence by volatility (most volatile first) and map each type to its preservation method token.",
            # Only the allowed method TOKENS are given (an enum), not the type->method mapping.
            "method_vocabulary": _METHOD_VOCAB,
        }
        gold_truth = {"collection_order": order_truth, "preservation": preservation}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored evidence-type set; order = RFC 3227 volatility; preservation = type->method-token mapping (vocabulary given, mapping withheld)",
            independent_derivation="order re-derived independently by sorting present types on the canonical volatility index; preservation mapping is a documented convention checked against the method table and queued for adjudication",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=["order is shuffled in the input so a positional copy fails"],
            adjudication_required=[
                "the type->preservation-method mapping should be confirmed with an IR lead; it is a documented default, and the exact method vocabulary is a convention"
            ],
        )
        return finalize(
            self.SUBTASK_ID, split, seed, public, gold_truth, prov, evidence_ids=list(present)
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        present = set(episode.public_inputs["evidence_types"])
        order = [t for t in _VOLATILITY if t in present]
        preservation = {t: _METHOD[t] for t in present}
        if (
            order == episode.gold_truth["collection_order"]
            and preservation == episode.gold_truth["preservation"]
        ):
            return VerificationResult(
                True,
                f"volatility order + catalog matched {len(present)} types",
                ["collection_order", "preservation"],
            )
        return VerificationResult(False, "re-derived order/preservation disagree with gold")

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {
            "collection_order": list(episode.gold_truth["collection_order"]),
            "preservation": dict(episode.gold_truth["preservation"]),
        }

    def grade(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        *,
        agent_id: str,
        evidence_refs: list[str] | None = None,
    ) -> ScoreResult:
        gt = episode.gold_truth
        order_res = score_order(
            answer.get("collection_order") or [],
            gt["collection_order"],
            canon=str,
            mode="tau*recall",
        )
        raw_pres = answer.get("preservation")
        pred_pres = raw_pres if isinstance(raw_pres, dict) else {}
        pres_score, pres_detail = accuracy(
            [(pred_pres.get(k), v) for k, v in gt["preservation"].items()]
        )
        score = 0.6 * order_res.score + 0.4 * pres_score
        comps = [
            ItemScore(
                field="collection_order",
                score=order_res.score,
                weight=0.6,
                detail=order_res.detail(),
            ),
            ItemScore(field="preservation", score=pres_score, weight=0.4, detail=pres_detail),
        ]
        return self._result(
            episode,
            answer,
            score,
            components=comps,
            trace=[f"order={order_res.score:.3f}", f"preservation={pres_score:.3f}"],
        )
