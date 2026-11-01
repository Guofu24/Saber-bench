"""Portable, allowlisted source export and hardened application-world deployment."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml

from saber.catalog.loader import repo_root
from saber.environments.models import EnvironmentConfig
from saber.world.agents import PLAYBOOKS

DOCKERFILE = """# Dependency versions come from uv.lock; update image versions deliberately.
FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM python:3.12.12-slim-bookworm
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY . /app
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python \
    && mkdir -p /data && chown 10001:10001 /data
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/src" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
STOPSIGNAL SIGTERM
CMD ["python", "-m", "saber.environments.worker", "--config", "/config/environment.json", "--out", "/data"]
"""

BUNDLE_README = """# SABER environment bundle

This bundle runs the existing continuous APPLICATION lab. All client/red/blue actors
share one Python runtime. It does not provision per-actor desktops, drive browsers,
attack the guest OS, or install a SIEM/SOAR. See environment.json for the selected
deployment profile. Runtime labels remain DEV_SIMULATION_ONLY.

## Local / operator-built VM / remote lab server

For VM or remote profiles, first transfer this entire directory to your chosen
guest/server and open its terminal. No automatic SSH/provisioning takes place.
Use Python 3.12+ and uv already installed there. In the `source` directory:

    uv sync --frozen --no-dev
    uv run --no-sync saber env run --config ../environment.json --out ../world --ticks 30 --on-target
    uv run --no-sync saber env run --config ../environment.json --out ../world --forever --on-target

`--on-target` acknowledges that this terminal is on the intended guest/server.
For Gemini add `--llm --key-pool /path/on/this/host/keys_pool.txt --call-budget 200`.
Credentials are never included in this bundle. Transfer/provide them separately.
Stop from a second terminal with `saber world stop --out ../world` using this venv.
Use `--resume` explicitly after STOP. Data is in `world/`; back it up while stopped.

## Container sandbox

From a checkout/venv with SABER installed, substitute this bundle directory:

    saber env up --bundle PATH_TO_BUNDLE
    saber env status --bundle PATH_TO_BUNDLE
    saber env report --bundle PATH_TO_BUNDLE --out report.json
    saber env down --bundle PATH_TO_BUNDLE

The default container has no external network, host ports, or key mount. Its
loopback HTTP calls still work. To opt in to Gemini, use env up with --llm,
--key-pool PATH and --call-budget N. This selects the separate complete
compose.gemini.yaml manifest: outbound networking is enabled for the controller,
and the key file is a read-only secret mount. Egress is NOT domain-filtered.
It is not an appropriate container for executing arbitrary malware or shell tools.

Container data uses a named volume; `down` preserves it. `up --resume` resumes the
same volume after STOP. Do not run `down -v` unless intentionally deleting data.
Export a report before removing the container. No volumes are deleted by SABER.

CPU/RAM limits apply to the sandbox container only. Guest/server sizing is managed
by the operator. The image build needs registry/package access; scripted runtime
does not. Package dependencies are locked; images have explicit version tags.

