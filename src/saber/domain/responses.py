"""ResponseAction: allowlisted kinds with typed targets. No free-form command fields exist."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from saber.domain.base import HostId, SafeStr, StrictModel, UtcDatetime

_DRIVE_PATH = re.compile(r"^[A-Za-z]:/")


class ActionKind(StrEnum):
    ISOLATE_LAB_HOST = "isolate_lab_host"
    BLOCK_LAB_ADDRESS = "block_lab_address"
    DISABLE_LAB_ACCOUNT = "disable_lab_account"
    COLLECT_EVIDENCE = "collect_evidence"
    DELETE_LAB_FILE = "delete_lab_file"
    KILL_LAB_PROCESS = "kill_lab_process"
    REMOVE_LAB_PERSISTENCE = "remove_lab_persistence"
    RESTORE_LAB_CONFIG = "restore_lab_config"


class ContainmentLayer(StrEnum):
    EDR = "edr"
    SWITCH = "switch"
    FIREWALL = "firewall"
    PROXY = "proxy"
    EMAIL_GATEWAY = "email_gateway"
    WAF = "waf"
    DNS = "dns"
    IDENTITY = "identity"


class ResponseMode(StrEnum):
    DRY_RUN = "dry_run"
    APPROVED_LAB = "approved_lab"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    PENDING = "pending"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTED = "executed"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"
    DENIED = "denied"
    EXPIRED = "expired"
    FAILED = "failed"


_S = ActionStatus
ACTION_TRANSITIONS: dict[ActionStatus, frozenset[ActionStatus]] = {
    _S.PROPOSED: frozenset({_S.APPROVED, _S.DENIED, _S.EXPIRED}),
    _S.APPROVED: frozenset({_S.EXECUTED, _S.EXPIRED, _S.FAILED, _S.DENIED}),
    _S.EXECUTED: frozenset({_S.VERIFIED, _S.ROLLED_BACK, _S.FAILED}),
    _S.VERIFIED: frozenset({_S.ROLLED_BACK}),
    _S.ROLLED_BACK: frozenset(),
    _S.DENIED: frozenset(),
    _S.EXPIRED: frozenset(),
    _S.FAILED: frozenset({_S.ROLLED_BACK}),
}

PersistenceKind = Literal[
    "run_key", "service", "scheduled_task", "wmi", "cron", "systemd", "profile_d", "startup"
]


class ActionTarget(StrictModel):
    """Exactly the fields an allowlisted action needs; strings reject shell metacharacters."""

    host_id: HostId | None = None
    address: SafeStr | None = None
    account: SafeStr | None = None
    path: SafeStr | None = None
    process_pid: int | None = Field(default=None, ge=1)
    persistence_kind: PersistenceKind | None = None
    persistence_name: SafeStr | None = None
    layer: ContainmentLayer | None = None

    @model_validator(mode="after")
    def _non_empty(self) -> ActionTarget:
        if not any(v is not None for v in self.model_dump().values()):
            raise ValueError("action target must name at least one attribute")
        if self.path is not None:
            normalized = self.path.replace("\\", "/")
            if ".." in normalized.split("/"):
                raise ValueError("action target path must not contain a '..' traversal segment")
            if not normalized.startswith("/") and not _DRIVE_PATH.match(normalized):
                raise ValueError("action target path must be absolute (lab-scoped)")
        return self


REQUIRED_TARGET_FIELDS: dict[ActionKind, tuple[str, ...]] = {
    ActionKind.ISOLATE_LAB_HOST: ("host_id",),
    ActionKind.BLOCK_LAB_ADDRESS: ("address", "layer"),
    ActionKind.DISABLE_LAB_ACCOUNT: ("account",),
    ActionKind.COLLECT_EVIDENCE: ("host_id",),
    ActionKind.DELETE_LAB_FILE: ("host_id", "path"),
    ActionKind.KILL_LAB_PROCESS: ("host_id", "process_pid"),
    ActionKind.REMOVE_LAB_PERSISTENCE: ("host_id", "persistence_kind", "persistence_name"),
    ActionKind.RESTORE_LAB_CONFIG: ("host_id", "path"),
}


class ResponseAction(StrictModel):
    schema_version: Literal[1] = 1
    action_id: UUID
    case_id: UUID | None = None
    episode_id: UUID
    kind: ActionKind
    target: ActionTarget
    reason: str = Field(min_length=1, max_length=2000)
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    mode: ResponseMode = ResponseMode.DRY_RUN
    policy_decision: PolicyDecision = PolicyDecision.PENDING
    approval_id: UUID | None = None
    status: ActionStatus = ActionStatus.PROPOSED
    created_at: UtcDatetime
    expires_at: UtcDatetime
    rollback_ref: str | None = Field(default=None, max_length=256)
    result_ref: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _shape(self) -> ResponseAction:
        for name in REQUIRED_TARGET_FIELDS[self.kind]:
            if getattr(self.target, name) is None:
                raise ValueError(f"action kind {self.kind.value} requires target.{name}")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at (TTL required)")
        executed = {ActionStatus.EXECUTED, ActionStatus.VERIFIED}
        if (
            self.mode is ResponseMode.APPROVED_LAB
            and self.status in executed
            and self.approval_id is None
        ):
            raise ValueError("executed lab actions require approval_id")
        return self
