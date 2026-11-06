"""Private mission outcome: protected client work weighed against detection.

Follows the CAGE Challenge 4 idea that a defender is judged by the legitimate
work it keeps running, not only by alerts. Inputs are evaluator counters that
never reach agents. The weights are a provisional DEV choice, not a benchmark score.
"""

from __future__ import annotations

import math
from typing import Any

WEIGHTS = {"work_availability": 0.5, "detection_quality": 0.5}


def wilson(successes: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval; stays inside [0, 1] for small samples."""
    if n <= 0:
        return None
    p = successes / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    scale = 1 + z * z / n
    return [
        round(max(0.0, (centre - margin) / scale), 4),
        round(min(1.0, (centre + margin) / scale), 4),
    ]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def mission_outcome(metrics: dict[str, Any]) -> dict[str, Any]:
    requests = int(metrics.get("client_requests", 0))
    outage = int(metrics.get("client_denied_outage", 0))
    contained = int(metrics.get("client_denied_containment", 0))
    collateral = int(metrics.get("client_denied_collateral", 0))
    # A justified containment of an offending client is a cost a correct defender
    # would also impose; only red outages and blue collateral count as avoidable loss.
    lost = outage + collateral
    availability = _ratio(requests - lost, requests)
    recall = _ratio(
        int(metrics.get("detected_incidents", 0)), int(metrics.get("verified_incidents", 0))
    )
    precision = _ratio(int(metrics.get("case_tp", 0)), int(metrics.get("cases", 0)))
    false_rate = _ratio(
        int(metrics.get("false_containments", 0)), int(metrics.get("containments", 0))
    )
    if recall is None:
        quality = None  # nothing to detect; only protected work is scored
    elif not recall or not precision:
        quality = 0.0
    else:
        quality = 2 * recall * precision / (recall + precision)
    if availability is None:
        score = None
    elif quality is None:
        score = availability
    else:
        score = WEIGHTS["work_availability"] * availability + WEIGHTS["detection_quality"] * quality
    return {
        "labels": ["DEV_SIMULATION_ONLY", "PROVISIONAL_WEIGHTS"],
        "client_requests": requests,
        "client_denied_outage": outage,
        "client_denied_containment": contained,
        "client_denied_collateral": collateral,
        "work_availability": _round(availability),
        "work_availability_ci95": wilson(requests - lost, requests),
        "incident_recall": _round(recall),
        "case_precision": _round(precision),
        "detection_quality": _round(quality),
        "false_containment_rate": _round(false_rate),
        "mission_score": _round(score),
        "weights": WEIGHTS,
        "formula": "work_availability alone without incidents; otherwise "
        "0.5*work_availability + 0.5*F1(incident_recall, case_precision)",
        "note": "Avoidable loss = client requests denied by outage or by containing a "
        "non-offender. Evaluator-only; not shown to agents and not a benchmark score.",
    }
