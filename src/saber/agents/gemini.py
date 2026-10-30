"""Google Gemini provider adapter with key-pool rotation and a hard budget gate.

FAIL-CLOSED, like :class:`saber.agents.provider.BlockedAnthropicProvider`. The project is
subscription-only with no API budget (see ``run.sh`` and ``CLAUDE.md``). A real, billable call
to Gemini happens ONLY when the operator makes two explicit decisions:

* opts in:   ``SABER_ENABLE_PAID_LLM=1``
* sets a cap: ``SABER_GEMINI_BUDGET_CALLS=<n>`` with ``n > 0``

With either missing, :meth:`GeminiProvider.generate` raises ``IntegrationBlocked`` before any
network I/O. The agent never flips these on by itself.

Keys are loaded from a *gitignored* pool file (default ``keys_pool.txt``, override with
``SABER_GEMINI_KEY_POOL``). Key material is never logged, never put in exceptions, and never
placed in a URL -- it travels only in the ``x-goog-api-key`` request header. Errors and ``repr``
reference keys by pool index only.

The HTTP transport is injectable so the whole adapter is exercised offline in CI with a fake
transport: no network, no spend. The default transport uses ``urllib`` from the stdlib (no new
dependency).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from saber.agents.provider import LLMResponse
from saber.domain.errors import BudgetExceeded, IntegrationBlocked

# (status_code, parsed_json_body) for one POST. Raising is allowed; callers treat it as a
# transport failure for the current key and rotate.
Transport = Callable[[str, str, dict[str, Any]], tuple[int, dict[str, Any]]]

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Permanently drop a key on 401/403 (bad key) or 404 (its project cannot serve this model — a
# 602-key pool spans many Google projects with different entitlements, so one key's 404 must not
# abort the run). 429 is quota: rest the key and come back (quota resets), do NOT drop it — this is
# what lets a long/forever run keep going. 5xx is a server overload: try another key, keep it.
_DISABLE_STATUSES = frozenset({401, 403, 404})
_COOLDOWN_STATUSES = frozenset({429})
_TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})


@dataclass
class KeyPool:
    """An ordered, de-duplicated set of API keys with round-robin rotation.

    Never stringifies key values. ``__repr__`` and error text expose only counts and indices.
    """

    keys: list[str] = field(default_factory=list)
    _idx: int = 0
    _disabled: set[int] = field(default_factory=set)  # permanently out (bad key / model not available)
    _cooldown: dict[int, float] = field(default_factory=dict)  # idx -> monotonic time it may be used again

    @classmethod
    def from_file(cls, path: str | Path) -> KeyPool:
        """Load keys from a pool file: one per line, ``#`` comments and blanks ignored, an
        optional ``NAME=value`` form accepted (value kept). Order preserved, duplicates dropped."""
        p = Path(path)
        if not p.exists():
            raise IntegrationBlocked(
                f"Gemini key pool file not found: {p}. Point SABER_GEMINI_KEY_POOL at a "
                "gitignored file with one API key per line.",
                pool_path=str(p),
            )
        keys: list[str] = []
        for raw in p.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            head, sep, tail = s.partition("=")
            if sep and " " not in head and tail.strip():
                s = tail.strip()
            keys.append(s)
        seen: set[str] = set()
        uniq: list[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                uniq.append(k)
        return cls(keys=uniq)

    def __repr__(self) -> str:  # never leak key material
        return f"KeyPool(total={len(self.keys)}, active={self.active()}, idx={self._idx})"

    def __len__(self) -> int:
        return len(self.keys)

    def _available(self, idx: int, now: float) -> bool:
        """A key is usable iff not permanently disabled and not currently cooling down."""
        if idx in self._disabled:
            return False
        until = self._cooldown.get(idx)
        return until is None or now >= until

    def active(self) -> int:
        """Count of keys usable right now (excludes disabled and currently-cooling keys)."""
        now = time.monotonic()
        return sum(1 for i in range(len(self.keys)) if self._available(i, now))

    def permanently_disabled(self) -> int:
        return len(self._disabled)

    def next_cooldown_eta(self) -> float | None:
        """Seconds until the soonest cooling key is usable again (None if none are cooling)."""
        now = time.monotonic()
        etas = [until - now for i, until in self._cooldown.items() if i not in self._disabled and until > now]
        return min(etas) if etas else None

    def current(self) -> tuple[int, str]:
        """Return ``(index, key)`` for the next usable key, advancing past disabled/cooling ones."""
        n = len(self.keys)
        if n == 0:
            raise IntegrationBlocked("Gemini key pool is empty.")
        now = time.monotonic()
        for _ in range(n):
            if self._available(self._idx, now):
                return self._idx, self.keys[self._idx]
            self._idx = (self._idx + 1) % n
        raise IntegrationBlocked("Gemini key pool exhausted: every key is disabled or cooling down.")

    def advance(self) -> None:
        if self.keys:
            self._idx = (self._idx + 1) % len(self.keys)

    def disable_current(self) -> None:
        self._disabled.add(self._idx)
        self.advance()

    def cooldown_current(self, seconds: float) -> None:
        """Rest the current key for ``seconds`` (e.g. after a 429 quota hit), then try the next."""
        self._cooldown[self._idx] = time.monotonic() + seconds
        self.advance()


def _urllib_transport(url: str, api_key: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Default transport: a single POST via stdlib ``urllib``. Key goes in the header only."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(  # noqa: S310 - fixed https Google endpoint
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8") or "{}")
        except Exception:
            payload = {}
        return exc.code, payload


def _to_gemini_contents(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """Map chat messages to Gemini ``contents`` plus an optional system instruction."""
    contents: list[dict[str, Any]] = []
    system: list[str] = []
    for m in messages:
        role = str(m.get("role", "user"))
        text = m.get("content", "")
        if not isinstance(text, str):
            text = json.dumps(text, default=str)
        if role == "system":
            system.append(text)
            continue
        contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
    return contents, ("\n\n".join(system) if system else None)


@dataclass
class GeminiProvider:
    """Fail-closed Gemini adapter. Billable calls need an explicit opt-in and budget cap."""

    model: str = "gemini-2.5-flash"
    pool: KeyPool = field(default_factory=KeyPool)
    budget_calls: int = 0  # hard cap on billable (HTTP 200) calls; 0 => blocked
    enabled: bool = False  # explicit operator opt-in
    transport: Transport | None = None  # injectable; None => urllib
    max_attempts: int = 20  # upper bound on key/backend rotations within one generate()
    backoff_s: float = 0.5  # base backoff between transient (5xx) retries; 0 disables sleeping
    cooldown_s: float = 60.0  # how long a 429'd (quota) key rests before it is tried again
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @classmethod
    def from_env(cls, model: str | None = None) -> GeminiProvider:
        """Build from environment. Does NOT call the network and does NOT enable spending unless
        both ``SABER_ENABLE_PAID_LLM=1`` and ``SABER_GEMINI_BUDGET_CALLS>0`` are set."""
        pool_path = os.environ.get("SABER_GEMINI_KEY_POOL", "keys_pool.txt")
        enabled = os.environ.get("SABER_ENABLE_PAID_LLM", "") == "1"
        try:
            budget = int(os.environ.get("SABER_GEMINI_BUDGET_CALLS", "0"))
        except ValueError:
            budget = 0
        pool = KeyPool.from_file(pool_path) if Path(pool_path).exists() else KeyPool()
        return cls(
            model=model or os.environ.get("SABER_GEMINI_MODEL", "gemini-2.5-flash"),
            pool=pool,
            budget_calls=budget,
            enabled=enabled,
        )

    @property
    def model_id(self) -> str:
        return self.model

    def _require_authorised(self) -> None:
        if not self.enabled:
            raise IntegrationBlocked(
                "Gemini provider is BLOCKED_INTEGRATION: paid LLM calls are off. The project is "
                "subscription-only; the operator must set SABER_ENABLE_PAID_LLM=1 AND a budget "
                "cap SABER_GEMINI_BUDGET_CALLS>0. The agent never enables this by itself.",
                enabled=False,
                budget_calls=self.budget_calls,
                pool_size=len(self.pool),
            )
        if self.budget_calls <= 0:
            raise IntegrationBlocked(
                "Gemini provider has no call budget: set SABER_GEMINI_BUDGET_CALLS>0 to authorise "
                "a bounded number of billable calls.",
                enabled=True,
                budget_calls=self.budget_calls,
            )
        if len(self.pool) == 0:
            raise IntegrationBlocked(
                "Gemini key pool is empty: no keys loaded from the pool file.",
                pool_size=0,
            )

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        self._require_authorised()
        if self.calls >= self.budget_calls:
            raise BudgetExceeded(
                f"Gemini call budget exhausted: {self.calls}/{self.budget_calls} billable calls used.",
                used=self.calls,
                budget=self.budget_calls,
            )

        contents, system = _to_gemini_contents(messages)
        body: dict[str, Any] = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = GEMINI_ENDPOINT.format(model=self.model)
        send = self.transport or _urllib_transport

        # Enough attempts to roll past a few overloaded backends and exhausted keys, but bounded.
        max_attempts = max(3, min(self.pool.active(), self.max_attempts))
        last_status: int | None = None
        transient = 0
        for _ in range(max_attempts):
            if self.pool.active() == 0:
                break
            idx, key = self.pool.current()
            try:
                status, data = send(url, key, body)
            except Exception as exc:  # transport failure for this key: rotate, do not leak key
                last_status = None
                self.pool.disable_current()
                _ = exc
                continue
            last_status = status
            if status == 200:
                return self._parse_ok(data)
            if status in _DISABLE_STATUSES:
                self.pool.disable_current()
                continue
            if status in _COOLDOWN_STATUSES:  # quota: rest this key, come back to it later
                self.pool.cooldown_current(self.cooldown_s)
                continue
            if status in _TRANSIENT_STATUSES:  # server overloaded: keep the key, try another backend
                transient += 1
                self.pool.advance()
                if self.backoff_s:
                    time.sleep(min(self.backoff_s * transient, 2.0))
                continue
            raise IntegrationBlocked(
                f"Gemini returned HTTP {status} (key #{idx}); not retrying this status.",
                http_status_from_provider=status,
                key_index=idx,
            )
        raise IntegrationBlocked(
            f"Gemini call did not succeed after {max_attempts} attempts (last status {last_status}); "
            f"{self.pool.active()}/{len(self.pool)} keys still enabled. 5xx means the model is "
            "overloaded — retry later.",
            last_status=last_status,
            active_keys=self.pool.active(),
        )

    def _parse_ok(self, data: dict[str, Any]) -> LLMResponse:
        candidates = data.get("candidates") or []
        text = ""
        stop = "end_turn"
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
            stop = candidates[0].get("finishReason", "STOP") or "STOP"
        usage = data.get("usageMetadata") or {}
        in_tok = int(usage.get("promptTokenCount", 0))
        out_tok = int(usage.get("candidatesTokenCount", 0))
        self.calls += 1
        self.input_tokens += in_tok
        self.output_tokens += out_tok
        self.pool.advance()  # spread load across the pool
        return LLMResponse(
            text=text,
            model_id=self.model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            tool_calls=0,
            stop_reason=str(stop),
        )
