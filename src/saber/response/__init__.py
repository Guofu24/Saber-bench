"""Incident-response layer (T030): policy, approvals, dry-run adapter, state machine.

Defaults are safe: DETECTION_ONLY forbids all side effects; action mode defaults to dry_run; an
IR agent can never approve its own action; approval binds the exact action hash, target, lab
environment and TTL; execution needs an executor token no agent holds. The real lab side-effect
driver is BLOCKED_INTEGRATION until the H4 lab gate.
"""

from saber.response.driver import BlockedLabResponseDriver, DryRunResponseAdapter, ResponseDriver
from saber.response.policy import ApprovalRecord, LabAssetRegistry, PolicyEngine
from saber.response.service import ResponseService

__all__ = [
    "ApprovalRecord",
    "BlockedLabResponseDriver",
    "DryRunResponseAdapter",
    "LabAssetRegistry",
    "PolicyEngine",
    "ResponseDriver",
    "ResponseService",
]
