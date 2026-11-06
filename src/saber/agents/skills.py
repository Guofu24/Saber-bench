"""Validated, bounded operational playbooks shared by all model-backed runtimes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml

from saber.agents.specialties import BLUE_SKILLS
from saber.catalog.loader import repo_root
from saber.domain.errors import IntegrationBlocked

RUNTIME_SKILLS = frozenset(
    {
        "client-user",
        "redteam-initial-access",
        "redteam-post-exploitation",
        "soc-mon",
        "soc-hunt",
        "soc-ir",
        "soc-cnt",
        "soc-orchestrator",
        *BLUE_SKILLS.values(),
    }
)
WORLD_REFERENCE = Path("soc-orchestrator/reference/continuous-world.md")
RANGE_REFERENCE = Path("soc-orchestrator/reference/soc-lab.md")
MAX_CASE_CHARS = 64000
MAX_WORLD_CHARS = 18000
MD_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_.:/-])((?:\.{1,2}/)*[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.md)"
    r"(?![A-Za-z0-9_.-])"
)


def read_markdown(path: Path, root: Path) -> str:
    """Refuse traversal, symlinked parents, oversized files and missing resources."""
    root = root.resolve()
    if not path.resolve().is_relative_to(root):
        raise IntegrationBlocked("Skill resource escapes the project.")
    current = path.absolute()
    while current != root:
        if current.is_symlink():
            raise IntegrationBlocked("Symlinked skill resources are unsupported.")
        if current.parent == current:
            raise IntegrationBlocked("Skill resource escapes the project.")
        current = current.parent
    try:
        if path.stat().st_size > 256000:
            raise IntegrationBlocked("Skill resource exceeds the file size limit.")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise IntegrationBlocked(f"Missing or unreadable skill resource: {path.name}") from exc
    if not text.strip():
        raise IntegrationBlocked(f"Empty skill resource: {path.name}")
    return text


def read_skill(name: str, root: Path) -> tuple[dict[str, Any], str]:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        raise IntegrationBlocked("Invalid skill name.")
    text = read_markdown(root / ".claude/skills" / name / "SKILL.md", root)
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)(.*)\Z", text, re.DOTALL)
    if not match:
        raise IntegrationBlocked(f"Invalid skill frontmatter: {name}")
    try:
        metadata = yaml.safe_load(match[1])
    except yaml.YAMLError as exc:
        raise IntegrationBlocked(f"Invalid skill YAML: {name}") from exc
    if not isinstance(metadata, dict) or metadata.get("name") != name:
        raise IntegrationBlocked(f"Skill name does not match directory: {name}")
    description = metadata.get("description")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise IntegrationBlocked(f"Invalid skill description: {name}")
    if "disable-model-invocation" in metadata and not isinstance(
        metadata["disable-model-invocation"], bool
    ):
        raise IntegrationBlocked(f"Invalid Claude invocation policy: {name}")
    body = match[2].strip()
    if not body or re.search(r"(?m)^\s*\[TODO:.*\]\s*$", body):
        raise IntegrationBlocked(f"Empty or unfinished skill: {name}")
    return metadata, body


def referenced_paths(path: Path, text: str) -> tuple[Path, ...]:
    return tuple(path.parent / ref for ref in dict.fromkeys(MD_REFERENCE.findall(text)))


def skill_resources(
    name: str, *, root: Path | None = None, include_library: bool = True
) -> tuple[Path, ...]:
    """Declared Markdown; optional metadata guides are pinned/exported but not eager case text."""
    root = (root or repo_root()).resolve()
    if name not in RUNTIME_SKILLS:
        raise IntegrationBlocked("Not an operational runtime skill.")
    base = root / ".claude/skills"
    queue = [base / name / "SKILL.md"]
    seen: set[Path] = set()
    resources = []
    while queue:
        path = queue.pop(0)
        resolved = path.resolve()
        if not resolved.is_relative_to(base):
            raise IntegrationBlocked("Runtime skill reference escapes the skills directory.")
        relative = resolved.relative_to(base)
        if relative.parts[0] not in RUNTIME_SKILLS or resolved.suffix != ".md":
            raise IntegrationBlocked("Runtime skill references a non-operational resource.")
        # Check the unresolved path too, so symlinked parents cannot disappear in resolve().
        text = read_markdown(path, root)
        if resolved in seen:
            continue
        path = resolved
        seen.add(path)
        if len(seen) > 64:
            raise IntegrationBlocked("Too many skill references.")
        if path.name == "SKILL.md":
            metadata, text = read_skill(path.parent.name, root)
            extra = metadata.get("metadata", {})
            if not isinstance(extra, dict):
                raise IntegrationBlocked("Invalid skill metadata.")
            library = extra.get("saber-library", [])
            if (
                not isinstance(library, list)
                or len(library) > 32
                or any(
                    not isinstance(ref, str) or not MD_REFERENCE.fullmatch(ref) for ref in library
                )
            ):
                raise IntegrationBlocked("Invalid on-demand skill references.")
            if include_library:
                queue.extend(path.parent / ref for ref in library)
        resources.append(path)
        queue.extend(referenced_paths(path, text))
    return tuple(resources)


def load_playbook(
    name: str, *, mode: Literal["case", "world", "range"] = "case", root: Path | None = None
) -> str:
    """Fail explicitly rather than silently substituting a generic or truncated playbook."""
    root = (root or repo_root()).resolve()
    if name not in RUNTIME_SKILLS:
        raise IntegrationBlocked("Not an operational runtime skill.")
    _, body = read_skill(name, root)
    base = root / ".claude/skills"
    paths: tuple[Path, ...]
    if mode == "range":
        paths = (base / RANGE_REFERENCE,)
        limit = MAX_WORLD_CHARS
    elif mode == "world":
        paths = (base / WORLD_REFERENCE,)
        limit = MAX_WORLD_CHARS
    elif mode == "case":
        paths = tuple(
            p
            for p in skill_resources(name, root=root, include_library=False)
            if p != base / name / "SKILL.md" and p != base / WORLD_REFERENCE
        )
        limit = MAX_CASE_CHARS
    else:
        raise IntegrationBlocked("Unknown skill execution mode.")
    parts = [body]
    for path in paths:
        text = read_markdown(path, root)
        if path.name == "SKILL.md":
            _, text = read_skill(path.parent.name, root)
        parts.append(f"\n\n--- Reference: {path.relative_to(base).as_posix()} ---\n{text.strip()}")
    result = "".join(parts)
    if len(result) > limit:
        raise IntegrationBlocked(f"Skill context exceeds the {mode} limit: {name}")
    return result
