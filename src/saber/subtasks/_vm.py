"""Helpers for VM-environment subtasks in offline DEV mode.

A machine is represented as an in-memory ``MachineSnapshot`` (no real hypervisor). The fixture
seals a *before* snapshot; the submission carries the *after* snapshot the verifier captured
outside the guest. State gates (machine_unchanged, all_removed, clean_intact, config_restored,
service_alive) run on these snapshots exactly as they would against real snapshots — only the
capture is simulated. Real hypervisor snapshotting is a BLOCKED_INTEGRATION adapter.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import Field

from saber.domain.base import StrictModel
from saber.grading.state import FileState, MachineSnapshot, ServiceState
from saber.subtasks._hv.common import Rng, iso


class GuestAction(StrictModel):
    """One declared action against the guest. The evaluator applies it to the sealed before-state.

    This is how a VM subtask stays sound offline: the agent declares operations, and the evaluator
    computes their effect on the sealed snapshot rather than trusting an agent-supplied after-state.
    `read` changes nothing (it is how an observe-only task declares it did not mutate).
    """

    op: Literal["read", "remove", "move", "modify"]
    path: str = Field(min_length=1, max_length=1024)
    to: str | None = Field(default=None, max_length=1024)

    @property
    def mutates(self) -> bool:
        return self.op != "read"


def _mutated_hash(old: str, path: str) -> str:
    return hashlib.sha256(f"modified:{old}:{path}".encode()).hexdigest()


def apply_actions(
    before: MachineSnapshot, actions: Sequence[GuestAction | Mapping[str, Any]], *, taken_at: str
) -> MachineSnapshot:
    """Derive the after-state by applying declared actions to the sealed before-snapshot."""
    files = dict(before.files)
    for raw in actions:
        action = raw if isinstance(raw, GuestAction) else GuestAction.model_validate(raw)
        if action.op == "read":
            continue
        if action.op == "remove":
            files.pop(action.path, None)
        elif action.op == "move" and action.to:
            fs = files.pop(action.path, None)
            if fs is not None:
                files[action.to] = fs.model_copy(update={"path": action.to})
        elif action.op == "modify":
            fs = files.get(action.path)
            if fs is not None:
                files[action.path] = fs.model_copy(
                    update={"sha256": _mutated_hash(fs.sha256, action.path)}
                )
    return MachineSnapshot(
        machine_id=before.machine_id,
        taken_at=taken_at,
        files=files,
        services=dict(before.services),
        cron_entries=list(before.cron_entries),
        users=list(before.users),
    )


def file_state(
    rng: Rng, path: str, *, tag: str = "", mtime_ns: int | None = None, size: int | None = None
) -> FileState:
    content_tag = tag or path
    return FileState(
        path=path,
        sha256=rng.sha256(content_tag),
        size=size if size is not None else rng.randint(512, 2_000_000),
        mtime_ns=mtime_ns
        if mtime_ns is not None
        else rng.randint(1_600_000_000_000_000_000, 1_700_000_000_000_000_000),
    )


def snapshot_from_files(
    machine_id: str,
    files: dict[str, FileState],
    *,
    taken_at: str,
    services: dict[str, ServiceState] | None = None,
    cron: list[str] | None = None,
    users: list[str] | None = None,
) -> MachineSnapshot:
    return MachineSnapshot(
        machine_id=machine_id,
        taken_at=taken_at,
        files=files,
        services=services or {},
        cron_entries=cron or [],
        users=users or [],
    )


def snapshot_to_public(snapshot: MachineSnapshot) -> dict[str, Any]:
    """Agent-visible projection of a machine: paths + hashes + inventories, no labels."""
    return {
        "machine_id": snapshot.machine_id,
        "files": {p: {"sha256": f.sha256, "size": f.size} for p, f in snapshot.files.items()},
        "services": {n: {"enabled": s.enabled} for n, s in snapshot.services.items()},
        "cron_entries": list(snapshot.cron_entries),
        "users": list(snapshot.users),
    }


def rebuild_snapshot(
    payload: dict[str, Any], *, taken_at: str, base: MachineSnapshot | None = None
) -> MachineSnapshot:
    """Rebuild a MachineSnapshot from an after-state payload, inheriting mtimes from `base`.

    A submission names the files/services/users that remain; mtimes come from the sealed base so
    that an unmodified file keeps its exact timestamp (evidence-integrity aware).
    """
    files: dict[str, FileState] = {}
    for path, meta in payload.get("files", {}).items():
        base_fs = base.files.get(path) if base else None
        files[path] = FileState(
            path=path,
            sha256=str(meta["sha256"]),
            size=int(meta.get("size", base_fs.size if base_fs else 0)),
            mtime_ns=int(meta["mtime_ns"])
            if "mtime_ns" in meta
            else (base_fs.mtime_ns if base_fs else 0),
        )
    services = {
        n: ServiceState(name=n, enabled=bool(s.get("enabled", True)))
        for n, s in payload.get("services", {}).items()
    }
    return MachineSnapshot(
        machine_id=str(payload.get("machine_id", base.machine_id if base else "vm")),
        taken_at=taken_at,
        files=files,
        services=services,
        cron_entries=list(payload.get("cron_entries", [])),
        users=list(payload.get("users", [])),
    )


def now_iso(rng: Rng) -> str:
    return iso(rng.time())
