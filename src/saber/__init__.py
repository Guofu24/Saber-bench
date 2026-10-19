"""SABER — SOC Agent Benchmark for Evaluation and Reproducibility.

Offline-first implementation of the 175-subtask NICE-derived SOC benchmark.
Nothing in this package executes live attacks, touches production systems or
reads evaluator truth from a Blue-agent code path.
"""

from __future__ import annotations

__version__ = "0.1.0"
PACKAGE_NAME = "saber-bench"
CATALOG_SUBTASK_COUNT = 175
CATALOG_NICE_TASK_COUNT = 55
CATALOG_ARTIFACT_TYPE_COUNT = 40

__all__ = [
    "CATALOG_ARTIFACT_TYPE_COUNT",
    "CATALOG_NICE_TASK_COUNT",
    "CATALOG_SUBTASK_COUNT",
    "PACKAGE_NAME",
    "__version__",
]
