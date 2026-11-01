"""Gemini key-pool adapter: fully offline. A fake transport stands in for the network, so these
tests exercise rotation, the budget cap and the fail-closed gate without any billable call."""

from __future__ import annotations

import pytest

from saber.agents.gemini import GeminiProvider, KeyPool
from saber.domain.errors import BudgetExceeded, IntegrationBlocked

FAKE_KEYS = ["fake-key-aaa", "fake-key-bbb", "fake-key-ccc"]


def _ok_body(text: str = "hi", in_tok: int = 5, out_tok: int = 3) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": in_tok, "candidatesTokenCount": out_tok},
    }


def _pool_file(tmp_path, keys=FAKE_KEYS, extra: str = "") -> str:
    p = tmp_path / "keys_pool.txt"
    p.write_text(extra + "\n".join(keys) + "\n", encoding="utf-8")
    return str(p)


# ---- pool loading -------------------------------------------------------------------------------


def test_pool_loads_dedupes_and_skips_comments(tmp_path) -> None:
    body = "# header comment\n\nfake-key-aaa\nfake-key-aaa\nNAME=fake-key-bbb\n  fake-key-ccc  \n"
    (tmp_path / "keys_pool.txt").write_text(body, encoding="utf-8")
    pool = KeyPool.from_file(tmp_path / "keys_pool.txt")
    assert pool.keys == ["fake-key-aaa", "fake-key-bbb", "fake-key-ccc"]
    assert len(pool) == 3 and pool.active() == 3


def test_pool_repr_never_leaks_key_values(tmp_path) -> None:
    pool = KeyPool.from_file(_pool_file(tmp_path))
    assert "fake-key" not in repr(pool)


def test_missing_pool_file_is_blocked(tmp_path) -> None:
    with pytest.raises(IntegrationBlocked):
        KeyPool.from_file(tmp_path / "nope.txt")


# ---- fail-closed gate ---------------------------------------------------------------------------


def test_disabled_by_default_raises_before_any_network(tmp_path) -> None:
    calls: list = []

    def transport(url, key, body):
        calls.append(key)
        return 200, _ok_body()

    prov = GeminiProvider(pool=KeyPool.from_file(_pool_file(tmp_path)), transport=transport)
    with pytest.raises(IntegrationBlocked):
        prov.generate([{"role": "user", "content": "x"}])
    assert calls == []  # never reached the transport


def test_enabled_but_no_budget_is_blocked(tmp_path) -> None:
    prov = GeminiProvider(
        pool=KeyPool.from_file(_pool_file(tmp_path)),
        enabled=True,
        budget_calls=0,
        transport=lambda u, k, b: (200, _ok_body()),
    )
    with pytest.raises(IntegrationBlocked):
        prov.generate([{"role": "user", "content": "x"}])


def test_enabled_empty_pool_is_blocked() -> None:
    prov = GeminiProvider(
        pool=KeyPool(), enabled=True, budget_calls=5, transport=lambda u, k, b: (200, _ok_body())
    )
    with pytest.raises(IntegrationBlocked):
        prov.generate([{"role": "user", "content": "x"}])


# ---- happy path (fake transport, no spend) ------------------------------------------------------


def test_authorised_call_returns_response_and_counts(tmp_path) -> None:
    seen = []

    def transport(url, key, body):
        seen.append(key)
        assert "generateContent" in url
        return 200, _ok_body("answer", in_tok=11, out_tok=4)

    prov = GeminiProvider(
        pool=KeyPool.from_file(_pool_file(tmp_path)),
        enabled=True,
        budget_calls=3,
        transport=transport,
    )
    r = prov.generate([{"role": "system", "content": "be terse"}, {"role": "user", "content": "q"}])
    assert r.text == "answer" and r.input_tokens == 11 and r.output_tokens == 4
    assert prov.calls == 1 and prov.input_tokens == 11
    assert seen == ["fake-key-aaa"]  # first key used


def test_round_robin_spreads_across_pool(tmp_path) -> None:
    seen = []
    prov = GeminiProvider(
        pool=KeyPool.from_file(_pool_file(tmp_path)),
        enabled=True,
        budget_calls=5,
        transport=lambda u, k, b: (seen.append(k), (200, _ok_body()))[1],
    )
    for _ in range(3):
        prov.generate([{"role": "user", "content": "q"}])
    assert seen == FAKE_KEYS  # one call each, rotating


# ---- budget cap ---------------------------------------------------------------------------------


def test_budget_cap_raises_budget_exceeded(tmp_path) -> None:
    prov = GeminiProvider(
        pool=KeyPool.from_file(_pool_file(tmp_path)),
        enabled=True,
        budget_calls=2,
        transport=lambda u, k, b: (200, _ok_body()),
    )
    prov.generate([{"role": "user", "content": "q"}])
    prov.generate([{"role": "user", "content": "q"}])
    with pytest.raises(BudgetExceeded):
        prov.generate([{"role": "user", "content": "q"}])
    assert prov.calls == 2  # the blocked attempt was not billed


