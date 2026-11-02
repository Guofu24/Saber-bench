"""Operator controls for learning data; actors cannot install tests or publish skills."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click

from saber.world import learning
from saber.world.environment import World
from saber.world.learning_eval import ReplaySuite, install_suite, rollback
from saber.world.models import WorldConfig
from saber.world.runtime import WorldLock
from saber.world.store import Store


@contextmanager
def saved_world(out: Path) -> Iterator[World]:
    if not (out / "world.sqlite3").is_file():
        raise click.ClickException("No saved world at this directory.")
    try:
        with WorldLock(out):
            store = Store(out)
            try:
                spec = store.get("lab", "spec")
                if spec:
                    from saber.lab.learning import LearningWorld
                    from saber.lab.models import LabSpec

                    yield LearningWorld(store, LabSpec.model_validate(spec))
                else:
                    cfg = WorldConfig.model_validate_json(
                        (out / "config.json").read_text(encoding="utf-8")
                    )
                    yield World(store, cfg)
            finally:
                store.close()
    except (OSError, ValueError, RuntimeError) as exc:
        # Validation errors may contain submitted text; do not echo it into logs.
        raise click.ClickException(
            f"Learning operation failed ({type(exc).__name__}); check schema, IDs and stopped-world lock."
        ) from None


def output(value: Any) -> None:
    click.echo(json.dumps(value, indent=2, ensure_ascii=False))


@click.group(
    "learning",
    help="Inspect experience, install operator replay suites, export proposals and roll back local skills.",
)
def learning_cli() -> None:
    pass


@learning_cli.command(
    "status", help="Read counters from the last runtime snapshot; works while the world runs."
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
def status(out: Path) -> None:
    try:
        output(json.loads((out / "learning.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        raise click.ClickException(
            "No learning snapshot. Run/resume this world with current code."
        ) from None


@learning_cli.command(
    "install-suite",
    help="Register trusted next-action checks in a stopped world. Never runs code from the file.",
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option(
    "--file",
    "suite_file",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    required=True,
)
def suite_install(out: Path, suite_file: Path) -> None:
    with saved_world(out) as world:
        if suite_file.stat().st_size > 256000:
            raise ValueError("Suite too large")
        suite = ReplaySuite.model_validate_json(suite_file.read_text(encoding="utf-8"))
        sid = install_suite(world.store, suite.model_dump(mode="json"))
        output(
            {
                "suite_id": sid,
                "skill": suite.skill,
                "max_model_calls_per_evaluation": 2 * len(suite.cases) * suite.repetitions,
            }
        )


@learning_cli.command(
    "list",
    help="List proposal IDs and state without dumping journals or model text. Requires a stopped world.",
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
def proposals(out: Path) -> None:
    with saved_world(out) as world:
        output(
            {
                "summary": learning.summary(world.store),
                "episodes": [
                    {
                        k: e.get(k)
                        for k in (
                            "id",
                            "actor_id",
                            "team",
                            "skill",
                            "status",
                            "reason",
                            "attempts",
                            "error_kind",
                        )
                    }
                    for e in world.store.items("learning-episodes").values()
                ],
                "proposals": [
                    {
                        k: p.get(k)
                        for k in (
                            "id",
                            "actor_id",
                            "team",
                            "skill",
                            "status",
                            "evaluation_id",
                            "published_version",
                            "error_kind",
                        )
                    }
                    for p in world.store.items("learning-proposals").values()
                ],
            }
        )


@learning_cli.command(
    "inspect",
    help="Inspect one proposal and its replay results in a stopped world; operator-only text.",
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--proposal", "proposal_id", required=True)
def inspect(out: Path, proposal_id: str) -> None:
    with saved_world(out) as world:
        proposal = world.store.get("learning-proposals", proposal_id)
        if proposal is None:
            raise ValueError("Unknown proposal")
        output(
            {
                "proposal": proposal,
                "evaluation": world.store.get(
                    "learning-evaluations", proposal.get("evaluation_id", "")
                ),
            }
        )


@learning_cli.command(
    "export",
    help="Write a concrete proposal as Markdown for review/version control; never changes the source skill.",
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--proposal", "proposal_id", required=True)
@click.option("--file", "target", type=click.Path(path_type=Path, dir_okay=False), required=True)
def export(out: Path, proposal_id: str, target: Path) -> None:
    with saved_world(out) as world:
        p = world.store.get("learning-proposals", proposal_id)
        if p is None:
            raise ValueError("Unknown proposal")
        note = p["lesson"]
        text = (
            f"# Proposed extension: {p['skill']}\n\n"
            f"Status: `{p['status']}`\n\nBase version: `{p['base_version']}`\n\n"
            f"Proposal: `{p['id']}`\n\n"
            f"Applies when: {note['applicability']}\n\n{note['guidance']}\n\n"
            f"Limits: {note['limitations']}\n\n"
            "Scope: local development learning. Decision replay does not certify full SOC behavior.\n"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    click.echo(f"Wrote proposal to {target}.")


@learning_cli.command(
    "versions", help="List immutable skill versions and active/released IDs in a stopped world."
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--skill", required=True)
def versions(out: Path, skill: str) -> None:
    with saved_world(out) as world:
        active = learning.prompt_version(world.store, skill)
        output(
            {
                "skill": skill,
                "released": world.store.get("skill-heads", skill),
                "active": active["id"] if active else None,
                "versions": [
                    {"id": v["id"], "parent": v["parent"], "lessons": len(v["lessons"])}
                    for v in world.store.items("skill-versions").values()
                    if v["skill"] == skill
                ],
            }
        )


@learning_cli.command(
    "rollback",
    help="Select a previously released skill for the next safe epoch; retain active case pins.",
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--skill", required=True)
@click.option("--version", "version_id", required=True)
def rollback_version(out: Path, skill: str, version_id: str) -> None:
    with saved_world(out) as world:
        rollback(world.store, skill, version_id)
    click.echo("Release head restored. Active cases keep their pinned version until a safe epoch.")


@learning_cli.command(
    "retry",
    help="Explicitly retry one deferred reflection/evaluation after fixing quota, data or provider issues.",
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--kind", type=click.Choice(["episode", "proposal"]), required=True)
@click.option("--id", "record_id", required=True)
def retry(out: Path, kind: str, record_id: str) -> None:
    with saved_world(out) as world:
        space = "learning-episodes" if kind == "episode" else "learning-proposals"
        with world.store.transaction():
            row = world.store.get(space, record_id)
            if not row or row["status"] != "DEFERRED":
                raise ValueError("Only deferred work can be retried")
            row.setdefault("retry_history", []).append(
                {"tick": world.tick, "error_kind": row.get("error_kind")}
            )
            row.update(status="PENDING" if kind == "episode" else "AWAITING_SUITE", attempts=0)
            row.pop("evaluation_started", None)
            world.store.put(space, record_id, row)
    click.echo("Queued one retry; provider budget and team pool are unchanged.")
