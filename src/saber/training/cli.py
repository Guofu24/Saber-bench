"""Offline CLI for external practice. Never downloads content or contacts HTB."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import click

from saber.forensics.vault import FORMATS, display
from saber.training.catalog import TRACKS
from saber.training.practice import attach, initialize, load_manifest, report, write_new
from saber.world.models import Actor, WorldConfig


def emit(value: Any) -> None:
    click.echo(json.dumps(display(value), indent=2, ensure_ascii=True))


@click.group(help="SABER-authored HTB practice tracks and evidence review; no live HTB connector.")
def training() -> None:
    pass


@training.command("catalog")
@click.option("--team", type=click.Choice(["red", "blue", "purple"]))
def catalog(team: str | None) -> None:
    emit(
        {
            "authorship": "SABER; not official HTB content",
            "reviewed_at": "2026-11-05",
            "live_connector": False,
            "tracks": [t.model_dump() for t in TRACKS.values() if team is None or t.team == team],
        }
    )


@training.command("init")
@click.option("--track", "track_id", type=click.Choice(list(TRACKS)), required=True)
@click.option("--exercise", required=True, help="Local exercise slug, not an answer or flag.")
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--source-url", help="Public HTB content URL; metadata only, never fetched.")
@click.option("--synthetic", is_flag=True, help="Identify locally authored demo evidence.")
@click.option("--assisted", is_flag=True, help="Record walkthrough/prior-answer assistance.")
def init_practice(
    track_id: str,
    exercise: str,
    out: Path,
    source_url: str | None,
    synthetic: bool,
    assisted: bool,
) -> None:
    try:
        result = initialize(
            out, track_id, exercise, source_url, synthetic=synthetic, assisted=assisted
        )
    except (ValueError, OSError):
        raise click.ClickException(
            "Cannot initialize: use a new directory, valid slug and public HTB URL."
        ) from None
    emit(result.model_dump(mode="json"))


@training.command("attach")
@click.option("--run", "root", type=click.Path(path_type=Path, exists=True), required=True)
@click.option(
    "--file", "source", type=click.Path(path_type=Path, exists=True, dir_okay=False), required=True
)
@click.option("--format", "fmt", type=click.Choice(FORMATS), required=True)
@click.option("--label", required=True)
@click.option(
    "--rights-note",
    required=True,
    help="Record your basis for using this evidence; not a license override.",
)
@click.option(
    "--conversion-note",
    required=True,
    help="State original bytes or conversion tool/version, input/output hashes and losses.",
)
@click.option("--assume-offset", default=None)
def attach_evidence(
    root: Path,
    source: Path,
    fmt: str,
    label: str,
    rights_note: str,
    conversion_note: str,
    assume_offset: str | None,
) -> None:
    try:
        result = attach(root, source, fmt, label, rights_note, conversion_note, assume_offset)
    except (ValueError, OSError, sqlite3.Error):
        raise click.ClickException(
            "Attachment failed. Check metadata, supported UTF-8 format and vault limits; any incomplete receipt is retained for inspection."
        ) from None
    emit(result)


@training.command("prepare-world")
@click.option("--run", "root", type=click.Path(path_type=Path, exists=True), required=True)
def prepare_world(root: Path) -> None:
    """Create a blue-only local roster for imported evidence; never starts agents."""
    try:
        manifest = load_manifest(root)
        if manifest.track.team != "blue":
            raise ValueError("Only blue evidence tracks have an automatic local roster")
        folder = root / "world"
        if folder.is_symlink() or (folder / "world.sqlite3").exists():
            raise ValueError("Cannot replace a running world")
        goal = (
            f"Practice {manifest.exercise}: {manifest.track.title}. "
            "Consult external-practice guidance, then investigate imported forensic sources. "
            "Cite records, test alternatives and preserve uncertainty. Historical evidence cannot "
            "verify live containment. Finish partial where evidence is missing."
        )
        config = WorldConfig(
            actors=[
                Actor(id=f"blue-{role}", team="blue", role=role, goal=goal)
                for role in manifest.track.roles
            ],
            learning_enabled=False,
        )
        folder.mkdir(parents=True, exist_ok=True)
        write_new(folder / "config.json", config.model_dump(mode="json"))
    except (ValueError, OSError):
        raise click.ClickException(
            "Cannot prepare: use a blue track without an existing world config/runtime."
        ) from None
    emit(
        {
            "world": str(folder),
            "actors": [a.id for a in config.actors],
            "started": False,
            "learning_enabled": False,
        }
    )


@training.command("report")
@click.option("--run", "root", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--review", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    help="New report file; existing files are never overwritten.",
)
def report_practice(root: Path, review: Path | None, out: Path | None) -> None:
    try:
        result = report(root, review)
        if out:
            write_new(out, result)
    except (ValueError, OSError, sqlite3.Error):
        raise click.ClickException(
            "Cannot report: check the manifest, receipts, review IDs and output path."
        ) from None
    emit(result)
    if result["status"] == "INTEGRITY_FAILURE":
        raise click.ClickException("Evidence integrity or receipt validation failed.")
