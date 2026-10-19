"""T0173.001 (IR, file) — reorder events recorded across three time zones.

Source scenario: given 30 events recorded in three different time zones, reorder them by true
(absolute) time. Source scorer: `event_order[]` (order) with aggregate `Kendall tau`.

Each event shows a local timestamp plus its UTC offset; the solver must order by the resulting
UTC instant. The sealed truth is the correct UTC ordering of opaque event ids.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
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
from saber.subtasks._hv.common import BASE_TIME, Rng

_OFFSETS = ("+07:00", "+00:00", "-05:00")
_ACTIONS = (
    "user login", "file created", "service started", "config changed", "process spawned",
    "network connection", "scheduled task registered", "account modified", "log cleared flag", "archive created",
)  # fmt: skip


def _fmt_local(instant: datetime, offset_str: str) -> str:
    sign = 1 if offset_str[0] == "+" else -1
    hh, mm = int(offset_str[1:3]), int(offset_str[4:6])
    local = instant + sign * timedelta(hours=hh, minutes=mm)
    return local.strftime("%Y-%m-%dT%H:%M:%S") + offset_str


class EventOrderOutput(StrictModel):
    event_order: list[str] = Field(min_length=1)


class Subtask(SubtaskBase):
    SUBTASK_ID = "T0173.001"
    OutputModel = EventOrderOutput
    VARIANTS = ("default",)

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        n = 30
        instants = rng.times_sorted(n, base=BASE_TIME, span_minutes=1440)
        order_truth = [f"evt-{i:02d}" for i in range(n)]  # already sorted by true UTC time
        events: list[dict[str, Any]] = []
        for i, instant in enumerate(instants):
            offset = rng.pick(_OFFSETS)
            events.append(
                {
                    "event_id": f"evt-{i:02d}",
                    "host": rng.hostname(),
                    "action": rng.pick(_ACTIONS),
                    "local_time": _fmt_local(instant, offset),
                    "tz_offset": offset,
                }
            )
        shuffled = rng.shuffle(events)
        log = {
            "hv": "HV-02",
            "note": "timestamps are local; tz_offset gives the UTC offset",
            "events": shuffled,
        }
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={"log": log},
            sealed_truth={"event_order": order_truth},
            evidence_ids=order_truth,
            notes="Correct order is ascending UTC instant; events presented shuffled.",
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        return {"event_order": list(truth["event_order"])}

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        comp = self.order_item(
            "event_order", answer.event_order, truth["event_order"], mode="tau", subtype="text"
        )
        return ScoreParts(
            components=[comp],
            raw_score=comp.score,
            trace=[f"event_order Kendall tau -> {comp.score:.4f} ({comp.detail})"],
        )

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:

        events = public_inputs["log"]["events"]
        ordered = sorted(events, key=lambda e: datetime.fromisoformat(e["local_time"]))
        return {"event_order": [e["event_id"] for e in ordered]}, []

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        truth = bundle.sealed_truth["event_order"]
        return [
            GoldenCase("reversed", {"event_order": list(reversed(truth))}, expected_score=0.0),
            GoldenCase(
                "one_swap", {"event_order": _swap(truth)}, expected_min=0.9, expected_max=0.999
            ),
        ]


def _swap(order: list[str]) -> list[str]:
    out = list(order)
    if len(out) >= 2:
        out[0], out[1] = out[1], out[0]
    return out
