"""Range controller, emulation driver and attack verifier ports (Protocols)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from saber.grading.state import MachineSnapshot


@dataclass(frozen=True)
class SnapshotRef:
    machine_id: str
    snapshot_id: str
    content_hash: str


@runtime_checkable
class RangeController(Protocol):
    """Provision/health/snapshot/restore. No arbitrary command endpoint is exposed."""

    def health(self, machine_id: str) -> bool: ...

    def snapshot(self, machine_id: str) -> SnapshotRef: ...

    def capture_state(self, machine_id: str) -> MachineSnapshot: ...

    def restore(self, ref: SnapshotRef) -> bool: ...


@runtime_checkable
class EmulationDriver(Protocol):
    """Runs only pre-reviewed, allowlisted emulation profiles bound to operator approval."""

    def list_allowlisted(self) -> list[str]: ...

    def execute(self, profile_id: str, *, approval_id: str, targets: list[str]) -> str: ...

    def status(self, run_id: str) -> str: ...


@runtime_checkable
class AttackVerifier(Protocol):
    """Independent verification of whether an emulation actually executed (outside the guest)."""

    def verify(self, run_id: str) -> str: ...  # VERIFIED | NOT_VERIFIED | INDETERMINATE
