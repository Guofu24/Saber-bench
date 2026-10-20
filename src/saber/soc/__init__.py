"""Phase G2 — end-to-end four-service SOC case workflow over live lab evidence.

Monitoring, Threat Hunting, Incident Response and Content Security operate on a genuinely executed
:class:`~saber.range.live.episode.LiveEpisode`, communicating through a structured :class:`Case`
with cited evidence references and audited tool calls. No service reads the sealed control-plane
truth or evaluator internals.

Honest contract binding: Monitoring (list exploit lines) and Content Security (author + held-out
test a detection rule) are SCORED against real set_delta source contracts (T1347.001, T0020.001).
Threat Hunting (timeline + affected entities) and Incident Response (verified reversible lab action)
are genuine workflow artifacts with measured outcomes, NOT claimed as source-contract coverage.
"""

from __future__ import annotations

from saber.soc.evaluation import run_g3_evaluation, write_g3_evaluation
from saber.soc.suite import run_soc_suite, write_soc_suite
from saber.soc.workflow import Case, run_case_workflow

__all__ = [
    "Case",
    "run_case_workflow",
    "run_g3_evaluation",
    "run_soc_suite",
    "write_g3_evaluation",
    "write_soc_suite",
]
