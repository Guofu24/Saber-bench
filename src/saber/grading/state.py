"""State verifiers for `state/*` items. Snapshots are taken outside the guest by the evaluator.

DEV adapter: a directory tree stands in for a machine (`LocalDirMachine`, DEV_SIMULATION_ONLY).
Real hypervisor snapshots are provided by `saber.range` adapters and are BLOCKED_INTEGRATION
until an isolated lab is approved.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import Field

from saber.domain.base import StrictModel, UtcDatetime
from saber.grading.results import GateOutcome


class FileState(StrictModel):
    path: str
    sha256: str
    size: int = Field(ge=0)
    mtime_ns: int


class ServiceState(StrictModel):
    name: str
    enabled: bool = True
    unit_sha256: str | None = None


class MachineSnapshot(StrictModel):
    machine_id: str
    taken_at: UtcDatetime
    files: dict[str, FileState] = Field(default_factory=dict)
    services: dict[str, ServiceState] = Field(default_factory=dict)
    cron_entries: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)
    config_tree_sha256: str | None = None
    labels: list[str] = Field(default_factory=lambda: ["DEV_SIMULATION_ONLY"])

    def digest(self) -> str:
        h = hashlib.sha256()
        for path in sorted(self.files):
            f = self.files[path]
            h.update(f"{path}\0{f.sha256}\0{f.size}\0".encode())
        for name in sorted(self.services):
            s = self.services[name]
            h.update(f"svc:{name}\0{s.enabled}\0{s.unit_sha256}\0".encode())
        for entry in sorted(self.cron_entries):
            h.update(f"cron:{entry}\0".encode())
        for user in sorted(self.users):
            h.update(f"user:{user}\0".encode())
        return h.hexdigest()

    def hashes(self) -> set[str]:
        return {f.sha256 for f in self.files.values()}


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_directory(
    root: Path,
    *,
    machine_id: str,
    taken_at: Any,
    config_subdir: str | None = "etc",
) -> MachineSnapshot:
    """Snapshot a directory tree standing in for a guest filesystem (DEV_SIMULATION_ONLY).

    Convention: `etc/cron.d/*` and `etc/crontab` lines are cron entries; `etc/systemd/system/*.service`
    are services (enabled unless a sibling `<name>.disabled` marker exists); `etc/passwd` lists users.
    """
    files: dict[str, FileState] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = PurePosixPath(p.relative_to(root).as_posix()).as_posix()
            st = p.stat()
            files[rel] = FileState(
                path=rel, sha256=_sha256_path(p), size=st.st_size, mtime_ns=st.st_mtime_ns
            )
    cron: list[str] = []
    for candidate in (
        [root / "etc" / "crontab", *sorted((root / "etc" / "cron.d").glob("*"))]
        if (root / "etc").is_dir()
        else []
    ):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    cron.append(f"{candidate.relative_to(root).as_posix()}:{line}")
    services: dict[str, ServiceState] = {}
    sysd = root / "etc" / "systemd" / "system"
    if sysd.is_dir():
        for unit in sorted(sysd.glob("*.service")):
            services[unit.name] = ServiceState(
                name=unit.name,
                enabled=not (sysd / f"{unit.name}.disabled").exists(),
                unit_sha256=_sha256_path(unit),
            )
    users: list[str] = []
    passwd = root / "etc" / "passwd"
    if passwd.is_file():
        for line in passwd.read_text(encoding="utf-8", errors="replace").splitlines():
            if line and ":" in line:
                users.append(line.split(":", 1)[0])
    config_hash: str | None = None
    if config_subdir and (root / config_subdir).is_dir():
        h = hashlib.sha256()
        for rel in sorted(k for k in files if k.startswith(config_subdir.rstrip("/") + "/")):
            h.update(f"{rel}\0{files[rel].sha256}\0".encode())
        config_hash = h.hexdigest()
    return MachineSnapshot(
        machine_id=machine_id, taken_at=taken_at, files=files, services=services,
        cron_entries=cron, users=users, config_tree_sha256=config_hash,
    )  # fmt: skip


class StateDiff(StrictModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    mtime_only: list[str] = Field(default_factory=list)
    services_changed: list[str] = Field(default_factory=list)
    cron_changed: bool = False
    users_changed: bool = False

    @property
    def unchanged(self) -> bool:
        return not (
            self.added
            or self.removed
            or self.modified
            or self.services_changed
            or self.cron_changed
            or self.users_changed
        )


def diff_snapshots(before: MachineSnapshot, after: MachineSnapshot) -> StateDiff:
    added = sorted(set(after.files) - set(before.files))
    removed = sorted(set(before.files) - set(after.files))
    modified: list[str] = []
    mtime_only: list[str] = []
    for path in sorted(set(before.files) & set(after.files)):
        b, a = before.files[path], after.files[path]
        if b.sha256 != a.sha256 or b.size != a.size:
            modified.append(path)
        elif b.mtime_ns != a.mtime_ns:
            mtime_only.append(path)
    services_changed = sorted(
        name
        for name in set(before.services) | set(after.services)
        if before.services.get(name) != after.services.get(name)
    )
    return StateDiff(
        added=added, removed=removed, modified=modified, mtime_only=mtime_only,
        services_changed=services_changed, cron_changed=sorted(before.cron_entries) != sorted(after.cron_entries),
        users_changed=sorted(before.users) != sorted(after.users),
    )  # fmt: skip


def machine_unchanged(
    before: MachineSnapshot, after: MachineSnapshot, *, name: str = "machine_unchanged"
) -> GateOutcome:
    d = diff_snapshots(before, after)
    if d.unchanged:
        return GateOutcome(name=name, passed=True, reason="no content/service/cron/user changes")
    parts = []
    if d.added:
        parts.append(f"added={d.added[:5]}")
    if d.removed:
        parts.append(f"removed={d.removed[:5]}")
    if d.modified:
        parts.append(f"modified={d.modified[:5]}")
    if d.services_changed:
        parts.append(f"services={d.services_changed[:5]}")
    if d.cron_changed:
        parts.append("cron changed")
    if d.users_changed:
        parts.append("users changed")
    return GateOutcome(name=name, passed=False, reason="; ".join(parts))


def clean_intact(
    before: MachineSnapshot,
    after: MachineSnapshot,
    protected: Iterable[str],
    *,
    name: str = "clean_intact",
) -> GateOutcome:
    """Every protected (clean) file must still exist byte-identical (hash + size)."""
    damaged: list[str] = []
    for path in protected:
        b = before.files.get(path)
        a = after.files.get(path)
        if b is None:
            damaged.append(f"{path} (not in baseline)")
        elif a is None:
            damaged.append(f"{path} (deleted)")
        elif a.sha256 != b.sha256 or a.size != b.size:
            damaged.append(f"{path} (modified)")
    if damaged:
        return GateOutcome(name=name, passed=False, reason=f"clean files damaged: {damaged[:5]}")
    return GateOutcome(name=name, passed=True, reason="all protected files byte-identical")


def all_removed(
    before: MachineSnapshot,
    after: MachineSnapshot,
    malicious: Iterable[str],
    *,
    name: str = "all_removed",
) -> tuple[GateOutcome, dict[str, Any]]:
    """Malicious paths must be gone AND their content hashes absent anywhere (no relocation)."""
    targets = list(malicious)
    still_present = [p for p in targets if p in after.files]
    mal_hashes = {before.files[p].sha256 for p in targets if p in before.files}
    relocated = sorted(
        p for p, f in after.files.items() if f.sha256 in mal_hashes and p not in targets
    )
    removed_count = len(targets) - len(still_present)
    detail = {
        "targets": len(targets),
        "removed": removed_count,
        "still_present": still_present[:10],
        "relocated": relocated[:10],
    }
    if still_present or relocated:
        reason = f"still_present={still_present[:3]} relocated={relocated[:3]}"
        return GateOutcome(name=name, passed=False, reason=reason), detail
    return GateOutcome(
        name=name, passed=True, reason=f"{len(targets)} artefacts removed, no relocation"
    ), detail


def removal_recall(
    before: MachineSnapshot, after: MachineSnapshot, malicious: Iterable[str]
) -> tuple[float, dict[str, Any]]:
    targets = [p for p in malicious if p in before.files]
    if not targets:
        return 0.0, {"targets": 0}
    after_hashes = after.hashes()
    gone = [
        p for p in targets if p not in after.files and before.files[p].sha256 not in after_hashes
    ]
    return len(gone) / len(targets), {"targets": len(targets), "gone": len(gone)}


def evidence_intact(
    originals: dict[str, FileState],
    collected: dict[str, FileState],
    *,
    name: str = "evidence_intact",
) -> GateOutcome:
    """Collected copies must match original hash AND preserve the original mtime (T1370)."""
    problems: list[str] = []
    for path, orig in originals.items():
        got = collected.get(path)
        if got is None:
            continue  # recall handled separately
        if got.sha256 != orig.sha256:
            problems.append(f"{path}: hash changed")
        elif got.mtime_ns != orig.mtime_ns:
            problems.append(f"{path}: mtime changed")
    if problems:
        return GateOutcome(name=name, passed=False, reason="; ".join(problems[:5]))
    return GateOutcome(name=name, passed=True, reason="hashes and timestamps preserved")


def config_restored(
    baseline: MachineSnapshot,
    after: MachineSnapshot,
    config_paths: Iterable[str],
    *,
    name: str = "config_restored",
) -> GateOutcome:
    diffs = [
        p
        for p in config_paths
        if baseline.files.get(p) is None
        or after.files.get(p) is None
        or baseline.files[p].sha256 != after.files[p].sha256
    ]
    if diffs:
        return GateOutcome(
            name=name, passed=False, reason=f"config differs from clean baseline: {diffs[:5]}"
        )
    return GateOutcome(name=name, passed=True, reason="config matches clean baseline")


def service_alive(probe: Callable[[], bool], *, name: str = "service_alive") -> GateOutcome:
    try:
        ok = bool(probe())
    except Exception as exc:  # noqa: BLE001 - any probe failure is a failed gate, never a crash
        return GateOutcome(name=name, passed=False, reason=f"probe error: {type(exc).__name__}")
    return GateOutcome(
        name=name, passed=ok, reason="service responded" if ok else "service not responding"
    )
