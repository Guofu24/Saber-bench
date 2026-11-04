"""Render complete source bundles without installing or starting infrastructure."""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
from pathlib import Path
from typing import Any

import yaml

from saber.catalog.loader import repo_root
from saber.lab.models import LabSpec


def principal(actor_id: str) -> str:
    return "acct-" + hashlib.sha256(actor_id.encode()).hexdigest()[:12]


def compose(spec: LabSpec) -> dict[str, Any]:
    services: dict[str, Any] = {}
    volumes: dict[str, Any] = {}
    secret_names = ["app", "controller", "collector", "client", "red", "blue", "network"]

    def service(name: str, role: str, networks: list[str], memory: str = "512m") -> dict[str, Any]:
        volumes[name] = {}
        config: dict[str, Any] = {
            "image": f"saber/{spec.name}-{name}:local",
            "build": {
                "context": "./source",
                "dockerfile": "Dockerfile.worker" if role == "worker" else "Dockerfile",
            },
            "command": [
                "python",
                "-m",
                "saber.lab.service",
                "--role",
                role,
                "--data",
                "/data",
                "--spec",
                "/config/lab.json",
            ],
            "init": True,
            "user": "10001:10001",
            "read_only": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "pids_limit": 256,
            "mem_limit": memory,
            "cpus": 2,
            "tmpfs": ["/tmp:rw,nosuid,size=256m"],
            "networks": networks,
            "volumes": [f"{name}:/data", "./lab.json:/config/lab.json:ro"],
            "restart": "unless-stopped",
            "stop_grace_period": "45s",
            "environment": {"SABER_LAB_ROLE": name, "PYTHONDONTWRITEBYTECODE": "1"},
            "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}},
            "healthcheck": {
                "test": [
                    "CMD",
                    "python",
                    "-c",
                    "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2))['ok']",
                ],
                "interval": "15s",
                "timeout": "3s",
                "retries": 5,
            },
        }
        services[name] = config
        return config

    app = service("app", "app", ["business", "telemetry"])
    app["secrets"] = ["app"]
    app["environment"]["SABER_COLLECTOR"] = "http://collector:8080"
    app["depends_on"] = {"collector": {"condition": "service_healthy"}}
    collector = service("collector", "collector", ["telemetry", "soc"], "1g")
    collector["secrets"] = ["collector"]
    collector["environment"]["SABER_INDEXER"] = "http://indexer:9200"
    collector["ports"] = ["127.0.0.1:7789:8080"]
    for team in ("client", "red", "blue"):
        worker = service(team, "worker", ["business", "telemetry", "control"], "2g")
        worker["secrets"] = [team]
        worker["environment"].update(
            {
                "SABER_TEAM": team,
                "SABER_APP": "http://app:8080",
                "SABER_COLLECTOR": "http://collector:8080",
            }
        )
        worker["shm_size"] = "256m"
        worker["deploy"] = {"replicas": spec.workers_per_team}
        worker["depends_on"] = {
            "app": {"condition": "service_healthy"},
            "collector": {"condition": "service_healthy"},
        }
    controller = service("controller", "controller", ["control", "telemetry"], "1g")
    controller["secrets"] = ["controller"]
    controller["volumes"].append("./learning:/config/learning:ro")
    controller["depends_on"] = {
        team: {"condition": "service_healthy"} for team in ("client", "red", "blue")
    }
    controller["environment"].update(
        {
            "SABER_CLIENT": "http://client:8080",
            "SABER_RED": "http://red:8080",
            "SABER_BLUE": "http://blue:8080",
            "SABER_COLLECTOR": "http://collector:8080",
        }
    )
    if spec.soar.enabled:
        gateway = service("soar", "soar", ["business", "telemetry", "soar"])
        gateway["secrets"] = ["soar"]
        gateway["ports"] = ["127.0.0.1:7793:8080"]
        if spec.soar.backend != "builtin":
            gateway["networks"].append("integration")
        services["blue"]["networks"].append("soar")
        services["blue"]["depends_on"]["soar"] = {"condition": "service_healthy"}
        secret_names.append("soar")
    if spec.analysis.enabled:
        analysis = service(
            "analysis", "analysis", ["analysis", "telemetry"], f"{spec.analysis.memory_gb}g"
        )
        analysis["build"]["dockerfile"] = "Dockerfile.analysis"
        analysis["secrets"] = ["analysis"]
        analysis["ports"] = ["127.0.0.1:7792:8080"]
        analysis["volumes"] += ["./analysis:/config/analysis:ro", "./tools:/opt/tools:ro"]
        analysis["environment"]["SABER_COLLECTOR"] = "http://collector:8080"
        services["blue"]["networks"].append("analysis")
        services["blue"]["depends_on"]["analysis"] = {"condition": "service_healthy"}
        secret_names.append("analysis")
    services["indexer"] = {
        "image": f"opensearchproject/opensearch:{spec.opensearch_version}",
        "environment": {
            "discovery.type": "single-node",
            "OPENSEARCH_JAVA_OPTS": "-Xms2g -Xmx2g",
            "DISABLE_INSTALL_DEMO_CONFIG": "true",
            "DISABLE_SECURITY_PLUGIN": "true",
        },
        "ulimits": {"nofile": {"soft": 65536, "hard": 65536}},
        "mem_limit": "4g",
        "cpus": 4,
        "pids_limit": 512,
        "networks": ["soc"],
        "volumes": ["indexer:/usr/share/opensearch/data"],
        "restart": "unless-stopped",
        "healthcheck": {
            "test": ["CMD", "curl", "-fsS", "http://localhost:9200/_cluster/health"],
            "interval": "20s",
            "timeout": "5s",
            "retries": 12,
        },
    }
    volumes["indexer"] = {}
    volumes["network-logs"] = {}
    services["network-sensor"] = {
        "image": "zeek/zeek:8.0.11",
        "entrypoint": ["/usr/local/zeek/bin/zeek"],
        "command": ["-C", "-i", "any", "/config/local.zeek"],
        "working_dir": "/logs",
        "network_mode": "service:app",
        "depends_on": ["app"],
        "cap_drop": ["ALL"],
        "cap_add": ["NET_RAW", "NET_ADMIN"],
        "security_opt": ["no-new-privileges:true"],
        "read_only": True,
        "volumes": ["network-logs:/logs", "./sensors/local.zeek:/config/local.zeek:ro"],
        "tmpfs": ["/tmp:rw,nosuid,size=64m"],
        "mem_limit": "1g",
        "cpus": 2,
        "pids_limit": 64,
        "restart": "unless-stopped",
    }
    shipper = service("network", "collector", ["telemetry"], "512m")
    shipper["command"] = [
        "python",
        "-m",
        "saber.lab.logship",
        "--source",
        "zeek",
        "--logs",
        "/logs",
        "--data",
        "/data",
        "--credentials",
        "/run/secrets/network",
        "--collector",
        "http://collector:8080",
        "--host",
        "network",
    ]
    shipper["volumes"].append("network-logs:/logs:ro")
    shipper["secrets"] = ["network"]
    shipper.pop("healthcheck")
    services["dashboards"] = {
        "image": f"opensearchproject/opensearch-dashboards:{spec.opensearch_version}",
        "environment": {
            "OPENSEARCH_HOSTS": '["http://indexer:9200"]',
            "DISABLE_SECURITY_DASHBOARDS_PLUGIN": "true",
        },
        "networks": ["soc"],
        "ports": ["127.0.0.1:5601:5601"],
        "mem_limit": "1g",
        "cpus": 2,
        "pids_limit": 256,
        "restart": "unless-stopped",
    }
    services["office"] = {
        "image": "node:22.16.0-bookworm-slim",
        "user": "1000:1000",
        "read_only": True,
        "working_dir": "/viewer",
        "command": [
            "node",
            "bin/agent-office.js",
            "watch",
            "--world",
            "/world",
            "--port",
            "7788",
            "--listen",
            "0.0.0.0",
        ],
        "volumes": ["./agent-office:/viewer:ro", "controller:/world:ro"],
        "networks": ["control"],
        "ports": ["127.0.0.1:7788:7788"],
        "mem_limit": "256m",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "pids_limit": 64,
        "restart": "unless-stopped",
    }
    return {
        "name": spec.name,
        "services": services,
        "volumes": volumes,
        "networks": {
            **{
                n: {"internal": True}
                for n in ("business", "telemetry", "control", "soc", "analysis", "soar")
            },
            **(
                {"integration": {"external": True, "name": spec.soar.external_network}}
                if spec.soar.enabled and spec.soar.backend != "builtin"
                else {}
            ),
        },
        "secrets": {n: {"file": f"./.secrets/{n}.json"} for n in secret_names},
    }


