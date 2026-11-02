"""Versioned, secret-free specifications for the three SOC lab sizes."""

from __future__ import annotations

import ipaddress
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saber.lab.analyzers import AnalysisSettings
from saber.lab.soar import SoarSettings
from saber.world.models import Actor, default_config

Preset = Literal["linux-small", "windows-ad", "expanded"]


class WindowsNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,14}$")
    address: str
    role: Literal["dc", "workstation", "member-server"]
    memory_gb: int = Field(ge=4, le=64)
    cpus: int = Field(default=2, ge=2, le=16)


class LabSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    name: str = Field(default="saber-soc", pattern=r"^[a-z][a-z0-9-]{0,31}$")
    preset: Preset
    actors: list[Actor]
    host_ram_gb: int = Field(ge=16, le=1024)
    host_cpus: int = Field(ge=4, le=128)
    disk_gb: int = Field(ge=100, le=10000)
    workers_per_team: int = Field(default=1, ge=1, le=16)
    tick_seconds: float = Field(default=5, ge=0.1, le=3600)
    retention_days: int = Field(default=7, ge=1, le=365)
    evidence_budget_mb: int = Field(default=4096, ge=64, le=1048576)
    learning_enabled: bool = True
    learning_interval_ticks: int = Field(default=30, ge=1, le=100000)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    soar: SoarSettings = Field(default_factory=SoarSettings)
    domain: str = Field(default="saber.test", pattern=r"^[a-z][a-z0-9-]{0,30}\.test$")
    windows_subnet: str = "172.28.80.0/24"
    windows: list[WindowsNode] = Field(default_factory=list, max_length=24)
    # Pinned versions deliberately independent of vendor 'latest' tags.
    opensearch_version: Literal["3.3.2"] = "3.3.2"
    playwright_version: Literal["1.56.0"] = "1.56.0"

    @model_validator(mode="after")
    def coherent(self) -> LabSpec:
        ids = [a.id for a in self.actors]
        if not 1 <= len(ids) <= 200 or len(ids) != len(set(ids)):
            raise ValueError("Roster must contain 1..200 unique actors")
        subnet = ipaddress.ip_network(self.windows_subnet, strict=True)
        if subnet.version != 4 or not subnet.is_private or subnet.prefixlen != 24:
            raise ValueError("Windows lab needs a private IPv4 /24")
        addresses = []
        for node in self.windows:
            address = ipaddress.ip_address(node.address)
            if address not in subnet or address in (
                subnet.network_address,
                subnet.broadcast_address,
                subnet.network_address + 1,
            ):
                raise ValueError("Windows address outside lab or reserved for host")
            addresses.append(address)
        if len(set(addresses)) != len(addresses) or len({n.name for n in self.windows}) != len(
            self.windows
        ):
            raise ValueError("Duplicate Windows host/address")
        if self.preset == "linux-small" and self.windows:
            raise ValueError("linux-small does not provision Windows")
        if self.preset != "linux-small" and sum(n.role == "dc" for n in self.windows) != 1:
            raise ValueError("Exactly one forest-root domain controller is required")
        containers_and_host = math.ceil(
            13.25
            + 6 * self.workers_per_team
            + (self.analysis.memory_gb if self.analysis.enabled else 0)
            + (0.5 if self.soar.enabled else 0)
        )
        if sum(n.memory_gb for n in self.windows) + containers_and_host > self.host_ram_gb:
            raise ValueError("Host RAM cannot fit guests plus control/SOC services")
        return self


def preset_spec(preset: Preset, name: str = "saber-soc") -> LabSpec:
    sizes = {
        "linux-small": (32, 6, 250, 2, 1),
        "windows-ad": (64, 8, 500, 4, 1),
        "expanded": (128, 16, 1000, 12, 3),
    }
    ram, cpu, disk, clients, workers = sizes[preset]
    windows = []
    if preset != "linux-small":
        windows = [WindowsNode(name="soc-dc", address="172.28.80.10", role="dc", memory_gb=4)]
        for i in range(2 if preset == "windows-ad" else 6):
            windows.append(
                WindowsNode(
                    name=f"soc-ws-{i + 1}",
                    address=f"172.28.80.{20 + i}",
                    role="workstation",
                    memory_gb=8,
                )
            )
        windows.append(
            WindowsNode(name="soc-files", address="172.28.80.40", role="member-server", memory_gb=4)
        )
    return LabSpec(
        name=name,
        preset=preset,
        host_ram_gb=ram,
        host_cpus=cpu,
        disk_gb=disk,
        actors=default_config(clients).actors,
        windows=windows,
        workers_per_team=workers,
    )
