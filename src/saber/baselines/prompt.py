"""Build the LLM baseline prompt from a gold episode and extract its JSON answer.

The prompt carries only PUBLIC inputs (never the sealed truth) plus the subtask's
source instruction and the pilot's ``OUTPUT_SPEC``. Extraction is tolerant of the two
common model habits (a ```json fence, or a short preamble before the object) but never
executes anything and returns ``None`` when no JSON object can be recovered.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from saber.gold.base import GoldEpisode, GoldPilot


def build_prompt(pilot: GoldPilot, episode: GoldEpisode) -> str:
    artifact = json.dumps(episode.public_inputs, ensure_ascii=False, indent=2, default=str)
    return (
        "You are a senior SOC analyst completing one benchmark subtask offline. "
        "Work only from the artifact below; you have no tools and no external access.\n\n"
        f"SUBTASK {pilot.SUBTASK_ID} — instruction:\n{pilot.instructions()}\n\n"
        f"INPUT ARTIFACT (JSON):\n{artifact}\n\n"
        "Return ONLY one JSON object, no markdown fence and no commentary, matching "
        f"exactly this shape:\n{pilot.OUTPUT_SPEC}\n\n"
        "Output the single JSON object and nothing else."
    )


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # drop the opening fence line (``` or ```json) and the trailing fence
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1 :]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _first_json_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` substring, respecting strings/escapes."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_answer_json(text: str) -> tuple[dict[str, Any] | None, str]:
    """Recover the answer object from model output. Returns ``(obj_or_None, note)``."""
    if not text or not text.strip():
        return None, "empty output"
    candidate = _strip_fence(text)
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj, "parsed whole output"
    except json.JSONDecodeError:
        pass
    snippet = _first_json_object(candidate)
    if snippet is not None:
        try:
            obj = json.loads(snippet)
            if isinstance(obj, dict):
                return obj, "parsed first JSON object in output"
        except json.JSONDecodeError:
            return None, "found braces but JSON invalid"
    return None, "no JSON object found"