`bundle-manifest.json` records exported file hashes and a unique Compose project
name. The env lifecycle verifies these hashes before launch. Edit the original
profile and render a NEW bundle to make changes; keep existing world data backed up.
"""


def compose_config(config: EnvironmentConfig, project: str, *, llm: bool = False) -> dict[str, Any]:
    service: dict[str, Any] = {
        "build": {"context": "./source"},
        "init": True,
        "user": "10001:10001",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "pids_limit": config.resources.pids,
        "mem_limit": f"{config.resources.memory_mb}m",
        "cpus": config.resources.cpus,
        "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m"],
        "volumes": ["world-data:/data", "./environment.json:/config/environment.json:ro"],
        "restart": "on-failure:3",
        "stop_grace_period": "80s",
        "environment": {"SABER_ENV_RESUME": "${SABER_ENV_RESUME:-0}"},
        "logging": {"driver": "json-file", "options": {"max-size": "5m", "max-file": "3"}},
    }
    doc: dict[str, Any] = {
        "name": project,
        "services": {"world": service},
        "volumes": {"world-data": {}},
    }
    if llm:
        service["networks"] = ["provider-egress"]
        service["secrets"] = ["gemini-pool"]
        service["environment"].update(
            {
                "SABER_ENV_LLM": "1",
                "SABER_ENV_CALL_BUDGET": "${SABER_ENV_CALL_BUDGET:?Set an explicit call budget}",
                "SABER_ENV_MODEL": "${SABER_ENV_MODEL:-gemini-3.5-flash-lite}",
            }
        )
        doc["networks"] = {"provider-egress": {"driver": "bridge"}}
        doc["secrets"] = {"gemini-pool": {"file": "${SABER_ENV_KEY_POOL:?Set the key file path}"}}
    else:
        service["network_mode"] = "none"
    return doc


def _copy_public(source: Path, target: Path, root: Path) -> None:
    if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
        raise ValueError("Source export refuses symlinks or files outside the project.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def render_bundle(
    config: EnvironmentConfig, out: Path, *, source_root: Path | None = None
) -> dict[str, Any]:
    root = source_root or repo_root()
    out = out.resolve()
    if out.exists():
        raise ValueError("Bundle destination already exists; use a new directory.")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".saber-bundle-", dir=out.parent) as temporary:
        stage = Path(temporary) / "bundle"
        source = stage / "source"
        source.mkdir(parents=True)
        # Never copy .git, .env, keys_pool, runs, private fixtures, or the user's venv.
        for name in ("pyproject.toml", "uv.lock", "catalog/subtasks.json"):
            _copy_public(root / name, source / name, root)
        for path in (root / "src" / "saber").rglob("*.py"):
            _copy_public(path, source / path.relative_to(root), root)
        for name in sorted(set(PLAYBOOKS.values())):
            relative = Path(".claude") / "skills" / name / "SKILL.md"
            if (root / relative).is_file():
                _copy_public(root / relative, source / relative, root)
        (source / "README.md").write_text("# SABER exported runtime\n", encoding="utf-8")
        (source / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
        (source / ".dockerignore").write_text(
            ".venv\n__pycache__\n*.pyc\n.env*\nkeys_pool*\n", encoding="utf-8"
        )
        (stage / "environment.json").write_text(
            config.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (stage / "README.md").write_text(BUNDLE_README, encoding="utf-8")
        project = f"{config.name}-{uuid.uuid4().hex[:10]}"
        if config.profile == "sandbox":
            for filename, llm in (("compose.yaml", False), ("compose.gemini.yaml", True)):
                (stage / filename).write_text(
                    yaml.safe_dump(compose_config(config, project, llm=llm), sort_keys=False),
                    encoding="utf-8",
                )
        revision = "unknown"
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                revision = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        hashes = {
            p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(stage.rglob("*"))
            if p.is_file()
        }
        manifest = {
            "schema_version": 1,
            "profile": config.profile,
            "project": project,
            "source_revision": revision,
            "source_note": "File hashes identify exported working-tree contents, including uncommitted changes.",
            "files": hashes,
        }
        (stage / "bundle-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        stage.rename(out)
    return {"bundle": str(out), "profile": config.profile, "project": project, "files": len(hashes)}


def verify_bundle(root: Path) -> EnvironmentConfig:
    root = root.resolve()
    manifest = json.loads((root / "bundle-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported bundle manifest.")
    required = {"environment.json", "source/pyproject.toml", "source/uv.lock", "source/Dockerfile"}
    if not required.issubset(manifest["files"]):
        raise ValueError("Incomplete bundle manifest.")
    for name, digest in manifest["files"].items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError("Invalid bundle file path.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Bundle contents changed; render a new bundle before launch.")
    config = EnvironmentConfig.model_validate_json(
        (root / "environment.json").read_text(encoding="utf-8")
    )
    if config.profile != manifest["profile"]:
        raise ValueError("Bundle profile mismatch.")
    if config.profile == "sandbox":
        for name, llm in (("compose.yaml", False), ("compose.gemini.yaml", True)):
            actual = yaml.safe_load((root / name).read_text(encoding="utf-8"))
            if actual != compose_config(config, manifest["project"], llm=llm):
                raise ValueError(
                    "Compose configuration differs from the supported sandbox profile."
                )
    return config
