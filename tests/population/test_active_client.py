"""The always-on benign client: benign by construction, deterministic, and safe without an LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from saber.agents.provider import LLMResponse
from saber.domain.errors import BudgetExceeded, IntegrationBlocked
from saber.population.active_client import (
    CATEGORIES,
    llm_profile,
    phase_multiplier,
    run_active_client,
    scripted_default_profile,
)
from saber.range.live.controlplane import _derive_truth
from saber.subtasks._hv.common import Rng

_SCENARIOS = ("web_sqli_probe", "auth_bruteforce", "fs_change", "persistence")


@dataclass
class _FakeProvider:
    """Minimal LLMProvider returning a fixed text (or raising) for profile calls."""

    text: str = "{}"
    raises: Exception | None = None
    calls: int = 0

    @property
    def model_id(self) -> str:
        return "fake-1"

    def generate(self, messages: list[dict[str, Any]], *, tools: Any = None,
                 max_tokens: int = 1024) -> LLMResponse:  # fmt: skip
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return LLMResponse(text=self.text, model_id="fake-1", input_tokens=10, output_tokens=5)


def _run(workdir: Path, **kw: Any) -> Any:
    """Run the daemon with time mocked out and a fixed working hour."""
    defaults: dict[str, Any] = dict(
        workdir=workdir, seed=7, base_interval_s=20.0, rhythm="flat",
        max_ticks=30, hour_fn=lambda: 10, clock=lambda: 0.0, sleep_fn=lambda _s: None,
    )  # fmt: skip
    defaults.update(kw)
    return run_active_client(**defaults)


def test_scripted_runs_with_no_provider_and_produces_log(tmp_path: Path) -> None:
    rep = _run(tmp_path, provider=None)
    assert rep.ticks == 30
    assert rep.requests_sent > 0
    assert rep.log_lines >= rep.requests_sent  # every sent request is one logged line
    assert rep.llm_calls == 0  # pure scripted: no billable calls
    assert rep.reset_ok is True
    assert set(rep.by_category) == set(CATEGORIES)
    assert sum(rep.by_category.values()) > 0


def test_benign_by_construction_no_scenario_truth_fires(tmp_path: Path) -> None:
    """The continuous log must contain NOTHING any scenario's server-side truth-derivation flags."""
    rep = _run(tmp_path, provider=None)
    lines = [json.loads(ln) for ln in Path(rep.access_log).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, "expected a non-empty access log"
    assert all(str(r.get("target", "")).startswith("/") for r in lines)  # loopback paths only
    assert all(r.get("status") != 401 for r in lines)  # logins use the valid password

    fs_root = tmp_path / "active-client" / "webroot"
    cron_root = tmp_path / "active-client" / "cronroot"
    for scenario in _SCENARIOS:
        truth = _derive_truth(scenario, lines, fs_root, cron_root)
        assert truth == set(), f"{scenario}: benign client produced a flagged line {sorted(truth)}"


def test_deterministic_for_same_seed(tmp_path: Path) -> None:
    a = _run(tmp_path / "a", provider=None)
    b = _run(tmp_path / "b", provider=None)
    assert a.by_category == b.by_category
    assert a.requests_sent == b.requests_sent
    assert a.ticks == b.ticks


def test_degrades_to_scripted_when_budget_exhausted(tmp_path: Path) -> None:
    prov = _FakeProvider(raises=BudgetExceeded("cap reached"))
    rep = _run(tmp_path, provider=prov, max_ticks=10)
    assert rep.ticks == 10  # keeps living after the LLM is cut off
    assert rep.llm_calls == 0  # the raising call is not counted as a successful profile
    assert rep.requests_sent > 0  # scripted traffic continues
    assert any(p.get("source") == "budget-exhausted" for p in rep.profiles_used)


def test_transient_block_keeps_running(tmp_path: Path) -> None:
    prov = _FakeProvider(raises=IntegrationBlocked("all keys cooling"))
    rep = _run(tmp_path, provider=prov, max_ticks=8)
    assert rep.ticks == 8
    assert rep.requests_sent > 0
    assert any(p.get("source") == "blocked-transient" for p in rep.profiles_used)


def test_llm_profile_keeps_only_known_categories_and_clamps(tmp_path: Path) -> None:
    prov = _FakeProvider(
        text='{"weights": {"browse": 2, "search": 1, "evil_cat": 5}, "intensity": 99, "note": "busy"}'
    )
    prof = llm_profile(prov, Rng("t", "1"), hour=10)
    assert prof.source == "llm"
    assert "evil_cat" not in prof.weights
    assert set(prof.weights) <= set(CATEGORIES)
    assert prof.intensity == 30.0  # clamped to the max
    # Only emits benign targets for known categories.
    norm = prof.normalized()
    assert abs(sum(norm.values()) - 1.0) < 1e-9


def test_llm_profile_falls_back_on_junk(tmp_path: Path) -> None:
    prof = llm_profile(_FakeProvider(text="sorry, no json here"), Rng("t", "2"), hour=3)
    assert prof.source == "scripted-fallback"
    assert set(prof.weights) <= set(CATEGORIES)


def test_phase_multiplier_shapes_the_day() -> None:
    assert phase_multiplier(3, "real") < phase_multiplier(20, "real") < phase_multiplier(10, "real")
    assert phase_multiplier(10, "flat") == 1.0
    assert phase_multiplier(2, "real") > 0  # night still idles, never fully silent


def test_hybrid_uses_llm_profile_then_replays(tmp_path: Path) -> None:
    """With a provider, the daemon spends exactly one profiler call per refresh window."""
    prov = _FakeProvider(text='{"weights": {"browse": 1, "login": 1}, "intensity": 6}')
    # clock stays 0 and refresh window is huge -> exactly one refresh at the first tick.
    rep = _run(tmp_path, provider=prov, max_ticks=12, profile_refresh_s=1e9)
    assert rep.llm_calls == 1
    assert any(p.get("source") == "llm" for p in rep.profiles_used)
    assert rep.requests_sent > 0


def test_scripted_default_profile_normalizes() -> None:
    norm = scripted_default_profile().normalized()
    assert abs(sum(norm.values()) - 1.0) < 1e-9
    assert set(norm) == set(CATEGORIES)
