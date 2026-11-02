"""Operator inspection and explicit reconciliation of durable playbooks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import click

from saber.lab.deployment import verify_bundle
from saber.lab.transport import request


def call(bundle: Path, job_id: str, body: Any = None) -> None:
    try:
        if not verify_bundle(bundle).soar.enabled or not re.fullmatch(r"[a-f0-9-]{32,36}", job_id):
            raise ValueError("Invalid SOAR configuration/job")
        auth = json.loads((bundle / ".secrets/soar.json").read_text())["operator_token"]
        code, result = request(
            "http://127.0.0.1:7793/jobs/" + job_id + ("/reconcile" if body else ""),
            token=auth,
            body=body,
        )
        if code != 200:
            raise ValueError("SOAR operation rejected")
        click.echo(json.dumps(result, indent=2))
    except (OSError, ValueError, ConnectionError):
        raise click.ClickException(
            "SOAR operation unavailable or invalid; credentials not printed"
        ) from None


@click.group("soar", help="Inspect playbook receipts and reconcile uncertain effects.")
def soar_cli() -> None:
    pass


@soar_cli.command("status")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--job-id", required=True)
def status(bundle: Path, job_id: str) -> None:
    call(bundle, job_id)


@soar_cli.command("reconcile")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--job-id", required=True)
@click.option(
    "--reason", required=True, help="Actual inspection performed and why case work may resume."
)
def reconcile(bundle: Path, job_id: str, reason: str) -> None:
    call(bundle, job_id, {"reason": reason})
