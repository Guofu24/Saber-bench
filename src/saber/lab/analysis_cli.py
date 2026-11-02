"""Operator tools for registering synthetic samples and checking analyzer receipts."""

from __future__ import annotations

import http.client
import json
import uuid
from pathlib import Path
from typing import Any

import click

from saber.lab.analyzers import ENGINES, PLUGIN, file_hash
from saber.lab.deployment import verify_bundle
from saber.lab.transport import request


def token(bundle: Path) -> str:
    if not verify_bundle(bundle).analysis.enabled:
        raise ValueError("Analysis is disabled in this bundle")
    return str(json.loads((bundle / ".secrets/analysis.json").read_text())["upload_token"])


def call(bundle: Path, route: str, body: Any = None) -> None:
    try:
        code, result = request("http://127.0.0.1:7792" + route, token=token(bundle), body=body)
        if code != 200:
            raise ValueError("Analysis request rejected")
        click.echo(json.dumps(result, indent=2))
    except (OSError, ValueError, ConnectionError):
        raise click.ClickException(
            "Analysis service unavailable or request invalid; credentials not printed"
        ) from None


@click.group("analysis", help="Register lab samples, inspect tools and run fixed offline analysis.")
def analysis_cli() -> None:
    pass


@analysis_cli.command("tools")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def tools(bundle: Path) -> None:
    call(bundle, "/tools")


@analysis_cli.command("samples")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def samples(bundle: Path) -> None:
    call(bundle, "/samples")


@analysis_cli.command("import")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option(
    "--file", "sample", type=click.Path(path_type=Path, exists=True, dir_okay=False), required=True
)
@click.option("--kind", type=click.Choice(["binary", "memory", "pcap"]), required=True)
def import_sample(bundle: Path, sample: Path, kind: str) -> None:
    try:
        auth = token(bundle)
        if (
            sample.is_symlink()
            or sample.name.lower().startswith(("keys_pool", ".env"))
            or ".secrets" in sample.parts
        ):
            raise ValueError("Expected an explicit lab sample")
        digest = file_hash(sample)
        connection = http.client.HTTPConnection("127.0.0.1", 7792, timeout=120)
        try:
            with sample.open("rb") as stream:
                connection.request(
                    "POST",
                    "/samples/" + digest,
                    body=stream,
                    headers={
                        "Authorization": "Bearer " + auth,
                        "X-Saber-Kind": kind,
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(sample.stat().st_size),
                    },
                )
            response = connection.getresponse()
            body = response.read(65537)
            if response.status != 200 or len(body) > 65536:
                raise ValueError("Sample upload rejected")
            click.echo(json.dumps(json.loads(body), indent=2))
        finally:
            connection.close()
    except (OSError, ValueError, http.client.HTTPException):
        raise click.ClickException(
            "Sample registration failed; inspect type, checksum and storage limits"
        ) from None


@analysis_cli.command("run")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--sample", required=True)
@click.option("--engine", type=click.Choice(ENGINES), required=True)
@click.option("--profile", type=click.Choice(["default", *PLUGIN]), default="default")
def run(bundle: Path, sample: str, engine: str, profile: str) -> None:
    call(
        bundle,
        "/jobs",
        {"id": str(uuid.uuid4()), "sample_id": sample, "engine": engine, "profile": profile},
    )


@analysis_cli.command("status")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--job-id", required=True)
def status(bundle: Path, job_id: str) -> None:
    import re

    if not re.fullmatch(r"[a-f0-9-]{32,36}", job_id):
        raise click.ClickException("Invalid job ID")
    call(bundle, "/jobs/" + job_id)
