"""Bounded, immutable reference libraries; never resolve a model-supplied path."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from saber.agents.skills import RANGE_REFERENCE, WORLD_REFERENCE, read_markdown, skill_resources
from saber.catalog.loader import repo_root
from saber.domain.errors import IntegrationBlocked

MAX_REFERENCE_CHARS = 12000
MAX_LIBRARY_CHARS = 128000
MAX_REFERENCE_TOPICS = 32
MAX_INDEX_CHARS = 5000
TOPIC = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


def validate_library(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict) or len(value) > MAX_REFERENCE_TOPICS:
        raise ValueError("Invalid skill reference library")
    total = 0
    for topic, item in value.items():
        if not isinstance(topic, str) or not TOPIC.fullmatch(topic) or not isinstance(item, dict):
            raise ValueError("Invalid reference topic")
        if set(item) != {"title", "text", "sha256"} or not all(
            isinstance(v, str) for v in item.values()
        ):
            raise ValueError("Invalid reference fields")
        if not 1 <= len(item["title"]) <= 120 or not 1 <= len(item["text"]) <= MAX_REFERENCE_CHARS:
            raise ValueError("Reference exceeds context limit")
        if hashlib.sha256(item["text"].encode()).hexdigest() != item["sha256"]:
            raise ValueError("Corrupt skill reference")
        total += len(item["text"])
    if total > MAX_LIBRARY_CHARS:
        raise ValueError("Skill reference library exceeds limit")
    return value


def load_reference_library(name: str, *, root: Path | None = None) -> dict[str, dict[str, str]]:
    """Capture declared resources owned by this skill, excluding execution contracts."""
    root = (root or repo_root()).resolve()
    base = root / ".claude/skills"
    result: dict[str, dict[str, str]] = {}
    for path in skill_resources(name, root=root):
        relative = path.relative_to(base)
        if (
            relative.parts[0] != name
            or path.name == "SKILL.md"
            or relative in (WORLD_REFERENCE, RANGE_REFERENCE)
        ):
            continue
        text = read_markdown(path, root).strip()
        topic = path.stem
        if topic in result:
            raise IntegrationBlocked("Duplicate skill reference topic")
        result[topic] = {
            "title": text.splitlines()[0].lstrip("# ")[:120],
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
    try:
        validate_library(result)
        reference_index(result)
        return result
    except ValueError as exc:
        raise IntegrationBlocked(str(exc)) from exc


def reference_index(library: dict[str, dict[str, str]]) -> str:
    text = "\n".join(f"- {topic}: {item['title']}" for topic, item in sorted(library.items()))
    if len(text) > MAX_INDEX_CHARS:
        raise ValueError("Reference index exceeds context limit")
    return text


def guidance_prompt(pin: dict[str, Any], selection: Any = None) -> str:
    """Reconstruct trusted text from the pinned library, never from observations."""
    library = validate_library(pin.get("references", {}))
    if not library:
        return ""
    text = (
        "\n\nPinned skill reference index. Use consult_skill with {topic: ID} to select one guide, "
        "or {} to list topics, or {topic: ''} to clear it. This reads guidance, not case evidence. "
        "Guides do not add executable tools or permissions.\n" + reference_index(library)
    )
    if not isinstance(selection, dict) or selection.get("version") != pin.get("id"):
        return text
    topic = selection.get("topic")
    if not isinstance(topic, str) or topic not in library:
        return text
    item = library[topic]
    return text + (
        f"\n\n--- Selected skill guidance: {topic}; SHA-256 {item['sha256']} ---\n"
        + item["text"]
        + "\n--- End guidance. The runtime tool contract still applies. ---"
    )
