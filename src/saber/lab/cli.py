"""Operator lifecycle for portable SOC lab bundles."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import click

from saber.forensics.cli import forensics_cli
from saber.lab.analysis_cli import analysis_cli
from saber.lab.backup_cli import backup_cli
from saber.lab.deployment import initialize_secrets, render, verify_bundle
from saber.lab.models import LabSpec, preset_spec
from saber.lab.soar_cli import soar_cli
from saber.world.learning_cli import learning_cli


def emit(value: Any) -> None:
    click.echo(json.dumps(value, indent=2, ensure_ascii=False))


@click.group(help="SOC lab presets, provisioning bundles and integration verification.")
def lab() -> None:
    pass


lab.add_command(learning_cli)
lab.add_command(analysis_cli)
lab.add_command(soar_cli)
lab.add_command(backup_cli)
lab.add_command(forensics_cli)


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


@lab.command("doctor")
@click.option("--config", type=click.Path(path_type=Path, exists=True), required=True)
@click.option(
    "--storage", type=click.Path(path_type=Path, exists=True, file_okay=False), default="."
)
def doctor(config: Path, storage: Path) -> None:
    from saber.lab.doctor import inspect_host

    result = inspect_host(LabSpec.model_validate_json(config.read_text(encoding="utf-8")), storage)
    emit(result)
    if not result["ready_for_deployment"]:
        raise click.exceptions.Exit(1)


def compose_command(bundle: Path, args: list[str], settings: dict[str, Any] | None = None) -> str:
    try:
        verify_bundle(bundle)
        exe = shutil.which("docker")
        if not exe:
            raise ValueError("missing Docker")
        saved = bundle / "active.receipt.json"
        mode = (
            settings
            if settings is not None
            else json.loads(saved.read_text())
            if saved.exists()
            else {}
        )
        env = os.environ.copy()
        files = ["-f", str((bundle / "compose.yaml").resolve())]
        if mode.get("llm"):
            files += ["-f", str((bundle / "compose.gemini.yaml").resolve())]
            env.update(
                {
                    "SABER_GEMINI_POOL": mode["key_pool"],
                    "SABER_MODEL": mode["model"],
                    "SABER_CALL_BUDGET": str(mode["call_budget"]),
                }
            )
        result = subprocess.run(
            [exe, "compose", "--env-file", os.devnull, *files, *args],
            capture_output=True,
            timeout=1800,
            check=False,
            env=env,
        )
        if result.returncode:
            raise ValueError("compose failed")
        return result.stdout.decode("utf-8", errors="replace")
    except (OSError, ValueError, subprocess.SubprocessError):
        raise click.ClickException(
            "Compose operation failed. Check Docker, bundle and credentials on the target host. Diagnostics redacted."
        ) from None


@lab.command("up")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--on-target", is_flag=True, help="Confirm this is the isolated lab deployment host.")
@click.option(
    "--llm",
    is_flag=True,
    help="Enable Gemini only in the controller; enables its outbound network.",
)
@click.option("--key-pool", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--call-budget", type=click.IntRange(1), default=None)
@click.option("--model", type=str)
def up(
    bundle: Path,
    on_target: bool,
    llm: bool,
    key_pool: Path | None,
    call_budget: int | None,
    model: str | None,
) -> None:
    if not on_target:
        raise click.ClickException(
            "Run on the intended lab host with --on-target; no infrastructure started"
        )
    if llm and (key_pool is None or call_budget is None or not model):
        raise click.ClickException("--llm requires --key-pool, --call-budget and --model")
    if not llm and any(v is not None for v in (key_pool, call_budget, model)):
        raise click.ClickException("Provider options require --llm")
    settings = {
        "llm": llm,
        "key_pool": str(key_pool.resolve()) if key_pool else None,
        "call_budget": call_budget,
        "model": model,
    }
    spec = verify_bundle(bundle)
    if spec.soar.enabled and spec.soar.backend != "builtin":
        try:
            inspected = subprocess.run(
                ["docker", "network", "inspect", spec.soar.external_network],
                capture_output=True,
                check=True,
                timeout=15,
            )
            if not json.loads(inspected.stdout)[0].get("Internal"):
                raise ValueError("Network must be internal")
            credentials = json.loads((bundle / ".secrets/soar.json").read_text())
            if not credentials.get("external_token"):
                raise ValueError("SOAR service credential required")
        except (OSError, ValueError, subprocess.SubprocessError):
            raise click.ClickException(
                "External SOAR requires an existing Docker internal network and a configured private service credential"
            ) from None
    compose_command(bundle, ["config", "--quiet"], settings)
    # Save the selected topology before launching, so cleanup works after partial startup.
    (bundle / "active.receipt.json").write_text(json.dumps(settings), encoding="utf-8")
    compose_command(bundle, ["up", "-d", "--build", "--wait", "--wait-timeout", "300"], settings)
    emit({"started": True, "runtime_verified": False, "next": "saber lab verify --bundle PATH"})


@lab.command("down")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def down(bundle: Path) -> None:
    compose_command(bundle, ["down"])
    emit({"stopped": True, "volumes": "preserved"})


@lab.command("status")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def status(bundle: Path) -> None:
    raw = compose_command(bundle, ["ps", "--all", "--format", "json"]).strip()
    rows = (
        json.loads(raw)
        if raw.startswith("[")
        else [json.loads(line) for line in raw.splitlines() if line]
    )
    emit(
        {
            "services": [{k: row.get(k) for k in ("Service", "State", "Health")} for row in rows],
            "runtime_verified": False,
        }
    )


@lab.command("stop")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def stop(bundle: Path) -> None:
    compose_command(bundle, ["stop", "-t", "60", "controller"])
    emit({"controller": "stopped", "sensors": "still running", "state": "preserved"})


@lab.command("resume")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
def resume(bundle: Path) -> None:
    compose_command(bundle, ["start", "controller"])
    emit(
        {
            "controller": "started",
            "uncertain_jobs": "reconcile existing receipt; never blindly retry",
        }
    )


@lab.command("logs")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--host")
@click.option("--kind")
@click.option("--limit", type=click.IntRange(1, 1000), default=100)
@click.option("--cursor", help="JSON [timestamp,event_id] returned by the previous page")
def logs(bundle: Path, host: str | None, kind: str | None, limit: int, cursor: str | None) -> None:
    from saber.lab.transport import request

    verify_bundle(bundle)
    auth = json.loads((bundle / ".secrets/controller.json").read_text())["read_token"]
    try:
        body = {
            "host": host,
            "kind": kind,
            "limit": limit,
            "cursor": json.loads(cursor) if cursor else None,
        }
        code, result = request("http://127.0.0.1:7789/search", token=auth, body=body)
        if code != 200:
            raise ValueError("query rejected")
    except (ValueError, OSError, ConnectionError):
        raise click.ClickException(
            "Log query unavailable or invalid; no credentials printed"
        ) from None
    emit(result)


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


@lab.command("reconcile-guest")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--job-id", required=True)
@click.option(
    "--reason",
    required=True,
    help="Record the operator's guest inspection and why it is safe to resume.",
)
def reconcile_guest(bundle: Path, job_id: str, reason: str) -> None:
    """After manual inspection, release an actor paused on an uncertain Windows job."""
    import re

    from saber.lab.transport import request

    try:
        verify_bundle(bundle)
        if not re.fullmatch(r"[a-f0-9-]{32,36}", job_id) or not 20 <= len(reason) <= 1000:
            raise ValueError("Invalid reconciliation")
        auth = json.loads((bundle / ".secrets/relay.json").read_text())["relay_token"]
        code, result = request(
            "http://127.0.0.1:7789/relay/work/" + job_id + "/reconcile",
            token=auth,
            body={"reason": reason},
        )
        if code != 200:
            raise ValueError("Reconciliation rejected")
    except (OSError, ValueError, ConnectionError):
        raise click.ClickException(
            "Guest reconciliation unavailable or invalid; no credentials printed"
        ) from None
    emit(result)
