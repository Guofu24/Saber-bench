"""Read-only checks. Reachability is never reported as vendor adapter readiness."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from saber.environments.models import EnvironmentConfig, Service


def memory_info() -> dict[str, int | None]:
    total: int | None = None
    available: int | None = None
    try:
        if sys.platform == "win32":

            class Memory(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong)
                    for name in (
                        "total",
                        "available",
                        "page_total",
                        "page_available",
                        "virtual_total",
                        "virtual_available",
                        "extended",
                    )
                ]

            status = Memory()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                total, available = int(status.total), int(status.available)
        elif Path("/proc/meminfo").exists():
            data = {
                line.split(":")[0]: int(line.split()[1]) * 1024
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith(("MemTotal:", "MemAvailable:"))
            }
            total, available = data.get("MemTotal"), data.get("MemAvailable")
    except (OSError, ValueError, AttributeError):
        pass
    return {
        "total_mb": total // 1048576 if total is not None else None,
        "available_mb": available // 1048576 if available is not None else None,
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def probe_service(service: Service, *, enabled: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": service.name,
        "capability": service.capability,
        "adapter_verified": False,
    }
    if not enabled or not service.approved_for_read_only_use:
        return result | {
            "status": "not_probed",
            "reason": "Requires --probe-services and approved_for_read_only_use=true.",
        }
    headers = {"Accept": "application/json"}
    if service.credential_env_name:
        credential = os.environ.get(service.credential_env_name)
        if not credential:
            return result | {"status": "credential_missing"}
        parts = urlsplit(service.api_base_url)
        if parts.scheme != "https" and parts.hostname not in ("127.0.0.1", "::1", "localhost"):
            return result | {"status": "tls_required_for_credentials"}
        headers["Authorization"] = f"Bearer {credential}"
    try:
        request = urllib.request.Request(
            service.api_base_url + service.health_check_path, headers=headers, method="GET"
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=5) as response:
            return result | {"status": "http_reachable", "http_status": response.status}
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        return result | {
            "status": "redirect_refused" if 300 <= code < 400 else "http_error",
            "http_status": code,
        }
    except (OSError, ValueError, urllib.error.URLError):
        return result | {
            "status": "unreachable",
            "reason": "Transport/TLS failure; details redacted.",
        }


def doctor(config: EnvironmentConfig, *, probe_services: bool = False) -> dict[str, Any]:
    blockers = []
    checks: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.system(),
        "logical_cpus": os.cpu_count(),
        "memory": memory_info(),
    }
    if config.profile == "sandbox":
        docker = shutil.which("docker")
        checks["docker_cli"] = docker is not None
        checks["linux_engine"] = False
        checks["compose"] = False
        if docker:
            for name, argv in (
                ("linux_engine", [docker, "info", "--format", "{{.OSType}}"]),
                ("compose", [docker, "compose", "version", "--short"]),
            ):
                try:
                    result = subprocess.run(
                        argv, capture_output=True, text=True, timeout=8, check=False
                    )
                    checks[name] = result.returncode == 0 and (
                        result.stdout.strip() == "linux"
                        if name == "linux_engine"
                        else bool(result.stdout.strip())
                    )
                except (OSError, subprocess.SubprocessError):
                    pass
        if not checks["linux_engine"]:
            blockers.append("Docker Linux engine unavailable; no daemon was started.")
        if not checks["compose"]:
            blockers.append("Docker Compose unavailable.")
    with ThreadPoolExecutor(max_workers=4) as executor:
        services = list(
            executor.map(
                lambda service: probe_service(service, enabled=probe_services), config.services
            )
        )
    warnings = []
    available = checks["memory"]["available_mb"]
    if (
        config.profile == "sandbox"
        and available is not None
        and available < config.resources.memory_mb
    ):
        warnings.append(
            "Available host RAM is below the configured container limit; reduce the limit or free RAM."
        )
    if config.profile in ("vm", "remote"):
        warnings.append(
            "This inspects the current host only; run the bundle on the intended guest/server with --on-target."
        )
    return {
        "profile": config.profile,
        "checks": checks,
        "prerequisites_available_on_this_host": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "services": services,
        "runtime_verified": False,
        "isolation_verified": False,
        "note": "No installation, provisioning, API inference or attack execution. Health checks do not connect vendor data/response adapters.",
    }
