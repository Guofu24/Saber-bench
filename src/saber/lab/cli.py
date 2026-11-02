"""Operator lifecycle for portable SOC lab bundles."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import click

from saber.lab.deployment import initialize_secrets, render, verify_bundle
from saber.lab.models import LabSpec, preset_spec


def emit(value: Any) -> None:
    click.echo(json.dumps(value, indent=2, ensure_ascii=False))


@click.group(help="SOC lab presets, provisioning bundles and integration verification.")
def lab() -> None:
    pass


@lab.command("list")
def list_presets() -> None:
    for name in ("linux-small", "windows-ad", "expanded"):
        spec = preset_spec(name)
        emit(
            {
                "preset": name,
                "host_ram_gb": spec.host_ram_gb,
                "host_cpus": spec.host_cpus,
                "disk_gb": spec.disk_gb,
                "actors": len(spec.actors),
                "windows_guests": len(spec.windows),
                "runtime_verified": False,
            }
        )


@lab.command("init")
@click.option(
    "--preset", type=click.Choice(["linux-small", "windows-ad", "expanded"]), required=True
)
@click.option("--name", default="saber-soc")
@click.option("--out", type=click.Path(path_type=Path), required=True)
def init_lab(preset: Any, name: str, out: Path) -> None:
    try:
        spec = preset_spec(preset, name)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as stream:
            stream.write(spec.model_dump_json(indent=2))
    except (OSError, ValueError):
        raise click.ClickException(
            "Cannot initialize configuration; use a valid name and new file"
        ) from None
    emit({"created": str(out), "preset": preset})


@lab.command("render")
@click.option("--config", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
def render_lab(config: Path, out: Path) -> None:
    try:
        emit(render(LabSpec.model_validate_json(config.read_text(encoding="utf-8")), out))
    except (OSError, ValueError):
        raise click.ClickException(
            "Cannot render lab; inspect schema and choose a new directory"
        ) from None


@lab.command("credentials")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def credentials(bundle: Path) -> None:
    try:
        initialize_secrets(bundle, verify_bundle(bundle))
    except (OSError, ValueError):
        raise click.ClickException(
            "Cannot initialize credentials; bundle invalid or credentials already exist"
        ) from None
    emit({"created": str(bundle / ".secrets"), "values_printed": False})


@lab.command("validate")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def validate(bundle: Path) -> None:
    try:
        spec = verify_bundle(bundle)
    except (OSError, ValueError):
        raise click.ClickException("Invalid bundle or changed build context") from None
    emit(
        {
            "valid": True,
            "preset": spec.preset,
            "runtime_verified": False,
            "required_host": {
                "ram_gb": spec.host_ram_gb,
                "cpu": spec.host_cpus,
                "disk_gb": spec.disk_gb,
            },
        }
    )


def compose_command(bundle: Path, args: list[str]) -> None:
    try:
        verify_bundle(bundle)
        exe = shutil.which("docker")
        if not exe:
            raise ValueError("missing Docker")
        result = subprocess.run(
            [exe, "compose", "-f", str((bundle / "compose.yaml").resolve()), *args],
            capture_output=True,
            timeout=1800,
            check=False,
        )
        if result.returncode:
            raise ValueError("compose failed")
    except (OSError, ValueError, subprocess.SubprocessError):
        raise click.ClickException(
            "Compose operation failed. Check Docker, bundle and credentials on the target host. Diagnostics redacted."
        ) from None


@lab.command("up")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--on-target", is_flag=True, help="Confirm this is the isolated lab deployment host.")
def up(bundle: Path, on_target: bool) -> None:
    if not on_target:
        raise click.ClickException(
            "Run on the intended lab host with --on-target; no infrastructure started"
        )
    compose_command(bundle, ["up", "-d", "--build", "--wait", "--wait-timeout", "300"])
    emit({"started": True, "runtime_verified": False, "next": "saber lab verify --bundle PATH"})


@lab.command("down")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def down(bundle: Path) -> None:
    compose_command(bundle, ["down"])
    emit({"stopped": True, "volumes": "preserved"})


@lab.command("verify")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def verify(bundle: Path) -> None:
    from saber.lab.acceptance import verify_live

    try:
        result = verify_live(bundle)
    except (OSError, ValueError, ConnectionError):
        raise click.ClickException(
            "Live verification unavailable; start services on the target host first"
        ) from None
    emit(result)
    if not result["passed"]:
        raise click.exceptions.Exit(1)
