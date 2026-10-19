"""Normalized error hierarchy. API layers render `code`, `message`, `trace_id` only."""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4


class ErrorCode(StrEnum):
    VALIDATION = "validation_error"
    POLICY_DENIED = "policy_denied"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    INVALID_TRANSITION = "invalid_transition"
    TIME_LEAK_DENIED = "time_leak_denied"
    CROSS_EPISODE_DENIED = "cross_episode_denied"
    BUDGET_EXCEEDED = "budget_exceeded"
    TRUTH_ACCESS_DENIED = "truth_access_denied"
    INTEGRATION_BLOCKED = "integration_blocked"
    SANDBOX_FAILURE = "sandbox_failure"
    INTERNAL = "internal_error"


class SaberError(Exception):
    code: ErrorCode = ErrorCode.INTERNAL
    http_status: int = 500

    def __init__(self, message: str, *, trace_id: str | None = None, **context: object) -> None:
        super().__init__(message)
        self.message = message
        self.trace_id = trace_id or uuid4().hex
        self.context = context

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message, "trace_id": self.trace_id}


class ValidationError(SaberError):
    code = ErrorCode.VALIDATION
    http_status = 422


class PolicyDenied(SaberError):
    code = ErrorCode.POLICY_DENIED
    http_status = 403


class TimeLeakDenied(PolicyDenied):
    code = ErrorCode.TIME_LEAK_DENIED


class CrossEpisodeDenied(PolicyDenied):
    code = ErrorCode.CROSS_EPISODE_DENIED


class TruthAccessDenied(PolicyDenied):
    code = ErrorCode.TRUTH_ACCESS_DENIED


class BudgetExceeded(SaberError):
    code = ErrorCode.BUDGET_EXCEEDED
    http_status = 429


class NotFound(SaberError):
    code = ErrorCode.NOT_FOUND
    http_status = 404


class Conflict(SaberError):
    code = ErrorCode.CONFLICT
    http_status = 409


class InvalidTransition(SaberError):
    code = ErrorCode.INVALID_TRANSITION
    http_status = 409


class IntegrationBlocked(SaberError):
    """Raised by adapters whose real backend is unavailable/unauthorized in this environment."""

    code = ErrorCode.INTEGRATION_BLOCKED
    http_status = 503


class SandboxFailure(SaberError):
    code = ErrorCode.SANDBOX_FAILURE
    http_status = 500