def initialize_secrets(bundle: Path, spec: LabSpec) -> None:
    folder = bundle / ".secrets"
    if folder.exists():
        raise ValueError("Secrets already exist; never rotate credentials implicitly")
    folder.mkdir(mode=0o700)
    accounts = {
        principal(a.id): {
            "token": secrets.token_urlsafe(32),
            "team": a.team,
            "role": a.role,
            "actor_id": a.id,
            "specialties": list(a.specialties),
        }
        for a in spec.actors
    }
    read_token = secrets.token_urlsafe(32)
    response_token = secrets.token_urlsafe(32)
    soar_app_token = secrets.token_urlsafe(32)
    relay_token = secrets.token_urlsafe(32)
    rpc_tokens = {t: secrets.token_urlsafe(32) for t in ("client", "red", "blue")}
    actor_tokens = {a.id: secrets.token_urlsafe(32) for a in spec.actors}
    ingestion = {
        n: secrets.token_urlsafe(32)
        for n in (
            "app",
            "client",
            "red",
            "blue",
            "network",
            "linux-audit",
            "analysis",
            "soar",
            *[w.name for w in spec.windows],
        )
    }
    configs: dict[str, Any] = {
        "network": {"ingest_token": ingestion["network"]},
        "linux-audit": {"ingest_token": ingestion["linux-audit"]},
        "app": {
            "accounts": accounts,
            "ingest_token": ingestion["app"],
            "soar_response_token": soar_app_token,
        },
        "controller": {"workers": rpc_tokens, "read_token": read_token},
        "collector": {
            "sources": ingestion,
            "read_token": read_token,
            "response_token": response_token,
            "relay_token": relay_token,
            "windows_sources": [w.name for w in spec.windows],
            "windows_nodes": [w.model_dump() for w in spec.windows],
            "actor_capabilities": {
                actor_tokens[a.id]: {
                    "actor": a.id,
                    "team": a.team,
                    "role": a.role,
                    "specialties": list(a.specialties),
                }
                for a in spec.actors
            },
        },
        "relay": {
            "relay_token": relay_token,
            "sources": {w.name: ingestion[w.name] for w in spec.windows},
        },
        "analysis": {
            "upload_token": secrets.token_urlsafe(32),
            "ingest_token": ingestion["analysis"],
            "actor_capabilities": {
                actor_tokens[a.id]: {
                    "actor": a.id,
                    "team": a.team,
                    "role": a.role,
                    "specialties": list(a.specialties),
                }
                for a in spec.actors
                if a.team == "blue"
            },
        },
    }
    configs["soar"] = {
        "operator_token": secrets.token_urlsafe(32),
        "callback_token": secrets.token_urlsafe(32),
        "external_token": "",
        "app_token": soar_app_token,
        "read_token": read_token,
        "ingest_token": ingestion["soar"],
        "actor_capabilities": configs["analysis"]["actor_capabilities"],
    }
    for team in ("client", "red", "blue"):
        configs[team] = {
            "windows_nodes": [w.model_dump() for w in spec.windows],
            "actor_capabilities": {a.id: actor_tokens[a.id] for a in spec.actors if a.team == team},
            "accounts": {p: a for p, a in accounts.items() if a["team"] == team},
            "read_token": read_token if team == "blue" else "",
            "rpc_token": rpc_tokens[team],
            "ingest_token": ingestion[team],
            "response_token": response_token if team == "blue" else "",
            "soar_url": "http://soar:8080" if team == "blue" and spec.soar.enabled else "",
            "analysis_url": "http://analysis:8080"
            if team == "blue" and spec.analysis.enabled
            else "",
        }
    for name, value in configs.items():
        path = folder / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        # The private parent directory is 0700; individual Compose secret bind
        # mounts must be readable by the unprivileged container UID.
        path.chmod(0o644)


