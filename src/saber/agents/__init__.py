"""Agent/provider layer: provider port + deterministic stub, specialist router, baselines.

Honesty note: the offline benchmark runs **no LLM**. The deterministic `StubProvider` exercises
the agent loop in CI; the real provider adapter is gated behind an operator-supplied key and is
not called here (the project is subscription-only with no API budget), so LLM-backed baselines
(B1-B4) are BLOCKED_INTEGRATION. Only the rules-only baseline (B0) and the evaluator oracle run
offline. Nothing here claims model quality.
"""

from saber.agents.baselines import BASELINES, Baseline, BaselineId, solve_episode
from saber.agents.provider import (
    BlockedAnthropicProvider,
    LLMProvider,
    LLMResponse,
    StubProvider,
)
from saber.agents.router import SpecialistRouter

__all__ = [
    "BASELINES",
    "Baseline",
    "BaselineId",
    "BlockedAnthropicProvider",
    "LLMProvider",
    "LLMResponse",
    "SpecialistRouter",
    "StubProvider",
    "solve_episode",
]
