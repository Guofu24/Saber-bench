"""No real keys/network. Budgets are reserved before calls and persist across restarts."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from saber.agents.gemini import KeyPool
from saber.domain.errors import BudgetExceeded, IntegrationBlocked
from saber.world.quota import QuotaProvider
from saber.world.store import Store

MESSAGES = [{"role": "user", "content": "hello"}]


def ok(url, key, body):
    return 200, {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2},
    }


def test_budget_reserved_and_survives_restart(tmp_path):
    store = Store(tmp_path)
    pool = KeyPool(keys=["fake-a", "fake-b"])
    provider = QuotaProvider(store, pool, model="test", call_budget=1, transport=ok)
    assert provider.generate(MESSAGES).text == "ok"
    store.close()
    store = Store(tmp_path)
    provider = QuotaProvider(store, pool, model="test", call_budget=1, transport=ok)
    with pytest.raises(BudgetExceeded):
        provider.generate(MESSAGES)
    assert store.get("meta", "llm_usage")["successes"] == 1
    assert "fake-a" not in json.dumps(store.items("quota"))
    store.close()


def test_keys_in_same_project_share_quota(tmp_path):
    store = Store(tmp_path)
    provider = QuotaProvider(
        store,
        KeyPool(keys=["a", "b"]),
        model="test",
        call_budget=10,
        rpm=1,
        project_groups={"0": "same-project", "1": "same-project"},
        transport=ok,
    )
    provider.generate(MESSAGES)
    with pytest.raises(IntegrationBlocked, match="resting"):
        provider.generate(MESSAGES)
    assert store.get("meta", "llm_usage")["attempts"] == 1
    store.close()


def test_429_respects_retry_hint_and_does_not_disable_project(tmp_path):
    store = Store(tmp_path)
    provider = QuotaProvider(
        store,
        KeyPool(keys=["fake-a"]),
        model="test",
        call_budget=10,
        transport=lambda u, k, b: (429, {"error": {"details": [{"retryDelay": "120s"}]}}),
    )
    with pytest.raises(IntegrationBlocked, match="429"):
        provider.generate(MESSAGES)
    q = next(iter(store.items("quota").values()))
    assert q["disabled"] is False and q["cool_until"] > q["day"][0] + 119
    with pytest.raises(IntegrationBlocked, match="resting"):
        provider.generate(MESSAGES)
    assert store.get("meta", "llm_usage")["attempts"] == 1
    store.close()


def test_transport_error_is_counted_redacted_and_recoverable(tmp_path):
    def broken(url, key, body):
        raise RuntimeError(f"SECRET {key}")

    store = Store(tmp_path)
    provider = QuotaProvider(
        store, KeyPool(keys=["secret-key"]), model="test", call_budget=10, transport=broken
    )
    with pytest.raises(IntegrationBlocked) as exc:
        provider.generate(MESSAGES)
    assert "secret-key" not in str(exc.value)
    assert store.get("meta", "llm_usage")["attempts"] == 1
    assert next(iter(store.items("quota").values()))["disabled"] is False
    store.close()


def test_prompt_larger_than_local_token_cap_makes_no_call(tmp_path):
    store = Store(tmp_path)
    provider = QuotaProvider(
        store, KeyPool(keys=["a"]), model="test", call_budget=10, tpm=10, transport=ok
    )
    with pytest.raises(IntegrationBlocked, match="TPM"):
        provider.generate(MESSAGES)
    assert store.get("meta", "llm_usage") is None
    store.close()


def test_parallel_calls_cannot_overspend_persistent_budget(tmp_path):
    store = Store(tmp_path)
    provider = QuotaProvider(
        store, KeyPool(keys=["a", "b", "c"]), model="test", call_budget=3, rpm=10, transport=ok
    )

    def call(_):
        try:
            return provider.generate(MESSAGES).text
        except BudgetExceeded:
            return "budget"

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(call, range(12)))
    assert results.count("ok") == 3
    assert store.get("meta", "llm_usage")["attempts"] == 3
    assert store.get("meta", "llm_usage")["successes"] == 3
    store.close()
