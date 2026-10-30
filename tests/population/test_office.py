"""agent-office event emission — offline. A capturing sink stands in for the HTTP viewer, so we
assert the population loop emits the right office events without needing the Node viewer running."""

from __future__ import annotations

from saber.agents.provider import LLMResponse
from saber.population.loop import run_population_episode
from saber.population.office import ROLE_AGENTS, OfficeEmitter


class TrivialProvider:
    model = "trivial"

    @property
    def model_id(self) -> str:
        return self.model

    def generate(self, messages, *, tools=None, max_tokens=1024) -> LLMResponse:
        return LLMResponse(text="{}", model_id=self.model, input_tokens=1, output_tokens=1)


def test_emitter_without_url_is_disabled_noop(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_OFFICE_URL", raising=False)
    em = OfficeEmitter(None)
    assert em.enabled is False
    # Every method must be a safe no-op when disabled.
    em.register_agents()
    em.llm_start("red", "m")
    em.handoff("red", "blue", "x")
    em.message(None, "hi")


def test_sink_captures_agent_registration() -> None:
    events: list = []
    em = OfficeEmitter(sink=events.extend)
    assert em.enabled is True
    em.register_agents()
    agent_ids = {e["id"] for e in events if e["type"] == "agent"}
    assert agent_ids == set(ROLE_AGENTS)


def test_loop_emits_full_office_event_set(tmp_path) -> None:
    events: list = []
    em = OfficeEmitter(sink=events.extend)
    run_population_episode("web_sqli_probe", 1, TrivialProvider(), workdir=tmp_path, emitter=em)

    types = {e["type"] for e in events}
    assert {"agent", "task", "llm_start", "llm_end", "handoff", "message", "status", "tool"} <= types

    referenced = (
        {e.get("id") for e in events}
        | {e.get("from") for e in events}
        | {e.get("to") for e in events}
    )
    assert {"red", "client", "range", "orchestrator", "blue"} <= referenced

    # The orchestrator hands the case to the blue team (the routing particle).
    assert any(
        e["type"] == "handoff" and e["from"] == "orchestrator" and e["to"] == "blue" for e in events
    )
    # Each LLM turn is bracketed start->end so the viewer shows think then answer.
    assert sum(1 for e in events if e["type"] == "llm_start") == 4
    assert sum(1 for e in events if e["type"] == "llm_end") == 4
