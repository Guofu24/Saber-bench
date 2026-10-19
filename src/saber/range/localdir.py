"""DEV directory-backed machine: lets state verifiers run offline (DEV_SIMULATION_ONLY).

A directory tree stands in for a guest filesystem. Only read/capture is offered here; there is no
command execution. State-mutating response is never performed against a real host in DEV.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from saber.grading.state import MachineSnapshot, snapshot_directory
from saber.range.ports import SnapshotRef


@dataclass
class LocalDirMachine:
    machine_id: str
    root: Path

    def health(self, machine_id: str) -> bool:
        return machine_id == self.machine_id and self.root.is_dir()

    def capture_state(self, machine_id: str) -> MachineSnapshot:
        if machine_id != self.machine_id:
            raise ValueError(f"unknown machine {machine_id!r}")
        return snapshot_directory(self.root, machine_id=self.machine_id, taken_at=datetime.now(UTC))

    def snapshot(self, machine_id: str) -> SnapshotRef:
        snap = self.capture_state(machine_id)
        content_hash = snap.digest()
        return SnapshotRef(
            machine_id=machine_id, snapshot_id=f"dev-{content_hash[:12]}", content_hash=content_hash
        )

    def restore(self, ref: SnapshotRef) -> bool:
        # DEV machines are not mutated in offline mode; restore is a verified no-op against the hash.
        current = self.snapshot(ref.machine_id)
        return current.content_hash == ref.content_hash

    def baseline_hash(self) -> str:
        return hashlib.sha256(self.capture_state(self.machine_id).digest().encode()).hexdigest()
