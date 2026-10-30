"""Baselines B0-B4 over the SABER protocol.

Only B0 (deterministic SIEM-style rules) and the evaluator ORACLE run offline. B1-B4 are
LLM-backed and BLOCKED_INTEGRATION here (subscription-only, no API budget). Each baseline exposes
the same solve signature so graders see identical output contracts (protocol fairness: G4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from saber.agents.provider import LLMProvider
from saber.domain.errors import IntegrationBlocked
from saber.episodes.builder import BuiltEpisode
from saber.episodes.runner import EpisodeResult, run_oracle, run_reference, run_stub


class BaselineId(StrEnum):
    B0_RULES = "B0"
    B1_SINGLE_AGENT = "B1"
    B2_SPECIALISTS = "B2"
    B3_SPECIALISTS_SHARED = "B3"
    B4_WITH_CONTENT = "B4"
    ORACLE = "ORACLE"


@dataclass(frozen=True)
class Baseline:
    id: BaselineId
    label: str
    offline: bool
    description: str


BASELINES: dict[BaselineId, Baseline] = {
    BaselineId.B0_RULES: Baseline(
        BaselineId.B0_RULES, "Deterministic rules", True, "rules-only reference solver; no LLM cost"
    ),
    BaselineId.B1_SINGLE_AGENT: Baseline(
        BaselineId.B1_SINGLE_AGENT,
        "Single general agent",
        False,
        "one general LLM agent; BLOCKED_INTEGRATION (no provider budget)",
    ),
    BaselineId.B2_SPECIALISTS: Baseline(
        BaselineId.B2_SPECIALISTS,
        "Specialists, no sharing",
        False,
        "four specialists, no shared case state; BLOCKED_INTEGRATION",
    ),
    BaselineId.B3_SPECIALISTS_SHARED: Baseline(
        BaselineId.B3_SPECIALISTS_SHARED,
        "Specialists + shared state",
        False,
        "coordinated specialists; BLOCKED_INTEGRATION",
    ),
    BaselineId.B4_WITH_CONTENT: Baseline(
        BaselineId.B4_WITH_CONTENT,
        "B3 + content feedback",
        False,
        "coordination + content loop; BLOCKED_INTEGRATION",
    ),
    BaselineId.ORACLE: Baseline(
        BaselineId.ORACLE,
        "Evaluator oracle",
        True,
        "upper bound: solves from sealed truth (evaluator-side sanity, not a competitor)",
    ),
}


# LLM baselines a supplied provider can drive here, and whether they load the service skill.
# B1 is a generic single agent; B2 is the service specialist (loads .claude/skills). B3 (shared
# case state across specialists) and B4 (content feedback loop) need cross-episode orchestration
# that is not wired yet, so they stay BLOCKED even when a provider is supplied.
_PROVIDER_DRIVEN: dict[BaselineId, bool] = {
    BaselineId.B1_SINGLE_AGENT: False,  # value = use_skill
    BaselineId.B2_SPECIALISTS: True,
}


def solve_episode(
    baseline: BaselineId,
    episode: BuiltEpisode,
    *,
    graded_at: datetime | None = None,
    provider: LLMProvider | None = None,
) -> EpisodeResult:
    """Run one baseline on one episode.

    B0/ORACLE run offline. B1/B2 run only when an operator-approved ``provider`` is supplied (the
    default ``None`` keeps them BLOCKED_INTEGRATION). B3/B4 are always BLOCKED here.
    """
    if baseline is BaselineId.ORACLE:
        return run_oracle(episode, graded_at=graded_at)
    if baseline is BaselineId.B0_RULES:
        result = run_reference(episode, graded_at=graded_at)
        if result is None:
            # No rules oracle for this subtask: B0 abstains (empty answer), graded honestly.
            return run_stub(episode, {}, [], graded_at=graded_at)
        return result
    if provider is not None and baseline in _PROVIDER_DRIVEN:
        from saber.agents.llm_solver import solve_episode_with_llm

        run = solve_episode_with_llm(
            episode, provider, use_skill=_PROVIDER_DRIVEN[baseline], graded_at=graded_at
        )
        return run.result
    raise IntegrationBlocked(
        f"baseline {baseline.value} is LLM-backed and BLOCKED_INTEGRATION: subscription-only, no "
        "API budget; supply an operator-approved provider "
        + ("and note B3/B4 coordination is not wired yet" if baseline not in _PROVIDER_DRIVEN else "to run it"),
        baseline=baseline.value,
    )
