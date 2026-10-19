"""Shared model configuration, scalar types and validators."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID, uuid5

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

SABER_NAMESPACE = UUID("5a6e7c3a-0b7e-4d0b-9c2f-5abe7f1d2026")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SUBTASK_ID_RE = re.compile(r"^T\d{4}\.\d{3}$")
NICE_ID_RE = re.compile(r"^T\d{4}$")
# Shell / template metacharacters that must never appear in action targets or paths.
SHELL_META_RE = re.compile(r"[;&|`$<>\n\r]|\$\(|\{\{|\}\}")


class StrictModel(BaseModel):
    """Base for every wire DTO: unknown fields rejected, whitespace stripped."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        populate_by_name=True,
        use_enum_values=False,
    )


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-naive datetime rejected; supply an aware UTC timestamp")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]
Sha256Hex = Annotated[str, StringConstraints(pattern=SHA256_RE.pattern, to_lower=True)]
SubtaskId = Annotated[str, StringConstraints(pattern=SUBTASK_ID_RE.pattern)]
NiceId = Annotated[str, StringConstraints(pattern=NICE_ID_RE.pattern)]
ShortStr = Annotated[str, StringConstraints(min_length=1, max_length=256)]
HostId = Annotated[
    str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
]
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[Any] | dict[str, Any]


def deterministic_uuid(*parts: str) -> UUID:
    """Stable UUID5 for fixtures and seeded episodes (never for secrets)."""
    return uuid5(SABER_NAMESPACE, "\x1f".join(parts))


def reject_shell_metacharacters(value: str) -> str:
    if SHELL_META_RE.search(value):
        raise ValueError("shell/template metacharacters are not permitted in this field")
    return value


SafeStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=512),
    AfterValidator(reject_shell_metacharacters),
]
