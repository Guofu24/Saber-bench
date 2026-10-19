"""Docker-backed reproducible Linux lab adapter (Phase E3).

Implements the :class:`RangeController` port against the ``lab/docker-compose.yml`` lab. It never
starts Docker or mutates a host automatically; it fails closed with a precise blocker when the
daemon is unavailable. Read-only health is a real check when the daemon is up; stateful snapshot /
restore stay ``BLOCKED_INTEGRATION`` until an authorized lab with an independent state verifier and
per-run operator approval exists (SECURITY.md H-gates). The lab plan is validated offline.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from saber.catalog.loader import repo_root
from saber.domain.errors import IntegrationBlocked
from saber.grading.state import MachineSnapshot
from saber.range.ports import SnapshotRef

_H_GATES = "SECURITY.md H1 (infra write), H2 (verified network isolation), H3 (approved profile)"


def lab_dir() -> Path:
    return repo_root() / "lab"


def lab_compose_path() -> Path:
    return lab_dir() / "docker-compose.yml"


def docker_daemon_up(timeout: float = 20.0) -> bool:
    """True iff a Docker daemon answers. Read-only probe; never starts anything."""
    exe = shutil.which("docker")
    if exe is None:
        return False
    try:
        r = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [exe, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


def validate_lab_plan(path: Path | None = None) -> tuple[bool, list[str]]:
    """Offline isolation/safety validation of the compose plan (no daemon needed)."""
    p = path or lab_compose_path()
    issues: list[str] = []
    if not p.exists():
        return False, [f"missing compose file: {p}"]
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return False, [f"compose YAML parse error: {exc}"]
    if not isinstance(doc, dict):
        return False, ["compose root is not a mapping"]

    networks = doc.get("networks") or {}
    if not any(isinstance(n, dict) and n.get("internal") is True for n in networks.values()):
        issues.append("no network marked internal: true (egress isolation required)")

    services = doc.get("services") or {}
    if not services:
        issues.append("no services defined")
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        if svc.get("privileged") is True:
            issues.append(f"service {name}: privileged is forbidden in the lab")
        if "ALL" not in (svc.get("cap_drop") or []):
            issues.append(f"service {name}: must cap_drop ALL")
        if "no-new-privileges:true" not in (svc.get("security_opt") or []):
            issues.append(f"service {name}: must set no-new-privileges")
        if svc.get("network_mode") == "host":
            issues.append(f"service {name}: host network mode is forbidden")
        for vol in svc.get("volumes") or []:
            vs = vol if isinstance(vol, str) else ""
            # bind mounts from the host must be read-only (named volumes like 'telemetry:/x' are ok)
            if vs.startswith((".", "/")) and not vs.rstrip().endswith(":ro"):
                issues.append(f"service {name}: host bind mount not read-only: {vs}")
    return (not issues), issues


@dataclass
class DockerLabController:
    """RangeController backed by the docker-compose lab. Fails closed; claims no real integration."""

    machine_id: str = "saber-lab-workload"
    compose_path: Path = field(default_factory=lab_compose_path)

    def _require_daemon(self) -> None:
        if not docker_daemon_up():
            raise IntegrationBlocked(
                "Docker lab is BLOCKED_INTEGRATION: the Docker Linux daemon is not running (CR-1). "
                "An operator must start Docker Desktop or install WSL2; the agent never starts it.",
                machine_id=self.machine_id,
            )

    def health(self, machine_id: str) -> bool:
        """Read-only: is the lab workload container running? (real check when the daemon is up)."""
        self._require_daemon()
        exe = shutil.which("docker")
        assert exe is not None  # daemon up implies docker present
        r = subprocess.run(  # noqa: S603 - fixed argv, no shell  # pragma: no cover - needs daemon
            [exe, "compose", "-f", str(self.compose_path), "ps", "--status=running", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return r.returncode == 0 and bool(r.stdout.strip())

    def snapshot(self, machine_id: str) -> SnapshotRef:
        self._require_daemon()  # pragma: no cover - needs daemon
        raise IntegrationBlocked(
            f"lab snapshot is BLOCKED_INTEGRATION: stateful capture requires an authorized lab with "
            f"an independent state verifier and per-run approval ({_H_GATES})",
            machine_id=machine_id,
        )

    def capture_state(self, machine_id: str) -> MachineSnapshot:
        self._require_daemon()  # pragma: no cover - needs daemon
        raise IntegrationBlocked(
            f"lab capture_state is BLOCKED_INTEGRATION until exercised in an authorized lab ({_H_GATES})",
            machine_id=machine_id,
        )

    def restore(self, ref: SnapshotRef) -> bool:
        self._require_daemon()  # pragma: no cover - needs daemon
        raise IntegrationBlocked(
            f"lab restore is BLOCKED_INTEGRATION: state mutation requires an authorized lab ({_H_GATES})",
            machine_id=ref.machine_id,
        )

    def bring_up_command(self) -> list[str]:
        """The exact (operator-run) command to start the lab. The adapter never runs it itself."""
        return ["docker", "compose", "-f", str(self.compose_path), "up", "-d"]

    def reset_command(self) -> list[str]:
        return ["docker", "compose", "-f", str(self.compose_path), "down", "-v"]


def lab_status() -> dict[str, Any]:
    """A one-call readiness snapshot of the lab (no mutation)."""
    ok, issues = validate_lab_plan()
    up = docker_daemon_up()
    return {
        "compose_path": str(lab_compose_path()),
        "plan_valid": ok,
        "plan_issues": issues,
        "docker_daemon_up": up,
        "status": "READY_TO_LAUNCH"
        if (ok and up)
        else ("BLOCKED_DAEMON_DOWN" if ok else "PLAN_INVALID"),
        "note": "benign, network-isolated lab; stateful ops stay BLOCKED_INTEGRATION until an authorized lab",
    }
