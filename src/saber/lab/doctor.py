"""Read-only target readiness; never starts Docker, installs tools or changes sysctls."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from saber.lab.models import LabSpec


def inspect_host(spec: LabSpec, directory: Path) -> dict[str, Any]:
    memory = None
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            memory = int(result.stdout.strip()) / (1024**3)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    else:
        try:
            fields = dict(
                line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
            )
            memory = int(fields["MemTotal"].split()[0]) / (1024**2)
        except (OSError, ValueError, KeyError):
            pass
    free = shutil.disk_usage(directory.resolve()).free / (1024**3)
    engine = False
    docker = shutil.which("docker")
    if docker:
        try:
            result = subprocess.run(
                [docker, "info", "--format", "{{json .OSType}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            engine = result.returncode == 0 and json.loads(result.stdout) == "linux"
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    checks = {
        "linux_docker_engine": engine,
        "ram_capacity": memory is not None and memory >= spec.host_ram_gb * 0.9,
        "logical_cpu_capacity": (os.cpu_count() or 0) >= spec.host_cpus,
        "free_disk_capacity": free >= spec.disk_gb,
    }
    max_map_count = None
    if sys.platform == "linux":
        try:
            max_map_count = int(Path("/proc/sys/vm/max_map_count").read_text())
            checks["opensearch_vm_max_map_count"] = max_map_count >= 262144
        except (OSError, ValueError):
            checks["opensearch_vm_max_map_count"] = False
    return {
        "ready_for_deployment": all(checks.values()),
        "runtime_verified": False,
        "preset": spec.preset,
        "checks": checks,
        "observed": {
            "ram_gb": round(memory, 1) if memory else None,
            "logical_cpus": os.cpu_count(),
            "free_disk_gb": round(free, 1),
            "vm_max_map_count": max_map_count,
        },
        "windows": "Separate Hyper-V host and prepared Windows VHDX images required"
        if spec.windows
        else "not required",
    }
