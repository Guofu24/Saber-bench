"""Response policy: lab asset registry, deterministic action hashing, operator approvals."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

from pydantic import Field

from saber.domain.base import StrictModel, UtcDatetime
from saber.domain.responses import ActionKind, ResponseAction, ResponseMode
from saber.domain.runs import Track


def action_hash(action: ResponseAction) -> str:
    """Stable hash over the fields an approval is bound to (kind + exact target + episode)."""
    material = {
        "kind": action.kind.value,
        "target": action.target.model_dump(mode="json", exclude_none=True),
        "episode_id": str(action.episode_id),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


class LabAssetRegistry(StrictModel):
    """The only assets a response may touch. Anything outside is rejected."""

    lab_environment_id: str = Field(min_length=1)
    hosts: frozenset[str] = frozenset()
    addresses: frozenset[str] = frozenset()
    accounts: frozenset[str] = frozenset()
    protected_hosts: frozenset[str] = frozenset()  # benign/VIP assets that must never be contained

    def permits(self, action: ResponseAction) -> tuple[bool, str]:
        t = action.target
        if t.host_id is not None:
            if t.host_id not in self.hosts:
                return False, f"host {t.host_id!r} not in lab_asset_registry"
            if t.host_id in self.protected_hosts and action.kind != ActionKind.COLLECT_EVIDENCE:
                return False, f"host {t.host_id!r} is protected; only evidence collection allowed"
        if t.address is not None and t.address not in self.addresses:
            return False, f"address {t.address!r} not in lab_asset_registry"
        if t.account is not None and t.account not in self.accounts:
            return False, f"account {t.account!r} not in lab_asset_registry"
        return True, "target within lab asset registry"


class ApprovalRecord(StrictModel):
    """Binds an operator approval to one exact action in one environment, with a TTL."""

    approval_id: UUID
    action_id: UUID
    action_hash: str = Field(min_length=64, max_length=64)
    lab_environment_id: str
    operator_id: str = Field(min_length=1)
    approved_at: UtcDatetime
    expires_at: UtcDatetime

    def valid_for(
        self, action: ResponseAction, registry_env: str, now: datetime
    ) -> tuple[bool, str]:
        if self.action_id != action.action_id:
            return False, "approval action_id mismatch"
        if self.action_hash != action_hash(action):
            return False, "approval does not match this action's parameters"
        if self.lab_environment_id != registry_env:
            return False, "approval is for a different lab environment"
        if now >= self.expires_at:
            return False, "approval TTL expired"
        return True, "approval valid"


class PolicyEngine:
    """Deterministic, deny-by-default policy. No LLM input; operator identity is distinct from agents."""

    def __init__(
        self, registry: LabAssetRegistry, *, track: Track, agent_ids: frozenset[str] = frozenset()
    ) -> None:
        self.registry = registry
        self.track = track
        self.agent_ids = agent_ids

    def evaluate_proposal(self, action: ResponseAction) -> tuple[bool, str]:
        if self.track is Track.DETECTION_ONLY and action.mode is ResponseMode.APPROVED_LAB:
            return False, "DETECTION_ONLY track forbids lab side effects"
        if not action.supporting_evidence_ids and action.kind != ActionKind.COLLECT_EVIDENCE:
            return False, "a containment action must cite supporting evidence"
        return self.registry.permits(action)

    def may_approve(self, operator_id: str) -> tuple[bool, str]:
        if operator_id in self.agent_ids:
            return False, "an agent cannot approve its own (or any) action"
        if not operator_id.startswith("operator:"):
            return False, "approver is not a recognised operator identity"
        return True, "operator may approve"

    def authorize_execution(
        self, action: ResponseAction, approval: ApprovalRecord | None, now: datetime
    ) -> tuple[bool, str]:
        if self.track is Track.DETECTION_ONLY:
            return False, "DETECTION_ONLY track cannot execute"
        if action.mode is not ResponseMode.APPROVED_LAB:
            return False, "execution requires approved_lab mode"
        ok, reason = self.registry.permits(action)
        if not ok:
            return False, reason
        if approval is None:
            return False, "no operator approval present"
        return approval.valid_for(action, self.registry.lab_environment_id, now)
