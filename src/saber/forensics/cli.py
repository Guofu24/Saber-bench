"""Operator-only evidence ingestion; agents never receive filesystem paths."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import click

from saber.forensics.vault import FORMATS, Vault


def emit(value: Any) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, indent=2))


@click.group(
    "forensics",
    help="Import historical logs for blue investigations; --out is the world/controller data directory.",
)
def forensics_cli() -> None:
    pass


@forensics_cli.command("import")
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option(
    "--file", "source", type=click.Path(path_type=Path, exists=True, dir_okay=False), required=True
)
@click.option("--format", "fmt", type=click.Choice(FORMATS), required=True)
@click.option("--label", required=True)
@click.option(
    "--assume-offset",
    default=None,
    help="Explicit offset for naive timestamps, e.g. +07:00. Default: unknown timezone.",
)
def import_source(out: Path, source: Path, fmt: str, label: str, assume_offset: str | None) -> None:
    try:
        with Vault(out) as vault:
            emit(vault.import_file(source, fmt, label, assume_offset))
    except (OSError, ValueError, sqlite3.Error):
        raise click.ClickException(
            "Import failed: check format, encoding, size, vault budget and paths; input file is retained."
        ) from None


@forensics_cli.command("sources")
@click.option("--out", type=click.Path(path_type=Path, exists=True), required=True)
def sources(out: Path) -> None:
    with Vault(out) as vault:
        emit(vault.sources())


@forensics_cli.command("verify")
@click.option("--out", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--source", "source_id", required=True)
def verify(out: Path, source_id: str) -> None:
    try:
        with Vault(out) as vault:
            result = vault.verify(source_id)
            emit(result)
            if not result["integrity_verified"]:
                raise click.ClickException("Original hash mismatch")
    except (OSError, ValueError):
        raise click.ClickException("Cannot verify the requested source") from None


@forensics_cli.command("sessions")
@click.option("--out", type=click.Path(path_type=Path, exists=True), required=True)
def sessions(out: Path) -> None:
    with Vault(out) as vault:
        emit(
            [
                {
                    "actor": r["owner"],
                    **{
                        k: json.loads(r["data"])[k]
                        for k in ("id", "state", "question", "source_ids")
                    },
                }
                for r in vault.db.execute(
                    "SELECT owner,data FROM sessions ORDER BY rowid DESC LIMIT 256"
                )
            ]
        )


@forensics_cli.command("evidence")
@click.option("--out", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--id", "evidence_id", type=click.IntRange(1, 9223372036854775807), required=True)
@click.option(
    "--export",
    "destination",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the exact original record to a NEW file; contains unredacted evidence.",
)
def evidence(out: Path, evidence_id: int, destination: Path | None) -> None:
    try:
        with Vault(out) as vault:
            row = vault.db.execute("SELECT * FROM records WHERE id=?", (evidence_id,)).fetchone()
            if row is None:
                raise click.ClickException("Unknown evidence ID")
            result = vault.evidence(row)
            if destination is not None:
                import hashlib

                with vault.original(row["source"]).open("rb") as stream:
                    stream.seek(row["offset"])
                    raw = stream.read(row["length"])
                if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                    raise click.ClickException("Original record hash mismatch")
                with destination.open("xb") as output:
                    output.write(raw)
                result["original_exported"] = True
            emit(result)
    except (OSError, ValueError):
        raise click.ClickException(
            "Cannot read/export evidence; verify its integrity and choose a new output file."
        ) from None


@forensics_cli.command("inspect")
@click.option("--out", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--session", "session_id", required=True)
def inspect(out: Path, session_id: str) -> None:
    from saber.forensics.vault import display

    with Vault(out) as vault:
        row = vault.db.execute(
            "SELECT owner,data FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise click.ClickException("Unknown investigation")
        emit({"actor": row["owner"], **display(json.loads(row["data"]))})
