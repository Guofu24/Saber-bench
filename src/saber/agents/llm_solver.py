"""LLM-backed episode solver (H5 wiring): a specialist agent loads its service playbook from
``.claude/skills`` and solves ONE benchmark episode from the public manifest + inputs, returning a
gradeable submission.

This is what lets a real model — e.g. the pooled :class:`~saber.agents.gemini.GeminiProvider` —
drive baselines B1 (generic single agent) and B2 (service specialist with the operational skill).
It uses ONLY agent-visible inputs (never the sealed truth), reuses the tolerant JSON extractor from
the gold baseline path, and grades with the real scorer via :func:`run_stub`.

Honesty: results are ``DEV_SIMULATION_ONLY`` measurements of whether the loop runs and produces a
gradeable answer. Nothing here promotes a subtask to READY_BENCHMARK, and the solver never claims
model quality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from saber.agents.provider import LLMProvider
from saber.agents.skills import load_playbook
from saber.baselines.prompt import extract_answer_json
from saber.domain.errors import IntegrationBlocked
from saber.episodes.builder import BuiltEpisode
from saber.episodes.runner import EpisodeResult, run_stub

SERVICE_SKILL = {"MON": "soc-mon", "CNT": "soc-cnt", "HUNT": "soc-hunt", "IR": "soc-ir"}

GENERIC_ROLE = (
    "You are a senior SOC analyst completing one benchmark subtask offline. Work only from the "
    "case material provided; you have no tools and no external access."
)


def load_skill_playbook(service: str) -> str:
    """Load a complete specialist playbook, or fail before any provider request."""
    name = SERVICE_SKILL.get(service)
    if not name:
        raise IntegrationBlocked("Unknown specialist service.")
    return load_playbook(name)


def build_messages(episode: BuiltEpisode, *, use_skill: bool) -> list[dict[str, str]]:
    """Build the (system, user) chat messages from PUBLIC episode material only."""
    service = episode.manifest.service
    inputs_json = json.dumps(
        episode.bundle.public_inputs, ensure_ascii=False, indent=2, default=str
    )
    schema_json = json.dumps(episode.manifest.output_schema, ensure_ascii=False, default=str)
    if use_skill:
        playbook = load_skill_playbook(service)
        system = (
            playbook
            + "\n\n---\nYou are now working ONE benchmark case. Apply the playbook above, but output "
            "ONLY the final machine answer in the exact JSON contract requested — no narration, no "
            "worklog, no markdown."
        )
    else:
        system = GENERIC_ROLE
    user = (
        f"SUBTASK {episode.manifest.subtask_id} ({service}) — instruction:\n"
        f"{episode.manifest.instructions}\n\n"
        f"CASE INPUT (JSON):\n{inputs_json}\n\n"
        f"The `answer` object MUST validate against this JSON schema:\n{schema_json}\n\n"
        f"Citeable evidence IDs (use these verbatim for evidence_refs): "
        f"{json.dumps(episode.evidence_ids)}\n\n"
        "Return ONLY one JSON object, no markdown fence, of EXACTLY this shape:\n"
        '{"answer": <object matching the schema above>, '
        '"evidence_refs": [<citeable ids you relied on, may be empty>]}\n'
        "Output the single JSON object and nothing else."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


@dataclass(frozen=True)
class LlmEpisodeRun:
    """One LLM solve of one episode: the graded result plus provider/parse accounting."""

    result: EpisodeResult
    answer: dict[str, Any] | None
    evidence_refs: list[str]
    parse_note: str
    model_id: str
    input_tokens: int
    output_tokens: int
    raw_text: str

    @property
    def score(self) -> float:
        return self.result.score.score

    @property
    def validity(self) -> str:
        return self.result.score.validity.value


def _split_answer(obj: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Pull (answer, evidence_refs) out of the model's object, tolerating both shapes."""
    if isinstance(obj.get("answer"), dict):
        answer = obj["answer"]
        raw_refs = obj.get("evidence_refs", [])
    else:  # model returned the bare answer, possibly with evidence_refs mixed in
        answer = {k: v for k, v in obj.items() if k != "evidence_refs"}
        raw_refs = obj.get("evidence_refs", [])
    refs = (
        [str(r) for r in raw_refs if isinstance(r, (str, int)) and not isinstance(r, bool)]
        if isinstance(raw_refs, list)
        else []
    )
    return answer, refs


def solve_episode_with_llm(
    episode: BuiltEpisode,
    provider: LLMProvider,
    *,
    use_skill: bool = True,
    max_tokens: int = 2048,
    graded_at: datetime | None = None,
) -> LlmEpisodeRun:
    """Prompt the provider to solve one episode, then grade its answer with the real scorer."""
    messages = build_messages(episode, use_skill=use_skill)
    resp = provider.generate(messages, max_tokens=max_tokens)
    obj, note = extract_answer_json(resp.text)
    answer: dict[str, Any] = {}
    refs: list[str] = []
    if obj is not None:
        answer, refs = _split_answer(obj)
    result = run_stub(episode, answer, refs, graded_at=graded_at)
    return LlmEpisodeRun(
        result=result,
        answer=answer or None,
        evidence_refs=refs,
        parse_note=note,
        model_id=resp.model_id,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        raw_text=resp.text[:500],
    )
