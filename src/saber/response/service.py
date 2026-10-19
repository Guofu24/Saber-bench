"""ResponseService: drives the action state machine with policy checks and audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from saber.domain.errors import InvalidTransition, PolicyDenied
from saber.domain.responses import (
    ACTION_TRANSITIONS,
    ActionStatus,
    PolicyDecision,
    ResponseAction,
    ResponseMode,
)
from saber.response.driver import ResponseDriver
from saber.response.policy import ApprovalRecord, PolicyEngine


@dataclass
class ResponseService:
    policy: PolicyEngine
    driver: ResponseDriver
    # No default: the executor token must be injected from a secret held by the operator, never an
    # agent (SECURITY.md separation of duties). A dry-run driver ignores it; a real one requires it.
    executor_token: str = ""
    audit: list[str] = field(default_factory=list)

    def _log(self, msg: str) -> None:
        self.audit.append(msg)

    def _transition(self, action: ResponseAction, new: ActionStatus) -> ResponseAction:
        if new not in ACTION_TRANSITIONS[action.status]:
            raise InvalidTransition(f"{action.status.value} -> {new.value} is not allowed")
        return action.model_copy(update={"status": new})

    def propose(self, action: ResponseAction) -> ResponseAction:
        ok, reason = self.policy.evaluate_proposal(action)
        decision = PolicyDecision.ALLOW if ok else PolicyDecision.DENY
        self._log(f"propose {action.action_id}: {decision.value} ({reason})")
        if not ok:
            return self._transition(
                action.model_copy(update={"policy_decision": decision}), ActionStatus.DENIED
            )
        return action.model_copy(update={"policy_decision": decision})

    def approve(
        self, action: ResponseAction, approval: ApprovalRecord, *, now: datetime
    ) -> ResponseAction:
        ok, reason = self.policy.may_approve(approval.operator_id)
        if not ok:
            self._log(f"approve {action.action_id}: DENY ({reason})")
            raise PolicyDenied(reason)
        valid, vreason = approval.valid_for(action, self.policy.registry.lab_environment_id, now)
        if not valid:
            self._log(f"approve {action.action_id}: DENY ({vreason})")
            raise PolicyDenied(vreason)
        self._log(f"approve {action.action_id}: APPROVED by {approval.operator_id}")
        return self._transition(
            action.model_copy(update={"approval_id": approval.approval_id}), ActionStatus.APPROVED
        )

    def execute(
        self, action: ResponseAction, approval: ApprovalRecord | None, *, now: datetime
    ) -> ResponseAction:
        ok, reason = self.policy.authorize_execution(action, approval, now)
        if not ok:
            self._log(f"execute {action.action_id}: DENY ({reason})")
            raise PolicyDenied(reason)
        if action.status is ActionStatus.EXECUTED:
            self._log(f"execute {action.action_id}: idempotent no-op (already executed)")
            return action
        outcome = self.driver.execute(action, executor_token=self.executor_token)
        if not outcome.executed and action.mode is ResponseMode.APPROVED_LAB:
            # A driver that could not actually perform the side effect must not be marked VERIFIED.
            self._log(f"execute {action.action_id}: FAILED (driver did not perform action)")
            return self._transition(action, ActionStatus.FAILED)
        self._log(f"execute {action.action_id}: EXECUTED ({outcome.result_ref})")
        return self._transition(
            action.model_copy(update={"result_ref": outcome.result_ref}), ActionStatus.EXECUTED
        )

    def dry_run(self, action: ResponseAction) -> ResponseAction:
        """Record a dry-run proposal annotation; never a side effect, allowed on any track."""
        outcome = self.driver.execute(
            action.model_copy(update={"mode": ResponseMode.DRY_RUN}), executor_token=""
        )
        self._log(f"dry_run {action.action_id}: {outcome.result_ref}")
        return action
