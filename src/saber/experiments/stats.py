"""Small deterministic statistics: mean and a seeded bootstrap CI over groups.

Bootstrap resamples the *unit of grouping* (here, subtasks) rather than correlated episodes, per
docs/BENCHMARK_PROTOCOL.md. A fixed seed makes the interval reproducible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    mean: float
    low: float
    high: float
    n: int


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def bootstrap_ci(
    values: list[float], *, seed: int = 12345, resamples: int = 2000, alpha: float = 0.05
) -> Interval:
    if not values:
        return Interval(0.0, 0.0, 0.0, 0)
    if len(values) == 1:
        return Interval(values[0], values[0], values[0], 1)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * resamples)]
    hi = means[min(resamples - 1, int((1 - alpha / 2) * resamples))]
    return Interval(mean=mean(values), low=lo, high=hi, n=n)
