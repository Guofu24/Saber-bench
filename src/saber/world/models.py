"""Configuration and strict action contracts for the continuous world."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saber.agents.specialties import BLUE_SKILLS, DEFAULT_BLUE_ROLES
from saber.forensics.tools import allowed as forensic_tools
from saber.world.lab_tools import ARTIFACT_TOOLS, RULE_TOOLS
from saber.world.operations import CASE_TOOLS, READ_TOOLS
from saber.world.work import LEAD_TOOLS, PERSONAL_TOOLS, WORKER_TOOLS

Team = Literal["client", "red", "blue"]
BLUE_ROLES = tuple(BLUE_SKILLS)
RED_ROLES = ("recon", "access", "impact")
CLIENT_ROLES = ("person", "employee", "developer", "administrator")


class Actor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    team: Team
    role: str = Field(min_length=1, max_length=80)
    goal: str = Field(default="", max_length=500)
    interval_ticks: int = Field(default=1, ge=1, le=10000)
    specialties: tuple[str, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def role_matches_team(self) -> Actor:
        if self.specialties and (
            self.team != "blue" or any(s not in BLUE_SKILLS for s in self.specialties)
        ):
            raise ValueError("additional specialties must be known blue capabilities")
        if len(set(self.specialties)) != len(self.specialties):
            raise ValueError("duplicate specialties")
        if self.team == "blue" and self.role not in BLUE_ROLES:
            raise ValueError(f"blue role must be one of {BLUE_ROLES}")
        if self.team == "red" and self.role not in RED_ROLES:
            raise ValueError(f"red role must be one of {RED_ROLES}")
        return self


class WorldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed: int = 42
    execution_mode: Literal["application", "native", "range"] = "application"
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
    learning_enabled: bool = True
    learning_interval_ticks: int = Field(default=30, ge=1, le=100000)

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
        for r in DEFAULT_BLUE_ROLES
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
    {
        "browse",
        "search",
        "login",
        "read_document",
        "collect",
        "exfiltrate",
        "register_job",
        "disrupt",
        "share",
    }
)
BLUE_TOOLS = {
    "lead": frozenset({"open_case", "assign", "notify", "close_case", "share", "verify_recovery"}),
    "monitor": frozenset({"open_case", "share"}),
    "hunter": frozenset({"open_case", "share"}),
    "dfir": frozenset({"investigate", "share"}) | ARTIFACT_TOOLS,
    "content": frozenset({"deploy_rule", "patch", "share"}) | RULE_TOOLS,
    "malware": frozenset({"share"}) | ARTIFACT_TOOLS,
    "network": frozenset({"investigate", "share"}) | ARTIFACT_TOOLS,
    "intel": frozenset({"share"}) | ARTIFACT_TOOLS,
    "platform": frozenset({"share"}),
    "identity": frozenset({"investigate", "share"}) | ARTIFACT_TOOLS,
    "recovery": frozenset({"share", "verify_recovery"}),
    "ir": frozenset(
        {
            "contain",
            "quarantine",
            "unquarantine",
            "restore",
            "release",
            "notify",
            "share",
            "verify_recovery",
        }
    ),
}


def tools_for(actor: Actor) -> frozenset[str]:
    if actor.team == "client":
        return CLIENT_TOOLS | PERSONAL_TOOLS | {"consult_skill"}
    if actor.team == "red":
        return RED_TOOLS | PERSONAL_TOOLS | {"consult_skill"}
    return (
        frozenset().union(*(BLUE_TOOLS[s] for s in specialties_for(actor)))
        | READ_TOOLS
        | forensic_tools(actor.team, actor.role, actor.specialties)
        | CASE_TOOLS
        | {"telemetry_health", "consult_skill"}
        | PERSONAL_TOOLS
        | WORKER_TOOLS
        | ({"reopen_case", *LEAD_TOOLS} if "lead" in specialties_for(actor) else set())
    )


def specialties_for(actor: Actor) -> tuple[str, ...]:
    return tuple(dict.fromkeys((actor.role, *actor.specialties))) if actor.team == "blue" else ()


def safe_name(value: Any) -> str:
    name = str(value)
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", name) or name.startswith("."):
        raise ValueError("invalid resource name")
    return name
