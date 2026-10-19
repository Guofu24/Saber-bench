"""T030 security: the required failure tests for lab-only response actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from saber.domain.errors import IntegrationBlocked, InvalidTransition, PolicyDenied
from saber.domain.responses import (
    ActionKind,
    ActionStatus,
    ActionTarget,
    ResponseAction,
    ResponseMode,
)
from saber.domain.runs import Track
from saber.response import (
    ApprovalRecord,
    BlockedLabResponseDriver,
    DryRunResponseAdapter,
    LabAssetRegistry,
    PolicyEngine,
    ResponseService,
)
from saber.response.driver import ExecutionOutcome
from saber.response.policy import action_hash


class _ExecutingDriver:
    """Test-only driver that reports a performed side effect (idempotency check)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, action: ResponseAction, *, executor_token: str) -> ExecutionOutcome:
        self.calls.append(str(action.action_id))
        return ExecutionOutcome(
            action_id=str(action.action_id),
            executed=True,
            result_ref=f"lab://done/{action.action_id}",
            rollback_ref="rb://1",
            note="performed",
        )

    def rollback(
        self, action: ResponseAction, rollback_ref: str, *, executor_token: str
    ) -> ExecutionOutcome:
        return ExecutionOutcome(
            action_id=str(action.action_id),
            executed=False,
            result_ref="rb",
            rollback_ref=rollback_ref,
            note="rolled back",
        )


NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
LAB = "lab-env-1"
EP = uuid4()
REGISTRY = LabAssetRegistry(
    lab_environment_id=LAB,
    hosts=frozenset({"lab-ws-01", "lab-ws-02", "lab-vip-01"}),
    addresses=frozenset({"198.51.100.5"}),
    accounts=frozenset({"labuser"}),
    protected_hosts=frozenset({"lab-vip-01"}),
)
AGENTS = frozenset({"ir-agent"})


def _action(
    host: str = "lab-ws-01",
    *,
    mode: ResponseMode = ResponseMode.APPROVED_LAB,
    kind: ActionKind = ActionKind.ISOLATE_LAB_HOST,
    evidence: bool = True,
) -> ResponseAction:
    return ResponseAction(
        action_id=uuid4(), episode_id=EP, kind=kind, target=ActionTarget(host_id=host),
        reason="confirmed beacon", supporting_evidence_ids=[uuid4()] if evidence else [],
        mode=mode, created_at=NOW, expires_at=NOW + timedelta(hours=1),
    )  # fmt: skip


def _approval(
    action: ResponseAction, operator: str = "operator:alice", env: str = LAB, ttl_hours: int = 1
) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=uuid4(), action_id=action.action_id, action_hash=action_hash(action),
        lab_environment_id=env, operator_id=operator, approved_at=NOW,
        expires_at=NOW + timedelta(hours=ttl_hours),
    )  # fmt: skip


def _svc(track: Track = Track.RESPONSE_ENABLED, driver: object = None) -> ResponseService:
    return ResponseService(
        policy=PolicyEngine(REGISTRY, track=track, agent_ids=AGENTS),
        driver=driver or DryRunResponseAdapter(),
    )


@pytest.mark.security
def test_track_a_cannot_execute() -> None:
    svc = _svc(Track.DETECTION_ONLY)
    action = _action(mode=ResponseMode.APPROVED_LAB)
    proposed = svc.propose(action)
    assert proposed.status is ActionStatus.DENIED
    with pytest.raises(PolicyDenied):
        svc.execute(action, _approval(action), now=NOW)


@pytest.mark.security
def test_unapproved_proposal_cannot_execute() -> None:
    svc = _svc()
    action = _action()
    with pytest.raises(PolicyDenied):
        svc.execute(action, None, now=NOW)


@pytest.mark.security
def test_approval_for_host_a_cannot_execute_on_host_b() -> None:
    svc = _svc()
    action_a = _action("lab-ws-01")
    approval = _approval(action_a)
    action_b = _action("lab-ws-02")  # different target -> different hash
    with pytest.raises(PolicyDenied):
        svc.execute(action_b, approval, now=NOW)


@pytest.mark.security
def test_approval_after_ttl_rejected() -> None:
    svc = _svc()
    action = _action()
    approval = _approval(action, ttl_hours=1)
    with pytest.raises(PolicyDenied):
        svc.execute(action, approval, now=NOW + timedelta(hours=2))


@pytest.mark.security
def test_unregistered_and_protected_hosts_rejected() -> None:
    svc = _svc()
    unknown = _action("corp-dc-01")
    assert svc.propose(unknown).status is ActionStatus.DENIED
    vip = _action("lab-vip-01")  # protected: isolation not allowed
    assert svc.propose(vip).status is ActionStatus.DENIED
    collect = _action("lab-vip-01", kind=ActionKind.COLLECT_EVIDENCE, evidence=False)
    ok, _ = svc.policy.evaluate_proposal(collect)
    assert ok  # evidence collection on a protected host is permitted


@pytest.mark.security
def test_agent_cannot_self_approve() -> None:
    svc = _svc()
    action = _action()
    with pytest.raises(PolicyDenied):
        svc.approve(action, _approval(action, operator="ir-agent"), now=NOW)
    with pytest.raises(PolicyDenied):
        svc.approve(action, _approval(action, operator="not-an-operator"), now=NOW)


@pytest.mark.security
def test_dry_run_has_no_side_effect() -> None:
    adapter = DryRunResponseAdapter()
    svc = _svc(driver=adapter)
    action = _action(mode=ResponseMode.DRY_RUN)
    svc.dry_run(action)
    assert adapter.recorded == [str(action.action_id)]


@pytest.mark.security
def test_lab_driver_is_blocked_integration() -> None:
    svc = _svc(driver=BlockedLabResponseDriver(lab_environment_id=LAB))
    action = _action()
    approval = _approval(action)
    result = svc.approve(action, approval, now=NOW)
    assert result.status is ActionStatus.APPROVED
    with pytest.raises(IntegrationBlocked):
        svc.execute(result, approval, now=NOW)


@pytest.mark.security
def test_duplicate_execution_is_idempotent() -> None:
    driver = _ExecutingDriver()
    svc = _svc(driver=driver)
    action = _action()
    approval = _approval(action)
    executed = svc.execute(
        action.model_copy(update={"status": ActionStatus.APPROVED}), approval, now=NOW
    )
    assert executed.status is ActionStatus.EXECUTED
    again = svc.execute(executed, approval, now=NOW)
    assert again.status is ActionStatus.EXECUTED  # no double apply
    assert driver.calls == [str(action.action_id)]  # driver invoked exactly once


@pytest.mark.security
def test_dry_run_driver_cannot_fake_lab_execution() -> None:
    # A dry-run driver must not mark an approved_lab action EXECUTED; it performed nothing.
    svc = _svc(driver=DryRunResponseAdapter())
    action = _action().model_copy(update={"status": ActionStatus.APPROVED})
    result = svc.execute(action, _approval(action), now=NOW)
    assert result.status is ActionStatus.FAILED


@pytest.mark.security
def test_invalid_state_transition_rejected() -> None:
    svc = _svc()
    action = _action()
    with pytest.raises(InvalidTransition):
        svc._transition(
            action.model_copy(update={"status": ActionStatus.VERIFIED}), ActionStatus.APPROVED
        )
