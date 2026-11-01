"""Persistent project-aware Gemini scheduling with conservative, operator-set quotas.

Every HTTP attempt reserves budget before sending. Quota state survives restarts;
RPM/TPM and rolling 24h caps are local ceilings, not claims about Google entitlements.
Keys never enter the database, logs, prompts or lab observations.
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any

from saber.agents.gemini import (
    GEMINI_ENDPOINT,
    KeyPool,
    Transport,
    _to_gemini_contents,
    _urllib_transport,
)
from saber.agents.provider import LLMResponse
from saber.domain.errors import BudgetExceeded, IntegrationBlocked
from saber.world.store import Store


class QuotaProvider:
    def __init__(
        self,
        store: Store,
        pool: KeyPool,
        *,
        model: str,
        call_budget: int,
        rpm: int = 2,
        rpd: int = 20,
        tpm: int = 100000,
        project_groups: dict[str, str] | None = None,
        transport: Transport | None = None,
    ) -> None:
        if call_budget <= 0 or min(rpm, rpd, tpm) <= 0:
            raise ValueError("Call budget and project limits must be positive.")
        if not pool.keys:
            raise ValueError("Empty key pool.")
        self.store, self.pool, self.model = store, pool, model
        self.call_budget, self.rpm, self.rpd, self.tpm = call_budget, rpm, rpd, tpm
        self.transport = transport or _urllib_transport
        self.project_groups = project_groups or {}
        if any(not k.isdigit() or int(k) >= len(pool.keys) for k in self.project_groups):
            raise ValueError("Project map contains an invalid deduplicated key index.")
        self._cursor = 0

    @property
    def model_id(self) -> str:
        return self.model

    def _project(self, index: int, key: str) -> str:
        group = self.project_groups.get(str(index))
        identity = f"project:{group}" if group else f"key:{key}"
        return hashlib.sha256(identity.encode()).hexdigest()[:24]

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        contents, system = _to_gemini_contents(messages)
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        # Conservative local token reservation, including output; settle actual usage separately.
        estimate = sum(len(str(m.get("content", ""))) for m in messages) + max_tokens
        if estimate > self.tpm:
            raise IntegrationBlocked(
                "Prompt exceeds configured per-project TPM ceiling; reduce context or adjust the local cap."
            )
        chosen: tuple[int, str, str] | None = None
        now = time.time()
        with self.store.transaction():
            usage = self.store.get(
                "meta",
                "llm_usage",
                {"attempts": 0, "successes": 0, "input_tokens": 0, "output_tokens": 0},
            )
            if usage["attempts"] >= self.call_budget:
                raise BudgetExceeded("Persistent LLM attempt budget exhausted.")
            for offset in range(len(self.pool.keys)):
                i = (self._cursor + offset) % len(self.pool.keys)
                key = self.pool.keys[i]
                project = self._project(i, key) + "/" + self.model
                q = self.store.get("quota", project, {})
                if q.get("disabled") or q.get("cool_until", 0) > now:
                    continue
                minute = [x for x in q.get("minute", []) if x[0] > now - 60]
                day = [x for x in q.get("day", []) if x > now - 86400]
                if (
                    len(minute) >= self.rpm
                    or len(day) >= self.rpd
                    or sum(x[1] for x in minute) + estimate > self.tpm
                ):
                    continue
                q.update({"minute": minute + [[now, estimate]], "day": day + [now]})
                self.store.put("quota", project, q)
                usage["attempts"] += 1
                self.store.put("meta", "llm_usage", usage)
                chosen = (i, key, project)
                self._cursor = (i + 1) % len(self.pool.keys)
                break
        if chosen is None:
            raise IntegrationBlocked(
                "All configured projects are resting or at their local quota; plans remain queued."
            )
        _, key, project = chosen
        try:
            status, data = self.transport(GEMINI_ENDPOINT.format(model=self.model), key, body)
        except Exception:
            self._rest(project, 60)
            raise IntegrationBlocked(
                "Gemini transport unavailable; project temporarily resting."
            ) from None
        if status != 200:
            # An authorization failure is permanent for this model; transient failures are not.
            self._rest(project, self._retry_seconds(data), disabled=status in (401, 403, 404))
            raise IntegrationBlocked(f"Gemini returned HTTP {status}; request deferred.")
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
        response_text = "".join(str(p.get("text", "")) for p in parts if not p.get("thought"))
        usage_data = data.get("usageMetadata") or {}
        in_tokens = max(0, int(usage_data.get("promptTokenCount", 0)))
        out_tokens = max(0, int(usage_data.get("candidatesTokenCount", 0)))
        with self.store.transaction():
            usage = self.store.get("meta", "llm_usage")
            usage["successes"] += 1
            usage["input_tokens"] += in_tokens
            usage["output_tokens"] += out_tokens
            self.store.put("meta", "llm_usage", usage)
        return LLMResponse(
            text=response_text,
            model_id=self.model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
        )

    def _rest(self, project: str, seconds: float, *, disabled: bool = False) -> None:
        with self.store.transaction():
            q = self.store.get("quota", project, {})
            q.update({"cool_until": time.time() + seconds, "disabled": disabled})
            self.store.put("quota", project, q)

    @staticmethod
    def _retry_seconds(data: dict[str, Any]) -> float:
        err = data.get("error", {})
        if isinstance(err, dict):
            for detail in err.get("details", []):
                if isinstance(detail, dict) and "retryDelay" in detail:
                    try:
                        value = float(str(detail["retryDelay"]).removesuffix("s"))
                        if math.isfinite(value):
                            return max(60.0, min(value, 86400.0))
                    except ValueError:
                        pass
        return 60.0
