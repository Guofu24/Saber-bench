"""Configuration and strict action contracts for the continuous world."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Team = Literal["client", "red", "blue"]
BLUE_ROLES = ("lead", "monitor", "hunter", "dfir", "content", "ir")
RED_ROLES = ("recon", "access", "impact")
CLIENT_ROLES = ("person", "employee", "developer", "administrator")


class Actor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    team: Team
    role: str = Field(min_length=1, max_length=80)
    goal: str = Field(default="", max_length=500)
    interval_ticks: int = Field(default=1, ge=1, le=10000)

    @model_validator(mode="after")
    def role_matches_team(self) -> Actor:
        if self.team == "blue" and self.role not in BLUE_ROLES:
            raise ValueError(f"blue role must be one of {BLUE_ROLES}")
        if self.team == "red" and self.role not in RED_ROLES:
            raise ValueError(f"red role must be one of {RED_ROLES}")
        return self


class WorldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed: int = 42
    tick_seconds: float = Field(default=2.0, ge=0.01, le=3600)
    actors: list[Actor] = Field(min_length=1, max_length=200)
    red_start_tick: int = Field(default=8, ge=1)
    response_ttl_ticks: int = Field(default=12, ge=1, le=10000)
    incident_ttl_ticks: int = Field(default=6, ge=1, le=1000)
    profile_refresh_ticks: int = Field(default=30, ge=1, le=100000)
    llm_workers: int = Field(default=4, ge=1, le=16)
    telemetry_window: int = Field(default=200, ge=10, le=2000)
    retention_events: int = Field(default=20000, ge=100, le=1000000)
    archive_bytes: int = Field(default=32_000_000, ge=10000)
    disk_budget_bytes: int = Field(default=512_000_000, ge=1_000_000)

    @model_validator(mode="after")
    def unique_ids(self) -> WorldConfig:
        ids = [a.id for a in self.actors]
        if len(set(ids)) != len(ids):
            raise ValueError("actor ids must be unique")
        return self


def default_config(clients: int = 6, seed: int = 42) -> WorldConfig:
    if not 1 <= clients <= 100:
        raise ValueError("clients must be between 1 and 100")
    actors = [
        Actor(
            id=f"client-{i + 1}",
            team="client",
            role=CLIENT_ROLES[i % len(CLIENT_ROLES)],
            goal="Carry out ordinary work and react to errors or security notifications.",
        )
        for i in range(clients)
    ]
    actors += [
        Actor(
            id=f"red-{r}",
            team="red",
            role=r,
            interval_ticks=2,
            goal="Discover and test weaknesses in this local application only.",
        )
        for r in RED_ROLES
    ]
    actors += [
        Actor(
            id=f"blue-{r}",
            team="blue",
            role=r,
            goal="Protect users, investigate evidence and minimize disruption.",
        )
        for r in BLUE_ROLES
    ]
    return WorldConfig(actors=actors, seed=seed)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = Field(pattern=r"^[a-z_]{1,40}$")
    args: dict[str, Any] = Field(default_factory=dict)


CLIENT_TOOLS = frozenset(
    {
        "browse",
        "search",
        "login",
        "read_document",
        "write_document",
        "call_app",
        "maintain",
        "acknowledge",
    }
)
RED_TOOLS = frozenset(
    {"browse", "search", "login", "read_document", "collect", "register_job", "disrupt", "share"}
)
BLUE_TOOLS = {
    "lead": frozenset({"open_case", "assign", "notify", "close_case", "share"}),
    "monitor": frozenset({"open_case", "share"}),
    "hunter": frozenset({"open_case", "share"}),
    "dfir": frozenset({"investigate", "share"}),
    "content": frozenset({"deploy_rule", "patch", "share"}),
    "ir": frozenset(
        {"contain", "quarantine", "unquarantine", "restore", "release", "notify", "share"}
    ),
}


def tools_for(actor: Actor) -> frozenset[str]:
    if actor.team == "client":
        return CLIENT_TOOLS
    if actor.team == "red":
        return RED_TOOLS
    return BLUE_TOOLS[actor.role]


def safe_name(value: Any) -> str:
    name = str(value)
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", name) or name.startswith("."):
        raise ValueError("invalid resource name")
    return name
