"""LLM provider port, a deterministic stub, and a fail-closed real-provider adapter."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from saber.domain.errors import IntegrationBlocked


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    tool_calls: int = 0
    stop_reason: str = "end_turn"


@runtime_checkable
class LLMProvider(Protocol):
    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...

    @property
    def model_id(self) -> str: ...


@dataclass
class StubProvider:
    """Deterministic, offline. Echoes a stable hash of the prompt; usage is counted, not billed.

    It performs no reasoning; callers that need an answer use the subtask's rules-only reference.
    The stub exists so the agent/orchestration loop is exercised reproducibly in CI.
    """

    model: str = "stub-deterministic-1"
    calls: int = 0

    @property
    def model_id(self) -> str:
        return self.model

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        self.calls += 1
        blob = json.dumps(messages, sort_keys=True, default=str)
        digest = hashlib.sha256(blob.encode()).hexdigest()
        in_tokens = max(1, len(blob) // 4)
        return LLMResponse(
            text=f"stub:{digest[:16]}",
            model_id=self.model,
            input_tokens=in_tokens,
            output_tokens=8,
            tool_calls=0,
        )


@dataclass
class BlockedAnthropicProvider:
    """Real provider adapter. Fails closed: subscription-only, no API budget authorised here."""

    model: str = "claude-not-configured"
    _key_env: str = field(default="ANTHROPIC_API_KEY")

    @property
    def model_id(self) -> str:
        return self.model

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        raise IntegrationBlocked(
            "LLM provider is BLOCKED_INTEGRATION: the benchmark is subscription-only with no API "
            "budget. Running LLM-backed baselines (B1-B4) requires an operator-approved provider "
            f"key in ${self._key_env} and an explicit budget decision; the agent never enables it.",
            configured=bool(os.environ.get(self._key_env)),
        )
