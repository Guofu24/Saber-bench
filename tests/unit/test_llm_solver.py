"""LLM episode solver wiring — fully offline. A fake provider returns canned text so the solve +
grade path is exercised with no network and no spend."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from saber.agents.baselines import BaselineId, solve_episode
from saber.agents.llm_solver import build_messages, load_skill_playbook, solve_episode_with_llm
from saber.agents.provider import LLMResponse
from saber.domain.errors import IntegrationBlocked
from saber.episodes import build_episode


@dataclass
class FakeProvider:
    text: str
    model: str = "fake-model"
    last_messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def model_id(self) -> str:
        return self.model

    def generate(self, messages, *, tools=None, max_tokens=1024) -> LLMResponse:
        self.last_messages = messages
        return LLMResponse(text=self.text, model_id=self.model, input_tokens=10, output_tokens=5)


def _oracle_payload(sid: str, variant: str):
    ep = build_episode(sid, 1, variant)
    answer = ep.subtask.answer_from_truth(ep.bundle.sealed_truth)
    refs = ep.subtask.perfect_evidence_refs(ep.bundle)
    return ep, answer, refs


def test_correct_wrapped_answer_scores_full() -> None:
    ep, answer, refs = _oracle_payload("T1112.001", "tp")
    text = json.dumps({"answer": answer, "evidence_refs": refs})
    run = solve_episode_with_llm(ep, FakeProvider(text), use_skill=True)
    assert run.score == 1.0
    assert run.validity == "VALID"
    assert run.model_id == "fake-model"
    assert run.evidence_refs == refs


def test_bare_answer_with_refs_mixed_in_is_split() -> None:
    ep, answer, refs = _oracle_payload("T1112.001", "tp")
    # Model returned the bare answer object with evidence_refs mixed in (no "answer" wrapper).
    text = json.dumps({**answer, "evidence_refs": refs})
    run = solve_episode_with_llm(ep, FakeProvider(text), use_skill=False)
    assert run.score == 1.0  # evidence_refs stripped out of the answer before schema validation
    assert run.evidence_refs == refs


def test_garbage_output_scores_zero_without_crashing() -> None:
    ep = build_episode("T1112.001", 1, "tp")
    run = solve_episode_with_llm(ep, FakeProvider("I cannot help with that."), use_skill=True)
    assert run.score == 0.0
    assert run.answer is None
    assert "no json" in run.parse_note.lower()


def test_use_skill_loads_playbook_into_system_prompt() -> None:
    ep = build_episode("T1112.001", 1, "tp")
    fp = FakeProvider("{}")
    solve_episode_with_llm(ep, fp, use_skill=True)
    system_with_skill = fp.last_messages[0]["content"]
    fp2 = FakeProvider("{}")
    solve_episode_with_llm(ep, fp2, use_skill=False)
    system_generic = fp2.last_messages[0]["content"]
    playbook = load_skill_playbook("MON")
    assert playbook  # the MON skill exists
    assert len(system_with_skill) > len(system_generic)
    assert playbook[:40] in system_with_skill


def test_build_messages_carries_no_sealed_truth() -> None:
    ep = build_episode("T1112.001", 1, "tp")
    blob = json.dumps(build_messages(ep, use_skill=True), ensure_ascii=False)
    # The verdict label lives in the sealed truth; it must not appear in the agent-visible prompt.
    assert "sealed_truth" not in blob
    assert ep.manifest.instructions in blob


def test_solve_episode_b2_uses_provider_and_b3_stays_blocked() -> None:
    ep, answer, refs = _oracle_payload("T0167.001", "default")
    prov = FakeProvider(json.dumps({"answer": answer, "evidence_refs": refs}))
    res = solve_episode(BaselineId.B2_SPECIALISTS, ep, provider=prov)
    assert res.score.score == 1.0
    # B3/B4 need orchestration that is not wired yet: still blocked even with a provider.
    with pytest.raises(IntegrationBlocked):
        solve_episode(BaselineId.B3_SPECIALISTS_SHARED, ep, provider=prov)


def test_llm_baselines_still_blocked_without_provider() -> None:
    ep = build_episode("T1112.001", 1, "tp")
    for b in (BaselineId.B1_SINGLE_AGENT, BaselineId.B2_SPECIALISTS):
        with pytest.raises(IntegrationBlocked):
            solve_episode(b, ep)
