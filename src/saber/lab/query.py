"""Bounded hunt queries shared by SQLite evidence and indexed normalized fields."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Paths refer to the measured event envelope, not model-provided paths/SQL/DSL.
PATHS = {
    "principal": ("$.data.principal", "$.data.fields.TargetUserName"),
    "process_id": ("$.data.pid", "$.data.fields.ProcessId"),
    "command_line": ("$.data.command_line", "$.data.fields.CommandLine"),
    "event_code": ("$.data.event_id",),
    "source_ip": ('$.data."id.orig_h"', "$.data.fields.SourceIp", "$.data.fields.IpAddress"),
    "destination_ip": ('$.data."id.resp_h"', "$.data.fields.DestinationIp"),
    "domain": ("$.data.query", "$.data.fields.QueryName", "$.data.domain"),
    "sha256": ("$.data.sha256",),
    "path": ("$.data.path", "$.data.fields.TargetFilename", "$.data.fields.Image"),
    "job_id": ("$.data.job_id",),
    "status": ("$.data.status", "$.data.fields.Status"),
}


class Predicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    operator: Literal["eq", "contains"] = "eq"
    value: str = Field(min_length=1, max_length=256)

    @field_validator("field")
    @classmethod
    def allowed(cls, value: str) -> str:
        if value not in PATHS:
            raise ValueError("Unknown evidence field")
        return value


class Search(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    kind: str | None = Field(default=None, max_length=64)
    before: str | None = None
    after: str | None = None
    cursor: tuple[str, str] | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    filters: list[Predicate] = Field(default_factory=list, max_length=8)

    @field_validator("before", "after")
    @classmethod
    def timestamp(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            raise ValueError("Timestamp requires timezone")
        return stamp.astimezone(UTC).isoformat(timespec="milliseconds")

    @field_validator("cursor")
    @classmethod
    def cursor_format(cls, value: tuple[str, str] | None) -> tuple[str, str] | None:
        import re

        if value is None:
            return None
        stamp = cls.timestamp(value[0])
        if stamp is None or not re.fullmatch(r"[a-f0-9-]{32,36}", value[1]):
            raise ValueError("Invalid continuation cursor")
        return stamp, value[1]

    @model_validator(mode="after")
    def window(self) -> Search:
        if self.before and self.after and self.after > self.before:
            raise ValueError("Invalid time window")
        return self


def sql_predicates(filters: list[Predicate]) -> tuple[str, list[Any]]:
    clauses, values = [], []
    for item in filters:
        paths = PATHS[item.field]
        parts = [f"json_extract(data, '{path}')" for path in paths]
        expression = parts[0] if len(parts) == 1 else "coalesce(" + ",".join(parts) + ")"
        expression = f"lower(CAST({expression} AS TEXT))"
        clauses.append(f"{expression}=?" if item.operator == "eq" else f"instr({expression},?)>0")
        values.append(item.value.lower())
    return " AND ".join(clauses), values


def normalized(event: dict[str, Any]) -> dict[str, str]:
    result = {}
    for field, paths in PATHS.items():
        for path in paths:
            # All paths come from PATHS; quoted names preserve Zeek dotted keys.
            import re

            keys = re.findall(r'\."([^"]+)"|\.([A-Za-z0-9_]+)', path)
            value: Any = event
            for quoted, plain in keys:
                value = value.get(quoted or plain) if isinstance(value, dict) else None
            if value is not None and not isinstance(value, (dict, list)):
                result[field] = str(value).lower()
                break
    return result


def backend_predicates(filters: list[Predicate]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in filters:
        field = "fields." + item.field
        if item.operator == "eq":
            result.append({"term": {field: item.value.lower()}})
        else:
            literal = (
                item.value.lower().replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")
            )
            result.append({"wildcard": {field: {"value": "*" + literal + "*"}}})
    return result


def public_event(document: dict[str, Any]) -> dict[str, Any]:
    # Derived index fields never enter a raw-evidence hash.
    return {k: v for k, v in document.items() if k != "fields"}
