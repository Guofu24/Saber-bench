"""Persistent project-aware Gemini scheduling with conservative, operator-set quotas.

Every HTTP attempt reserves budget before sending. Quota state survives restarts;
RPM/TPM and rolling 24h caps are local ceilings, not claims about Google entitlements.
Keys never enter the database, logs, prompts or lab observations.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
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
from saber.world.key_layout import TeamKeyLayout
from saber.world.models import Team
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
        key_indices: list[int] | None = None,
        team: Team | None = None,
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
        self.team = team
        self.indices = list(range(len(pool.keys))) if key_indices is None else list(key_indices)
        if not self.indices or any(i < 0 or i >= len(pool.keys) for i in self.indices):
            raise ValueError("Invalid or empty key allocation.")
        if len(set(self.indices)) != len(self.indices):
            raise ValueError("Duplicate key indices in allocation.")
        self._fingerprints = {
            i: hashlib.sha256(pool.keys[i].encode()).hexdigest() for i in self.indices
        }
        if self.team:
            with self.store.transaction():
                saved = self.store.get("key-cursors", self._cursor_name(), {})
                active = next(
                    (i for i in self.indices if self._fingerprints[i] == saved.get("key_hash")),
                    self.indices[0],
                )
                self._pool_state(active, self._availability_state(active))

    @property
    def model_id(self) -> str:
        return self.model

    def _project(self, index: int, key: str) -> str:
        group = self.project_groups.get(str(index))
        identity = f"project:{group}" if group else f"key:{key}"
        return hashlib.sha256(identity.encode()).hexdigest()[:24]

    def _cursor_name(self) -> str:
        return f"{self.team}/{self.model}"

    def _availability_state(self, index: int) -> str:
        q = self.store.get(
            "quota", self._project(index, self.pool.keys[index]) + "/" + self.model, {}
        )
        now = time.time()
        if q.get("disabled"):
            return "disabled"
        if q.get("cool_until", 0) > now:
            return "cooling_down"
        minute = [x for x in q.get("minute", []) if x[0] > now - 60]
        day = [x for x in q.get("day", []) if x > now - 86400]
        if len(minute) >= self.rpm or len(day) >= self.rpd or sum(x[1] for x in minute) >= self.tpm:
            return "at_local_limit"
        return "ready"

    def _pool_state(self, index: int, state: str) -> None:
        if self.team:
            self.store.put(
                "llm-pools",
                self.team,
                {
                    "model": self.model,
                    "first_key": self.indices[0] + 1,
                    "last_key": self.indices[-1] + 1,
                    "keys": len(self.indices),
                    "active_key": index + 1,
                    "state": state,
                },
            )

    def _team_usage(
        self,
        usage: dict[str, Any],
        *,
        attempts: int = 0,
        successes: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        if self.team:
            counters = usage.setdefault("by_team", {}).setdefault(
                self.team, {"attempts": 0, "successes": 0, "input_tokens": 0, "output_tokens": 0}
            )
            for name, value in (
                ("attempts", attempts),
                ("successes", successes),
                ("input_tokens", input_tokens),
                ("output_tokens", output_tokens),
            ):
                counters[name] += value

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
            cursor = self._cursor
            if self.team:
                saved = self.store.get("key-cursors", self._cursor_name(), {})
                cursor = next(
                    (
                        pos
                        for pos, index in enumerate(self.indices)
                        if self._fingerprints[index] == saved.get("key_hash")
                    ),
                    0,
                )
            for offset in range(len(self.indices)):
                position = (cursor + offset) % len(self.indices)
                i = self.indices[position]
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
                self._team_usage(usage, attempts=1)
                self.store.put("meta", "llm_usage", usage)
                chosen = (i, key, project)
                if self.team:
                    self.store.put(
                        "key-cursors", self._cursor_name(), {"key_hash": self._fingerprints[i]}
                    )
                    self._pool_state(i, "in_flight")
                else:
                    self._cursor = (position + 1) % len(self.indices)
                break
            if chosen is None and self.team:
                state = self.store.get("llm-pools", self.team, {})
                state.update({"active_key": None, "state": "waiting_for_quota"})
                self.store.put("llm-pools", self.team, state)
        if chosen is None:
            raise IntegrationBlocked(
                "All configured projects are resting or at their local quota; plans remain queued."
            )
        index, key, project = chosen
        try:
            status, data = self.transport(GEMINI_ENDPOINT.format(model=self.model), key, body)
        except Exception:
            self._rest(project, 60, index=index)
            raise IntegrationBlocked(
                "Gemini transport unavailable; project temporarily resting.", retryable=True
            ) from None
        if status != 200:
            # An authorization failure is permanent for this model; transient failures are not.
            self._rest(
                project, self._retry_seconds(data), disabled=status in (401, 403, 404), index=index
            )
            raise IntegrationBlocked(
                f"Gemini returned HTTP {status}; request deferred.",
                retryable=status in (401, 403, 404, 429, 500, 502, 503, 504),
            )
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
            self._team_usage(usage, successes=1, input_tokens=in_tokens, output_tokens=out_tokens)
            self.store.put("meta", "llm_usage", usage)
            if self.team:
                state = self.store.get("llm-pools", self.team, {})
                q = self.store.get("quota", project, {})
                if (
                    state.get("active_key") == index + 1
                    and not q.get("disabled")
                    and q.get("cool_until", 0) <= time.time()
                ):
                    self._pool_state(index, self._availability_state(index))
        return LLMResponse(
            text=response_text,
            model_id=self.model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
        )

    def _rest(
        self, project: str, seconds: float, *, disabled: bool = False, index: int | None = None
    ) -> None:
        with self.store.transaction():
            q = self.store.get("quota", project, {})
            q.update({"cool_until": time.time() + seconds, "disabled": disabled})
            self.store.put("quota", project, q)
            if self.team and index is not None:
                state = self.store.get("llm-pools", self.team, {})
                if state.get("active_key") == index + 1:
                    self._pool_state(index, "disabled" if disabled else "cooling_down")

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


class TeamQuotaProvider:
    """Route trusted actor teams to disjoint queues; never infer a team from a prompt."""

    def __init__(
        self,
        store: Store,
        layout: TeamKeyLayout,
        *,
        model: str,
        call_budget: int,
        rpm: int = 2,
        rpd: int = 20,
        tpm: int = 100000,
        project_groups: dict[str, str] | None = None,
        transport: Transport | None = None,
        failover_attempts: int = 3,
    ) -> None:
        if not 1 <= failover_attempts <= 10:
            raise ValueError("Failover attempts must be between 1 and 10.")
        self.model = model
        self.failover_attempts = failover_attempts
        self.providers = {
            team: QuotaProvider(
                store,
                layout.pool,
                model=model,
                call_budget=call_budget,
                rpm=rpm,
                rpd=rpd,
                tpm=tpm,
                project_groups=project_groups,
                transport=transport,
                key_indices=indices,
                team=team,
            )
            for team, indices in layout.indices.items()
        }

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
        raise IntegrationBlocked("Team pool requires an explicit trusted actor team.")

    def generate_for(
        self,
        team: Team,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 1024,
        should_stop: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        provider = self.providers.get(team)
        if provider is None:
            raise IntegrationBlocked("Unknown actor team; no API call made.")
        for attempt in range(self.failover_attempts):
            if should_stop and should_stop():
                raise IntegrationBlocked("Planner stopping; no further failover attempts.")
            try:
                return provider.generate(messages, max_tokens=max_tokens)
            except IntegrationBlocked as exc:
                if not exc.context.get("retryable") or attempt + 1 == self.failover_attempts:
                    raise
        raise IntegrationBlocked("Team pool could not serve this request.")
