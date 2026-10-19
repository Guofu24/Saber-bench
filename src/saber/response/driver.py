"""Response drivers. Dry-run records proposals with no side effects; the lab driver is blocked."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from saber.domain.errors import IntegrationBlocked
from saber.domain.responses import ResponseAction


@dataclass(frozen=True)
class ExecutionOutcome:
    action_id: str
    executed: bool
    result_ref: str
    rollback_ref: str | None
    note: str


@runtime_checkable
class ResponseDriver(Protocol):
    def execute(self, action: ResponseAction, *, executor_token: str) -> ExecutionOutcome: ...

    def rollback(
        self, action: ResponseAction, rollback_ref: str, *, executor_token: str
    ) -> ExecutionOutcome: ...


@dataclass
class DryRunResponseAdapter:
    """Records what *would* happen. Never touches a host; safe for DETECTION_ONLY and dev."""

    recorded: list[str] = field(default_factory=list)

    def execute(self, action: ResponseAction, *, executor_token: str) -> ExecutionOutcome:
        self.recorded.append(str(action.action_id))
        return ExecutionOutcome(
            action_id=str(action.action_id),
            executed=False,
            result_ref=f"dryrun://{action.kind.value}/{action.action_id}",
            rollback_ref=None,
            note="dry-run proposal recorded; no side effect performed",
        )

    def rollback(
        self, action: ResponseAction, rollback_ref: str, *, executor_token: str
    ) -> ExecutionOutcome:
        return ExecutionOutcome(
            action_id=str(action.action_id),
            executed=False,
            result_ref=f"dryrun-rollback://{action.action_id}",
            rollback_ref=rollback_ref,
            note="dry-run rollback recorded",
        )


@dataclass
class BlockedLabResponseDriver:
    """Real lab side-effect driver. Fails closed until an isolated lab and H4 gate exist."""

    lab_environment_id: str

    def execute(self, action: ResponseAction, *, executor_token: str) -> ExecutionOutcome:
        raise IntegrationBlocked(
            "lab response execution is BLOCKED_INTEGRATION: requires an approved isolated lab "
            "(SECURITY.md H2/H4), a verified snapshot and an operator-held executor token",
            lab_environment_id=self.lab_environment_id,
            action_id=str(action.action_id),
        )

    def rollback(
        self, action: ResponseAction, rollback_ref: str, *, executor_token: str
    ) -> ExecutionOutcome:
        raise IntegrationBlocked(
            "lab rollback is BLOCKED_INTEGRATION until a lab is approved",
            lab_environment_id=self.lab_environment_id,
            action_id=str(action.action_id),
        )
