"""Agent provider, specialist router, baselines and the experiment matrix (offline)."""

from __future__ import annotations

import pytest

from saber.agents import BlockedAnthropicProvider, SpecialistRouter, StubProvider
from saber.agents.baselines import BaselineId, solve_episode
from saber.domain.errors import IntegrationBlocked
from saber.episodes import build_episode
from saber.episodes.runner import run_reference
from saber.experiments import run_matrix


def test_stub_provider_is_deterministic_and_offline() -> None:
    p = StubProvider()
    msgs = [{"role": "user", "content": "triage this alert"}]
    r1 = p.generate(msgs)
    r2 = StubProvider().generate(msgs)
    assert r1.text == r2.text
    assert r1.input_tokens > 0 and r1.model_id == "stub-deterministic-1"
    assert p.calls == 1


def test_real_provider_is_blocked() -> None:
    with pytest.raises(IntegrationBlocked):
        BlockedAnthropicProvider().generate([{"role": "user", "content": "x"}])


def test_specialist_router_maps_service() -> None:
    router = SpecialistRouter(
        solver=lambda ep: run_reference(ep) and (run_reference(ep).submission.answer, [])
    )
    ep = build_episode("T2012.001", 1, "default")
    specialist, answer, _ = router.solve(ep)
    assert specialist == "hunt"
    assert answer is not None
    assert router.coverage()["hunt"] == 1


def test_b0_and_oracle_run_offline() -> None:
    ep = build_episode("T1112.001", 1, "tp")
    oracle = solve_episode(BaselineId.ORACLE, ep)
    assert oracle.score.score == 1.0
    b0 = solve_episode(BaselineId.B0_RULES, ep)
    assert b0.score.validity.value == "VALID"


def test_llm_baselines_blocked() -> None:
    ep = build_episode("T1112.001", 1, "tp")
    for b in (
        BaselineId.B1_SINGLE_AGENT,
        BaselineId.B2_SPECIALISTS,
        BaselineId.B3_SPECIALISTS_SHARED,
        BaselineId.B4_WITH_CONTENT,
    ):
        with pytest.raises(IntegrationBlocked):
            solve_episode(b, ep)


def test_run_matrix_aggregates_with_ci() -> None:
    report = run_matrix(subtask_ids=["T1112.001", "T2012.001", "T0173.001"], seeds=[1, 42])
    assert report["labels"] == ["DEV_SIMULATION_ONLY"]
    assert set(report["baselines_run"]) == {"B0", "ORACLE"}
    assert set(report["baselines_blocked"]) >= {"B1", "B2", "B3", "B4"}
    by_baseline = {r["baseline"]: r for r in report["by_baseline"]}
    # Oracle is the upper bound: mean 1.0 across subtasks.
    assert by_baseline["ORACLE"]["mean"] == pytest.approx(1.0)
    assert 0.0 <= by_baseline["B0"]["ci_low"] <= by_baseline["B0"]["ci_high"] <= 1.0
    assert by_baseline["ORACLE"]["n_subtasks"] == 3
    assert report["specialist_coverage"]  # routed to specialists
    assert any(c["baseline"] == "B0" for c in report["cells"])
