"""Bounded lifecycle operations; normal shutdown never removes world data."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from saber.environments.bundle import verify_bundle
from saber.environments.models import EnvironmentConfig
from saber.world.models import WorldConfig
from saber.world.runtime import WorldLock, atomic_json


def prepare_world(config: EnvironmentConfig, out: Path) -> None:
    with WorldLock(out):
        path = out / "config.json"
        if path.exists():
            previous = WorldConfig.model_validate_json(path.read_text(encoding="utf-8"))
            if previous != config.world:
                raise ValueError("World configuration differs. Use a new data directory.")
        elif (out / "world.sqlite3").exists():
            raise ValueError(
                "Existing world database has no config; restore its configuration first."
            )
        else:
            atomic_json(path, config.world.model_dump(mode="json"))
        atomic_json(
            out / "deployment.json",
            {
                "selected_profile": config.profile,
                "name": config.name,
                "runtime": "application_world",
                "services_are_health_inventory_only": True,
            },
        )


def compose_command(bundle: Path) -> list[str]:
    config = verify_bundle(bundle)
    if config.profile != "sandbox":
        raise ValueError("Container lifecycle requires a sandbox bundle.")
    docker = shutil.which("docker")
    if docker is None:
        raise ValueError("Docker CLI is unavailable. No runtime was started.")
    return [
        docker,
        "compose",
        "--project-directory",
        str(bundle.resolve()),
        "-f",
        str(bundle.resolve() / "compose.yaml"),
    ]


def invoke(argv: list[str], *, timeout: float = 30, extra_env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        argv,
        env=os.environ | (extra_env or {}),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        # Do not echo raw Docker/build/provider output or environment variables.
        raise ValueError(
            "Docker command failed. Check the engine, image build and bundle; no secret output is echoed."
        )
    return result.stdout.strip()


def sandbox_up(
    bundle: Path,
    *,
    llm: bool = False,
    call_budget: int | None = None,
    key_pool: Path | None = None,
    model: str = "gemini-3.5-flash-lite",
    resume: bool = False,
) -> None:
    if llm != (call_budget is not None) or (call_budget is not None and call_budget <= 0):
        raise ValueError("Gemini requires --llm and a positive --call-budget together.")
    if llm and (key_pool is None or not key_pool.is_file()):
        raise ValueError("Provide an existing --key-pool file for Gemini.")
    command = compose_command(bundle)
    if invoke([command[0], "info", "--format", "{{.OSType}}"], timeout=10) != "linux":
        raise ValueError("A running Linux Docker engine is required.")
    environment = {"SABER_ENV_RESUME": "1" if resume else "0"}
    if llm:
        command[-1] = str(bundle.resolve() / "compose.gemini.yaml")
        assert key_pool is not None
        environment.update(
            SABER_ENV_KEY_POOL=key_pool.resolve().as_posix(),
            SABER_ENV_CALL_BUDGET=str(call_budget),
            SABER_ENV_MODEL=model,
        )
    invoke(command + ["up", "-d", "--build"], timeout=900, extra_env=environment)


def sandbox_down(bundle: Path) -> None:
    invoke(compose_command(bundle) + ["down", "--timeout", "80"], timeout=120)


def sandbox_status(bundle: Path) -> str:
    return invoke(compose_command(bundle) + ["ps", "--all", "--format", "json"])


def sandbox_report(bundle: Path, out: Path) -> dict[str, Any]:
    if out.exists():
        raise ValueError("Report destination exists; choose a new file.")
    command = compose_command(bundle)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".saber-report-", dir=out.parent) as temporary:
        path = Path(temporary) / "report.json"
        invoke(command + ["cp", "world:/data/report.json", str(path)])
        if path.stat().st_size > 2_000_000:
            raise ValueError("Unexpected report size.")
        report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        with out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return {"report": str(out), "tick": report.get("tick"), "llm": report.get("llm", {})}