# ---- key rotation on auth/quota errors ----------------------------------------------------------


def test_rotates_past_rate_limited_key(tmp_path) -> None:
    def transport(url, key, body):
        if key == "fake-key-aaa":
            return 429, {"error": {"message": "quota"}}
        return 200, _ok_body("ok")

    pool = KeyPool.from_file(_pool_file(tmp_path))
    prov = GeminiProvider(pool=pool, enabled=True, budget_calls=5, transport=transport)
    r = prov.generate([{"role": "user", "content": "q"}])
    assert r.text == "ok"
    assert pool.active() == 2  # the 429 key got disabled
    assert prov.calls == 1


def test_transient_503_rotates_without_disabling_keys(tmp_path) -> None:
    n = {"i": 0}

    def transport(url, key, body):
        n["i"] += 1
        if n["i"] == 1:  # first backend overloaded
            return 503, {"error": {"message": "The model is overloaded."}}
        return 200, _ok_body("recovered")

    pool = KeyPool.from_file(_pool_file(tmp_path))
    prov = GeminiProvider(pool=pool, enabled=True, budget_calls=5, backoff_s=0, transport=transport)
    r = prov.generate([{"role": "user", "content": "q"}])
    assert r.text == "recovered"
    assert pool.active() == 3  # a 503 must NOT disable any key
    assert prov.calls == 1


def test_persistent_5xx_is_blocked_not_crashed(tmp_path) -> None:
    prov = GeminiProvider(
        pool=KeyPool.from_file(_pool_file(tmp_path)),
        enabled=True,
        budget_calls=5,
        backoff_s=0,
        transport=lambda u, k, b: (503, {"error": "overloaded"}),
    )
    with pytest.raises(IntegrationBlocked):
        prov.generate([{"role": "user", "content": "q"}])
    assert prov.calls == 0 and KeyPool.from_file(_pool_file(tmp_path)).active() == 3


def test_429_cools_down_not_permanently_disabled(tmp_path) -> None:
    pool = KeyPool.from_file(_pool_file(tmp_path))
    # cooldown_s large: the 429'd key rests (not usable now) but is NOT permanently disabled.
    prov = GeminiProvider(
        pool=pool,
        enabled=True,
        budget_calls=5,
        cooldown_s=999,
        transport=lambda u, k, b: (429, {}) if k == "fake-key-aaa" else (200, _ok_body()),
    )
    r = prov.generate([{"role": "user", "content": "q"}])
    assert r.text == "hi"
    assert pool.permanently_disabled() == 0  # quota is temporary, key not dropped
    assert pool.active() == 2  # the cooling key is excluded from active right now
    assert pool.next_cooldown_eta() is not None


def test_429_key_returns_after_cooldown_expires(tmp_path) -> None:
    pool = KeyPool.from_file(_pool_file(tmp_path, keys=["only-key"]))
    # cooldown_s=0: a 429 rests the key for 0s, so it is immediately usable again next call.
    seen = {"n": 0}

    def transport(url, key, body):
        seen["n"] += 1
        return (429, {}) if seen["n"] == 1 else (200, _ok_body())

    prov = GeminiProvider(
        pool=pool, enabled=True, budget_calls=5, cooldown_s=0, transport=transport
    )
    r = prov.generate([{"role": "user", "content": "q"}])
    assert r.text == "hi"  # same single key recovered after a 0s cooldown
    assert pool.active() == 1


def test_all_keys_failing_is_blocked(tmp_path) -> None:
    prov = GeminiProvider(
        pool=KeyPool.from_file(_pool_file(tmp_path)),
        enabled=True,
        budget_calls=5,
        transport=lambda u, k, b: (401, {"error": "bad key"}),
    )
    with pytest.raises(IntegrationBlocked):
        prov.generate([{"role": "user", "content": "q"}])
    assert prov.calls == 0


def test_transport_exception_rotates_and_does_not_leak(tmp_path) -> None:
    def transport(url, key, body):
        if key == "fake-key-aaa":
            raise ConnectionError("boom")
        return 200, _ok_body("recovered")

    prov = GeminiProvider(
        pool=KeyPool.from_file(_pool_file(tmp_path)),
        enabled=True,
        budget_calls=5,
        transport=transport,
    )
    r = prov.generate([{"role": "user", "content": "q"}])
    assert r.text == "recovered"


# ---- from_env stays fail-closed -----------------------------------------------------------------


def test_from_env_defaults_to_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SABER_GEMINI_KEY_POOL", _pool_file(tmp_path))
    monkeypatch.delenv("SABER_ENABLE_PAID_LLM", raising=False)
    monkeypatch.delenv("SABER_GEMINI_BUDGET_CALLS", raising=False)
    prov = GeminiProvider.from_env()
    assert prov.enabled is False and prov.budget_calls == 0 and len(prov.pool) == 3
    with pytest.raises(IntegrationBlocked):
        prov.generate([{"role": "user", "content": "x"}])
