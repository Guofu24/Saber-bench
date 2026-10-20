"""Approved, allowlisted, reversible lab-only IR actions with real state verification (Phase G).

The only live containment action is quarantining a file inside the sandboxed webroot. Per
SECURITY.md's incident-response contract, authorization is strict:

* **Allowlisted** — the action must be in :data:`ALLOWLISTED_ACTIONS`.
* **Bound approval** — an :class:`Approval` is granted for a specific action + target (+ scope, TTL);
  reusing it for a different action/target, or after it expires, is rejected.
* **Separate executor token** — execution requires an executor token that matches the one the
  approval was granted to; the detection/agent path does not hold it (separation of duties).
* **Reversible + verified** — quarantine has a restore, and the effect is VERIFIED from the real
  post-action filesystem state (target gone from the webroot, present in quarantine, zero
  collateral). A recommendation is never treated as containment — only a verified ActionResult is.
"""

from __future__ import annotations

import hashlib
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ALLOWLISTED_ACTIONS = ("quarantine_webroot_file", "restore_webroot_file")
_QUARANTINE = ".quarantine"


@dataclass(frozen=True)
class Approval:
    """An operator approval bound to one action + target, with an executor token and a TTL."""

    approval_id: str
    action: str
    target: str
    scope: str
    executor_token: str
    expires_at: datetime

    def covers(self, action: str, target: str, *, now: datetime | None = None) -> tuple[bool, str]:
        now = now or datetime.now(UTC)
        if action not in ALLOWLISTED_ACTIONS:
            return False, f"action {action!r} not allowlisted"
        if self.action != action:
            return False, f"approval is for action {self.action!r}, not {action!r}"
        if self.target != target:
            return False, f"approval is bound to target {self.target!r}, not {target!r}"
        if now > self.expires_at:
            return False, "approval expired"
        return True, "ok"


def grant_approval(
    action: str, target: str, *, executor_token: str, scope: str = "webroot", ttl_s: int = 300
) -> Approval:
    """Operator mints an approval bound to the exact action + target (lab operator role)."""
    if action not in ALLOWLISTED_ACTIONS:
        raise ValueError(f"cannot approve non-allowlisted action {action!r}")
    if not executor_token:
        raise ValueError("executor_token required")
    return Approval(
        approval_id=f"APPR-{secrets.token_hex(4)}",
        action=action,
        target=Path(target).name,
        scope=scope,
        executor_token=executor_token,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_s),
    )


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
    return sorted(n for n, sha in before.items() if n != exclude and after.get(n) != sha)


def _authorize(
    action: str, name: str, approval: Approval | None, executor_token: str, before: dict[str, str]
) -> ActionResult | None:
    """Return a refusal ActionResult if not authorized, else None (authorized)."""

    def refuse(detail: str) -> ActionResult:
        return ActionResult(
            action,
            name,
            approval.approval_id if approval else "none",
            executed=False,
            reversible=True,
            verified=False,
            before=before,
            after=before,
            detail="refused: " + detail,
        )

    if approval is None:
        return refuse("deny-by-default, no operator approval")
    ok, reason = approval.covers(action, name)
    if not ok:
        return refuse(reason)
    if not executor_token or executor_token != approval.executor_token:
        return refuse("executor token missing or does not match the approval")
    return None


def quarantine_file(
    fs_root: Path, name: str, *, approval: Approval | None, executor_token: str
) -> ActionResult:
    """Move a webroot file into quarantine under a bound approval + executor token; verify from state."""
    action = "quarantine_webroot_file"
    name = Path(name).name  # basename only — no traversal
    qdir = fs_root / _QUARANTINE
    before = _snapshot(fs_root)
    refusal = _authorize(action, name, approval, executor_token, before)
    if refusal is not None:
        return refusal
    assert approval is not None
    src = fs_root / name
    if not src.is_file():
        return ActionResult(
            action,
            name,
            approval.approval_id,
            executed=False,
            reversible=True,
            verified=False,
            before=before,
            after=before,
            detail=f"refused: {name} not present",
        )
    qdir.mkdir(exist_ok=True)
    shutil.move(str(src), str(qdir / name))
    after = _snapshot(fs_root)
    collateral = _collateral(before, after, name)
    verified = name not in after and (qdir / name).is_file() and not collateral
    return ActionResult(
        action,
        name,
        approval.approval_id,
        executed=True,
        reversible=True,
        verified=verified,
        before=before,
        after=after,
        collateral=collateral,
        detail="quarantined; verified from real fs state"
        if verified
        else "executed but verification failed",
    )


def restore_file(
    fs_root: Path, name: str, *, approval: Approval | None, executor_token: str
) -> ActionResult:
    """Reverse a quarantine under a bound approval + executor token; verify from state."""
    action = "restore_webroot_file"
    name = Path(name).name
    qdir = fs_root / _QUARANTINE
    before = _snapshot(fs_root)
    refusal = _authorize(action, name, approval, executor_token, before)
    if refusal is not None:
        return refusal
    assert approval is not None
    src = qdir / name
    if not src.is_file():
        return ActionResult(
            action,
            name,
            approval.approval_id,
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
        approval.approval_id,
        executed=True,
        reversible=True,
        verified=verified,
        before=before,
        after=after,
        detail="restored",
    )
