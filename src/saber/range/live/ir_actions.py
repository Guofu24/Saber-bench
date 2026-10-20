"""Approved, allowlisted, reversible lab-only IR actions with real state verification (Phase G).

The only live containment action is quarantining a file inside the sandboxed webroot: it is
deny-by-default (refused without a non-empty operator approval id), allowlisted, confined to the
webroot (basename only, no traversal), reversible (restore), and VERIFIED from the actual
filesystem state after execution (the file is gone from the webroot and present in quarantine, with
no collateral change to other files). An action recommendation is never treated as containment —
only a verified ActionResult is.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ALLOWLISTED_ACTIONS = ("quarantine_webroot_file", "restore_webroot_file")
_QUARANTINE = ".quarantine"


@dataclass
class ActionResult:
    action: str
    target: str
    approval_id: str
    executed: bool
    reversible: bool
    verified: bool
    before: dict[str, str]
    after: dict[str, str]
    collateral: list[str] = field(default_factory=list)
    detail: str = ""
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def audit(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "approval_id": self.approval_id,
            "executed": self.executed,
            "reversible": self.reversible,
            "verified": self.verified,
            "collateral": self.collateral,
            "detail": self.detail,
            "ts": self.ts,
        }


def _snapshot(d: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if d.is_dir():
        for f in sorted(d.glob("*")):
            if f.is_file():
                out[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def _collateral(before: dict[str, str], after: dict[str, str], exclude: str) -> list[str]:
    """Files (other than the target) whose content changed or vanished — should be empty."""
    changed = []
    for name, sha in before.items():
        if name == exclude:
            continue
        if after.get(name) != sha:
            changed.append(name)
    return sorted(changed)


def quarantine_file(fs_root: Path, name: str, *, approval_id: str) -> ActionResult:
    """Move a webroot file into quarantine. Refuses without approval; verifies from real state."""
    action = "quarantine_webroot_file"
    name = Path(name).name  # basename only — no traversal
    qdir = fs_root / _QUARANTINE
    before = _snapshot(fs_root)
    if not approval_id:
        return ActionResult(
            action,
            name,
            approval_id,
            executed=False,
            reversible=True,
            verified=False,
            before=before,
            after=before,
            detail="refused: deny-by-default, no operator approval id",
        )
    src = fs_root / name
    if not src.is_file():
        return ActionResult(
            action,
            name,
            approval_id,
            executed=False,
            reversible=True,
            verified=False,
            before=before,
            after=before,
            detail=f"refused: {name} not present in webroot",
        )
    qdir.mkdir(exist_ok=True)
    shutil.move(str(src), str(qdir / name))
    after = _snapshot(fs_root)
    collateral = _collateral(before, after, name)
    verified = name not in after and (qdir / name).is_file() and not collateral
    return ActionResult(
        action,
        name,
        approval_id,
        executed=True,
        reversible=True,
        verified=verified,
        before=before,
        after=after,
        collateral=collateral,
        detail="quarantined; webroot no longer serves the file"
        if verified
        else "executed but state verification failed",
    )


def restore_file(fs_root: Path, name: str, *, approval_id: str) -> ActionResult:
    """Reverse a quarantine (restore the file to the webroot), verified from real state."""
    action = "restore_webroot_file"
    name = Path(name).name
    qdir = fs_root / _QUARANTINE
    before = _snapshot(fs_root)
    if not approval_id:
        return ActionResult(
            action,
            name,
            approval_id,
            executed=False,
            reversible=True,
            verified=False,
            before=before,
            after=before,
            detail="refused: deny-by-default, no operator approval id",
        )
    src = qdir / name
    if not src.is_file():
        return ActionResult(
            action,
            name,
            approval_id,
            executed=False,
            reversible=True,
            verified=False,
            before=before,
            after=before,
            detail=f"refused: {name} not in quarantine",
        )
    shutil.move(str(src), str(fs_root / name))
    after = _snapshot(fs_root)
    verified = name in after and not (qdir / name).is_file()
    return ActionResult(
        action,
        name,
        approval_id,
        executed=True,
        reversible=True,
        verified=verified,
        before=before,
        after=after,
        detail="restored",
    )
