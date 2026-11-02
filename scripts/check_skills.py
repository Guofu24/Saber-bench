"""Offline validation of repository skills, resource links and runtime prompt wiring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from saber.agents.skills import (
    MD_REFERENCE,
    RUNTIME_SKILLS,
    RANGE_REFERENCE,
    load_playbook,
    read_skill,
    skill_resources,
)
from saber.catalog.loader import repo_root
from saber.domain.errors import IntegrationBlocked
from saber.world.agents import PLAYBOOKS
from saber.world.models import BLUE_ROLES, RED_ROLES


def audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    base = root / ".claude/skills"
    errors: list[str] = []
    rows = []
    resources: set[Path] = set()
    entries = sorted(base.glob("*/SKILL.md"))
    names = {p.parent.name for p in entries}
    for name in sorted(RUNTIME_SKILLS - names):
        errors.append(f"Missing operational skill: {name}")
    for path in entries:
        name = path.parent.name
        try:
            metadata, body = read_skill(name, root)
            runtime = name in RUNTIME_SKILLS
            row: dict[str, Any] = {
                "name": name,
                "kind": "operational" if runtime else "development",
                "manual_only": metadata.get("disable-model-invocation", False),
            }
            if runtime:
                paths = skill_resources(name, root=root)
                resources.update(paths)
                row.update(
                    resources=len(paths),
                    case_chars=len(load_playbook(name, root=root)),
                    world_chars=len(load_playbook(name, mode="world", root=root)),
                    range_chars=len(load_playbook(name, mode="range", root=root)),
                )
                resources.add((base / RANGE_REFERENCE).resolve())
            else:
                # Development instructions intentionally refer to repository-root docs/tasks.
                for ref in MD_REFERENCE.findall(body):
                    target = path.parent / ref
                    if not target.is_file():
                        target = root / ref
                    if not target.resolve().is_relative_to(root) or not target.is_file():
                        raise IntegrationBlocked(f"Missing development reference: {ref}")
            rows.append(row)
        except IntegrationBlocked as exc:
            errors.append(f"{name}: {exc}")
    for name in RUNTIME_SKILLS & names:
        for resource in (base / name).rglob("*.md"):
            if resource.resolve() not in resources:
                errors.append(f"Unreferenced operational document: {resource.relative_to(base)}")
    expected_roles = {"client", *BLUE_ROLES, *RED_ROLES}
    if set(PLAYBOOKS) != expected_roles or set(PLAYBOOKS.values()) != RUNTIME_SKILLS:
        errors.append("World role-to-skill coverage differs from the runtime model.")
    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "scope": "offline structure, declared references, context limits and role wiring",
        "skill_count": len(entries),
        "operational_skill_count": len(RUNTIME_SKILLS & names),
        "reference_count": sum(p.name != "SKILL.md" for p in resources),
        "world_roles": PLAYBOOKS,
        "skills": rows,
        "errors": sorted(errors),
        "limitations": "No provider calls; not an evaluation of model judgment or external tool integration.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=repo_root())
    parser.add_argument("--out", type=Path, help="Optional JSON audit artifact")
    args = parser.parse_args()
    report = audit(args.root)
    encoded = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
