"""Blocked hypervisor adapters: fail closed until an approved isolated lab exists."""

from __future__ import annotations

from dataclasses import dataclass

from saber.domain.errors import IntegrationBlocked
from saber.grading.state import MachineSnapshot
from saber.range.ports import SnapshotRef

_H_GATES = "SECURITY.md H1 (infra write), H2 (verified network isolation), H3 (approved profile)"


@dataclass
class BlockedRangeController:
    """Real hypervisor controller (e.g. Proxmox). BLOCKED_INTEGRATION until a lab is approved."""

    lab_environment_id: str

    def health(self, machine_id: str) -> bool:
        raise IntegrationBlocked(
            f"range health is BLOCKED_INTEGRATION ({_H_GATES})", machine_id=machine_id
        )

    def snapshot(self, machine_id: str) -> SnapshotRef:
        raise IntegrationBlocked(
            f"range snapshot is BLOCKED_INTEGRATION ({_H_GATES})", machine_id=machine_id
        )

    def capture_state(self, machine_id: str) -> MachineSnapshot:
        raise IntegrationBlocked(
            f"range capture_state is BLOCKED_INTEGRATION ({_H_GATES})", machine_id=machine_id
        )

    def restore(self, ref: SnapshotRef) -> bool:
        raise IntegrationBlocked(
            f"range restore is BLOCKED_INTEGRATION ({_H_GATES})", machine_id=ref.machine_id
        )


@dataclass
class BlockedEmulationDriver:
    """Allowlisted-emulation driver. Lists profiles but refuses to execute without a real lab + approval."""

    allowlist: tuple[str, ...] = ("discovery_benign_lookalike", "persistence_inert_marker")

    def list_allowlisted(self) -> list[str]:
        return list(self.allowlist)

    def execute(self, profile_id: str, *, approval_id: str, targets: list[str]) -> str:
        if profile_id not in self.allowlist:
            raise IntegrationBlocked(
                f"profile {profile_id!r} is not allowlisted", profile=profile_id
            )
        raise IntegrationBlocked(
            "emulation execution is BLOCKED_INTEGRATION: requires an isolated lab with verified "
            "network isolation and per-run operator approval (SECURITY.md H2/H3)",
            profile=profile_id,
            approval_id=approval_id,
            targets=targets,
        )

    def status(self, run_id: str) -> str:
        return "INDETERMINATE"
