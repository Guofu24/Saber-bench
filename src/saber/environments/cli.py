"""Profile selection and lifecycle commands for operators."""

from __future__ import annotations

import json
import subprocess
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
@click.option("--tick-seconds", type=click.FloatRange(0.01, 3600), default=2.0, show_default=True)
def init_profile(
    profile: ProfileName, out: Path, name: str, clients: int, tick_seconds: float
) -> None:
    try:
        config = EnvironmentConfig(
            name=name,
            profile=profile,
            world=default_config(clients).model_copy(update={"tick_seconds": tick_seconds}),
        )
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


@env.command("render", help="Export a portable bundle without keys, local data or host changes.")
@click.option("--config", type=click.Path(path_type=Path), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
def render_profile(config: Path, out: Path) -> None:
    from saber.environments.bundle import render_bundle

    cfg = load(config)
    try:
        emit(render_bundle(cfg, out))
    except (OSError, ValueError):
        raise click.ClickException(
            "Could not export bundle; use a new destination and check public source files."
        ) from None


@env.command(
    "doctor",
    help="Inspect this host without changes; optionally probe explicitly approved service health URLs.",
)
@click.option("--config", type=click.Path(path_type=Path), required=True)
@click.option(
    "--probe-services",
    is_flag=True,
    help="GET only approved health URLs; no redirects or automatic service setup.",
)
def doctor_profile(config: Path, probe_services: bool) -> None:
    from saber.environments.diagnostics import doctor

    report = doctor(load(config), probe_services=probe_services)
    emit(report)
    if report["blockers"]:
        raise click.exceptions.Exit(1)


@env.command(
    "run",
    help="Run on THIS host. VM/remote profiles require --on-target in the guest/server terminal.",
)
@click.option("--config", type=click.Path(path_type=Path), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--ticks", type=click.IntRange(1), default=30, show_default=True)
@click.option("--forever", is_flag=True)
@click.option(
    "--on-target",
    is_flag=True,
    help="Acknowledge that this command runs on the intended VM/server.",
)
@click.option("--resume", is_flag=True)
@click.option("--llm", is_flag=True)
@click.option("--call-budget", type=click.IntRange(1), default=None)
@click.option("--key-pool", type=click.Path(path_type=Path), default=Path("keys_pool.txt"))
@click.option("--model", default="gemini-3.5-flash-lite", show_default=True)
@click.pass_context
def run_profile(
    ctx: click.Context,
    config: Path,
    out: Path,
    ticks: int,
    forever: bool,
    on_target: bool,
    resume: bool,
    llm: bool,
    call_budget: int | None,
    key_pool: Path,
    model: str,
) -> None:
    from saber.environments.lifecycle import prepare_world
    from saber.world.cli import run_world

    cfg = load(config)
    if cfg.profile == "sandbox":
        raise click.ClickException(
            "Use env render + env up for sandbox; no local fallback was started."
        )
    if cfg.profile in ("vm", "remote") and not on_target:
        raise click.ClickException(
            "Run this command inside the chosen guest/server with --on-target. No remote host is provisioned."
        )
    if llm != (call_budget is not None):
        raise click.ClickException("--llm and --call-budget must be supplied together.")
    try:
        prepare_world(cfg, out)
    except (OSError, ValueError, RuntimeError):
        raise click.ClickException(
            "Cannot prepare world: check configuration compatibility and runner lock."
        ) from None
    click.echo(f"Profile {cfg.profile}: executing on this host; application world only.")
    ctx.invoke(
        run_world,
        out=out,
        ticks=ticks,
        forever=forever,
        resume=resume,
        llm=llm,
        call_budget=call_budget,
        key_pool=key_pool,
        model=model,
    )


@env.command(
    "up", help="Build/start a sandbox bundle. Gemini egress/key mount requires explicit --llm."
)
@click.option("--bundle", type=click.Path(path_type=Path), required=True)
@click.option("--llm", is_flag=True)
@click.option("--call-budget", type=click.IntRange(1), default=None)
@click.option("--key-pool", type=click.Path(path_type=Path), default=None)
@click.option("--model", default="gemini-3.5-flash-lite", show_default=True)
@click.option("--resume", is_flag=True)
def up_profile(
    bundle: Path,
    llm: bool,
    call_budget: int | None,
    key_pool: Path | None,
    model: str,
    resume: bool,
) -> None:
    from saber.environments.lifecycle import sandbox_up

    try:
        sandbox_up(
            bundle, llm=llm, call_budget=call_budget, key_pool=key_pool, model=model, resume=resume
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        raise click.ClickException(
            "Sandbox start failed. Check bundle integrity, Linux engine, build access and explicit Gemini arguments. Raw diagnostics are redacted."
        ) from None
    emit(
        {
            "start_requested": True,
            "profile": "sandbox",
            "llm": llm,
            "note": "Use env status/report to verify the running worker and inference; startup is not proof of successful API calls.",
        }
    )


@env.command("down", help="Stop/remove this bundle's container. Preserve its named data volume.")
@click.option("--bundle", type=click.Path(path_type=Path), required=True)
def down_profile(bundle: Path) -> None:
    from saber.environments.lifecycle import sandbox_down

    try:
        sandbox_down(bundle)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise click.ClickException(
            "Could not stop sandbox; check the bundle and Docker engine."
        ) from None
    emit({"stopped": True, "data_volume": "preserved", "resume": "env up --bundle PATH --resume"})


@env.command("status", help="Read sandbox container status, including stopped containers.")
@click.option("--bundle", type=click.Path(path_type=Path), required=True)
def status_profile(bundle: Path) -> None:
    from saber.environments.lifecycle import sandbox_status

    try:
        click.echo(sandbox_status(bundle) or "No containers exist for this bundle.")
    except (OSError, ValueError, subprocess.SubprocessError):
        raise click.ClickException(
            "Cannot read sandbox status; check the bundle and Docker engine."
        ) from None


@env.command(
    "report", help="Copy the sandbox report to a new local file before removing its container."
)
@click.option("--bundle", type=click.Path(path_type=Path), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
def report_profile(bundle: Path, out: Path) -> None:
    from saber.environments.lifecycle import sandbox_report

    try:
        emit(sandbox_report(bundle, out))
    except (OSError, ValueError, subprocess.SubprocessError):
        raise click.ClickException(
            "Cannot export report. Use a new output path and an existing container with a report."
        ) from None
