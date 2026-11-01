"""Profile selection and lifecycle commands for operators."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from saber.environments.models import EnvironmentConfig, ProfileName, read_config
from saber.environments.profiles import PROFILES, describe
from saber.world.models import default_config


def emit(value: Any) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, indent=2))


def load(path: Path) -> EnvironmentConfig:
    try:
        return read_config(path)
    except ValidationError as exc:
        # Pydantic's default exception includes input values, which may be secrets.
        locations = [".".join(str(x) for x in e["loc"]) for e in exc.errors(include_input=False)]
        raise click.ClickException(
            "Invalid configuration fields: " + ", ".join(locations)
        ) from None
    except (OSError, ValueError):
        raise click.ClickException("Cannot read environment configuration.") from None


@click.group("env", help="Choose local, sandbox, operator-built VM or remote-server deployment.")
def env() -> None:
    pass


@env.command(
    "list", help="Show deployment options and their actual scope; no discovery or changes."
)
def list_profiles() -> None:
    emit([describe(name) for name in PROFILES])


@env.command("init", help="Create a profile configuration. Does not install or start anything.")
@click.option("--profile", type=click.Choice(list(PROFILES)), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--name", default="saber-lab", show_default=True)
@click.option("--clients", type=click.IntRange(1, 100), default=4, show_default=True)
def init_profile(profile: ProfileName, out: Path, name: str, clients: int) -> None:
    try:
        config = EnvironmentConfig(name=name, profile=profile, world=default_config(clients))
    except ValidationError:
        raise click.ClickException(
            "Name must contain lowercase letters, digits and hyphens."
        ) from None
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("x", encoding="utf-8") as stream:
            stream.write(config.model_dump_json(indent=2) + "\n")
    except FileExistsError:
        raise click.ClickException(
            "Configuration already exists; choose a new --out path."
        ) from None
    emit({"created": str(out), "profile": profile, "actors": len(config.world.actors)})


@env.command(
    "validate", help="Validate configuration offline; this does not prove runtime isolation."
)
@click.option("--config", type=click.Path(path_type=Path), required=True)
def validate_profile(config: Path) -> None:
    cfg = load(config)
    emit({"valid": True, "name": cfg.name, "services": len(cfg.services), **describe(cfg.profile)})
