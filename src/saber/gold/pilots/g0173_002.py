"""Gold pilot T0173.002 (IR, file) — normalise event timestamps to UTC and order them.

Artifact: events each with a local timestamp and an explicit UTC offset (three time zones). The
solver returns the UTC-ordered event ids AND the normalised UTC timestamp of each. Ground truth is
independently derived by converting each local time + offset to UTC (a documented computation) and
sorting — distinct from merely reading an index. Scored Σ wᵢ·sᵢ: order (tau*recall, 0.6) + utc
timestamps within ±5 min (0.4). Hard negative: two events in different zones whose LOCAL times look
ordered one way but whose true UTC order is the reverse.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.grading.primitives import score_numeric, score_order
from saber.grading.results import ItemScore, ScoreResult
from saber.subtasks._hv.common import BASE_TIME, Rng

_OFFSETS = ("+07:00", "+00:00", "-05:00")


def _to_utc(local_iso: str) -> datetime:
    dt = datetime.fromisoformat(local_iso)
    off = dt.utcoffset()
    return (dt - off).replace(tzinfo=None) if off is not None else dt.replace(tzinfo=None)


def _fmt_local(instant: datetime, offset: str) -> str:
    sign = 1 if offset[0] == "+" else -1
    hh, mm = int(offset[1:3]), int(offset[4:6])
    return (instant + sign * timedelta(hours=hh, minutes=mm)).strftime("%Y-%m-%dT%H:%M:%S") + offset


class Pilot(GoldPilot):
    SUBTASK_ID = "T0173.002"
    SOURCE_VERSIONS = {"artifact": "multi-tz-event-log"}
    OUTPUT_SPEC = 'JSON {"event_order": ["<id>", ... in true UTC time order], "utc_times": ["<YYYY-MM-DDTHH:MM:SSZ>", ... aligned to event_order]}'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        n = rng.randint(8, 12)
        instants = sorted(
            {rng.time(base=BASE_TIME, min_minutes=0, max_minutes=1440) for _ in range(n)}
        )
        n = len(instants)
        ids = [f"evt-{i:02d}" for i in range(n)]
        events = []
        utc_by_id = {}
        for e, inst in zip(ids, instants, strict=True):
            off = rng.pick(_OFFSETS)
            local = _fmt_local(inst, off)
            events.append(
                {
                    "id": e,
                    "local_time": local,
                    "tz_offset": off,
                    "action": rng.pick(("login", "file write", "service start", "net conn")),
                }
            )
            utc_by_id[e] = inst
        shuffled = rng.shuffle([dict(x) for x in events])
        order_truth = [e for e, _ in sorted(utc_by_id.items(), key=lambda kv: kv[1])]
        utc_truth = [utc_by_id[e].strftime("%Y-%m-%dT%H:%M:%SZ") for e in order_truth]
        public = {
            "log": {
                "hv": "HV-02",
                "events": shuffled,
                "note": "timestamps are local; tz_offset gives the UTC offset",
            },
            "objective": "Normalise every timestamp to UTC and order the events by true UTC time.",
        }
        gold_truth = {"event_order": order_truth, "utc_times": utc_truth}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored multi-timezone event log; UTC order computed from local+offset",
            independent_derivation="verifier recomputes UTC = local - offset and re-sorts; must equal the gold order and times",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "cross-zone pairs whose local order is the reverse of their true UTC order"
            ],
            adjudication_required=[],
        )
        return finalize(
            self.SUBTASK_ID, split, seed, public, gold_truth, prov, evidence_ids=list(ids)
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        events = episode.public_inputs["log"]["events"]
        utc = {e["id"]: _to_utc(e["local_time"]) for e in events}
        order = [e for e, _ in sorted(utc.items(), key=lambda kv: kv[1])]
        times = [utc[e].strftime("%Y-%m-%dT%H:%M:%SZ") for e in order]
        if order == episode.gold_truth["event_order"] and times == episode.gold_truth["utc_times"]:
            return VerificationResult(
                True,
                f"UTC recomputation matched order+times for {len(order)} events",
                ["event_order", "utc_times"],
            )
        return VerificationResult(False, "recomputed UTC order/times disagree with gold")

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {
            "event_order": list(episode.gold_truth["event_order"]),
            "utc_times": list(episode.gold_truth["utc_times"]),
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
            answer.get("event_order") or [], gt["event_order"], canon=str, mode="tau*recall"
        )
        # Per-event UTC within +/- 5 minutes, aligned to the submitted order.
        pred_order = answer.get("event_order") or []
        pred_times = answer.get("utc_times") or []
        truth_time = dict(zip(gt["event_order"], gt["utc_times"], strict=True))
        hits = 0
        for i, eid in enumerate(pred_order):
            if (
                eid in truth_time
                and i < len(pred_times)
                and score_numeric(pred_times[i], truth_time[eid], "±5′")[0] == 1.0
            ):
                hits += 1
        time_score = hits / len(gt["event_order"]) if gt["event_order"] else 0.0
        score = 0.6 * order_res.score + 0.4 * time_score
        comps = [
            ItemScore(
                field="event_order", score=order_res.score, weight=0.6, detail=order_res.detail()
            ),
            ItemScore(
                field="utc_times", score=time_score, weight=0.4, detail={"within_5min": hits}
            ),
        ]
        return self._result(
            episode,
            answer,
            score,
            components=comps,
            trace=[f"order={order_res.score:.3f}", f"utc={time_score:.3f}"],
        )