def render(spec: LabSpec, out: Path) -> dict[str, Any]:
    if out.exists():
        raise ValueError("Choose a new bundle directory")
    root = repo_root()
    if any(
        out.resolve().is_relative_to(root / source_dir)
        for source_dir in ("src", "infra/soc", "agent-office", ".claude")
    ):
        raise ValueError("Bundle output cannot be inside its own source inputs")
    out.mkdir(parents=True)
    (out / "tools").mkdir()
    source = out / "source"
    for name in (
        "pyproject.toml",
        "uv.lock",
        "LICENSE",
        "README.md",
        "README.vi.md",
        "notes.md",
        "catalog/subtasks.json",
    ):
        dest = source / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, dest)
    for path in (root / "src" / "saber").rglob("*.py"):
        if path.is_symlink():
            raise ValueError("Source symlinks are not allowed")
        dest = source / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    from saber.agents.skills import RUNTIME_SKILLS, skill_resources

    resources = {p for name in RUNTIME_SKILLS for p in skill_resources(name, root=root)}
    resources.add(root / ".claude/skills/soc-orchestrator/reference/soc-lab.md")
    for path in resources:
        dest = source / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    from saber.environments.bundle import OFFICE_FILES

    for name in OFFICE_FILES:
        dest = out / "agent-office" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "agent-office" / name, dest)
    assets = root / "infra" / "soc"
    for path in assets.rglob("*"):
        if path.is_file() and not path.is_symlink():
            dest = out / path.relative_to(assets)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
    (out / "lab.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    for name in (
        "SOC_LAB_VI.md",
        "SOC_COMPLETION.md",
        "SOC_ANALYSIS_VI.md",
        "SOC_SOAR_VI.md",
        "SOC_RECOVERY_VI.md",
        "SOC_LEARNING_VI.md",
        "SOC_BUILD_CHECKLIST.md",
    ):
        shutil.copyfile(root / "docs" / name, out / name)
        (source / "docs").mkdir(exist_ok=True)
        shutil.copyfile(root / "docs" / name, source / "docs" / name)
    (out / "compose.yaml").write_text(
        yaml.safe_dump(compose(spec), sort_keys=False), encoding="utf-8"
    )
    gemini = {
        "services": {
            "controller": {
                "networks": ["control", "telemetry", "provider-egress"],
                "secrets": ["controller", "gemini-pool"],
                "environment": {
                    "SABER_LLM": "1",
                    "SABER_CALL_BUDGET": "${SABER_CALL_BUDGET:?Explicit budget required}",
                    "SABER_MODEL": "${SABER_MODEL:?Explicit model required}",
                },
            }
        },
        "networks": {"provider-egress": {"internal": False}},
        "secrets": {
            "gemini-pool": {"file": "${SABER_GEMINI_POOL:?Existing private key file required}"}
        },
    }
    (out / "compose.gemini.yaml").write_text(
        yaml.safe_dump(gemini, sort_keys=False), encoding="utf-8"
    )
    (out / ".gitignore").write_text(".secrets/\n*.receipt.json\n*.vhdx\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "preset": spec.preset,
        "runtime_verified": False,
        "files": {
            str(p.relative_to(out)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob("*"))
            if p.is_file()
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "bundle": str(out),
        "preset": spec.preset,
        "services": list(compose(spec)["services"]),
        "windows_guests": len(spec.windows),
        "runtime_verified": False,
    }


def verify_bundle(bundle: Path) -> LabSpec:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    root = bundle.resolve()
    for name, digest in manifest["files"].items():
        path = root / name
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(root)
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ValueError("Bundle integrity check failed")
    # Build context cannot contain operator credentials or unmanifested files.
    for path in (root / "source").rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlinked build context is forbidden")
        if path.is_file() and path.relative_to(root).as_posix() not in manifest["files"]:
            raise ValueError("Unexpected build context file")
    return LabSpec.model_validate_json((root / "lab.json").read_text(encoding="utf-8"))
