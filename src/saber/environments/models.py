"""Secret-free deployment configuration; selecting a profile never provisions a host."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from saber.world.models import WorldConfig, default_config

ProfileName = Literal["local", "sandbox", "vm", "remote"]


class Service(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    capability: Literal["siem", "soar", "cases", "edr", "cti", "storage", "other"]
    api_base_url: str
    health_check_path: str = "/health"
    credential_env_name: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    approved_for_read_only_use: bool = False

    @field_validator("api_base_url")
    @classmethod
    def endpoint_without_secrets(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            port = parts.port
        except ValueError:
            raise ValueError("Invalid service URL.") from None
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or any(c.isspace() or ord(c) < 32 for c in value)
            or "\\" in value
            or (port is not None and port == 0)
        ):
            raise ValueError("Use an HTTP(S) URL without credentials, query or fragment.")
        return value.rstrip("/")

    @field_validator("health_check_path")
    @classmethod
    def relative_health_path(cls, value: str) -> str:
        if not re.fullmatch(r"/[a-zA-Z0-9_./-]*", value) or ".." in value or "//" in value:
            raise ValueError("Health path must be an absolute path on the configured service.")
        return value


class Resources(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_mb: int = Field(default=2048, ge=512, le=131072)
    cpus: float = Field(default=2.0, ge=0.25, le=64, allow_inf_nan=False)
    pids: int = Field(default=256, ge=64, le=4096)


class EnvironmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    profile: ProfileName
    world: WorldConfig = Field(default_factory=default_config)
    resources: Resources = Field(default_factory=Resources)
    services: list[Service] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def unique_services(self) -> EnvironmentConfig:
        names = [s.name for s in self.services]
        if len(names) != len(set(names)):
            raise ValueError("Service names must be unique.")
        return self


def read_config(path: Path) -> EnvironmentConfig:
    return EnvironmentConfig.model_validate_json(path.read_text(encoding="utf-8-sig"))
