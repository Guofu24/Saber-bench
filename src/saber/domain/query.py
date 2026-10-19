"""Constrained EventQuery DSL. LLM-facing request has no as_of and no raw backend DSL."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from saber.domain.base import HostId, StrictModel, UtcDatetime
from saber.domain.events import EventCategory, NormalizedEvent

MAX_PAGE_SIZE = 100
MAX_FILTERS = 10
MAX_HOSTS = 50
MAX_IN_VALUES = 50
MAX_TIME_RANGE = timedelta(days=31)
MAX_VALUE_LENGTH = 512

ALLOWED_FILTER_FIELDS: frozenset[str] = frozenset(
    {
        "host_id", "source", "category", "action",
        "process.name", "process.pid", "process.parent_pid", "process.parent_name",
        "process.command_line", "process.image_path", "process.sha256", "process.user",
        "user.id", "user.name", "user.domain",
        "network.src_ip", "network.src_port", "network.dst_ip", "network.dst_port",
        "network.protocol", "network.direction", "network.domain",
        "file.path", "file.name", "file.sha256",
        "attributes.rule_id", "attributes.rule_name", "attributes.event_code",
        "attributes.logon_type", "attributes.status", "attributes.message", "attributes.url",
        "attributes.user_agent", "attributes.severity", "attributes.alert_id", "attributes.case_id",
    }
)  # fmt: skip
CONTAINS_FIELDS: frozenset[str] = frozenset(
    {
        "process.command_line", "process.image_path", "file.path", "attributes.message",
        "attributes.url", "attributes.user_agent", "attributes.rule_name",
    }
)  # fmt: skip


class FilterOperator(StrEnum):
    EQ = "eq"
    IN = "in"
    GTE = "gte"
    LTE = "lte"
    CONTAINS = "contains"


FilterScalar = str | int | float | bool


class EventFilter(StrictModel):
    field: str = Field(min_length=1, max_length=64)
    operator: FilterOperator
    value: FilterScalar | list[FilterScalar]

    @field_validator("field")
    @classmethod
    def _allowlisted(cls, value: str) -> str:
        if value not in ALLOWED_FILTER_FIELDS:
            raise ValueError(f"filter field {value!r} is not allowlisted")
        return value

    @model_validator(mode="after")
    def _operator_rules(self) -> EventFilter:
        if self.operator is FilterOperator.IN:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("operator in requires a non-empty list")
            if len(self.value) > MAX_IN_VALUES:
                raise ValueError(f"operator in accepts at most {MAX_IN_VALUES} values")
        elif isinstance(self.value, list):
            raise ValueError(f"operator {self.operator.value} requires a scalar value")
        if self.operator is FilterOperator.CONTAINS:
            if self.field not in CONTAINS_FIELDS:
                raise ValueError(f"contains is not permitted on field {self.field!r}")
            if not isinstance(self.value, str):
                raise ValueError("contains requires a string value")
        values = self.value if isinstance(self.value, list) else [self.value]
        for item in values:
            if isinstance(item, str) and len(item) > MAX_VALUE_LENGTH:
                raise ValueError("filter value too long")
        return self


class EventQueryRequest(StrictModel):
    """What an agent/tool may send. episode_id and as_of are bound server-side."""

    time_from: UtcDatetime | None = None
    time_to: UtcDatetime | None = None
    hosts: list[HostId] = Field(default_factory=list, max_length=MAX_HOSTS)
    categories: list[EventCategory] = Field(default_factory=list, max_length=20)
    filters: list[EventFilter] = Field(default_factory=list, max_length=MAX_FILTERS)
    limit: int = Field(default=50, ge=1, le=MAX_PAGE_SIZE)
    cursor: str | None = Field(default=None, max_length=1024)
    order: Literal["asc", "desc"] = "asc"

    @model_validator(mode="after")
    def _window(self) -> EventQueryRequest:
        if self.time_from and self.time_to:
            if self.time_to < self.time_from:
                raise ValueError("time_to precedes time_from")
            if self.time_to - self.time_from > MAX_TIME_RANGE:
                raise ValueError("time range exceeds maximum window")
        return self


class ResolvedEventQuery(EventQueryRequest):
    """Internal gateway representation after binding identity and benchmark clock."""

    episode_id: UUID
    as_of: UtcDatetime

    @model_validator(mode="after")
    def _no_future(self) -> ResolvedEventQuery:
        if self.time_to is not None and self.time_to > self.as_of:
            raise ValueError("time_to is after as_of (future window denied)")
        if self.time_from is not None and self.time_from > self.as_of:
            raise ValueError("time_from is after as_of (future window denied)")
        return self


class EventPage(StrictModel):
    events: list[NormalizedEvent]
    next_cursor: str | None = None
    as_of: UtcDatetime
    scanned: int = Field(ge=0)
    truncated: bool = False
