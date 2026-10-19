"""Deterministic grading library (B003). Evaluator-only; never imported by agent code paths.

Every primitive returns an explicit trace so a score can be audited without re-running.
Conventions are documented in docs/adr/0001-scorer-conventions.md.
"""

from saber.grading.results import GateOutcome, ItemScore, ScoreResult, Validity

SCORER_VERSION = "score_v1"

__all__ = ["SCORER_VERSION", "GateOutcome", "ItemScore", "ScoreResult", "Validity"]
