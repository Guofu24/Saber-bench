"""Environment inventory and capability decision matrix (environment-first policy).

Reads an operator-provided ``config/existing-environment.json`` (if present) and classifies each
required capability as reuse / adapt / install / block. It performs no network access and never
reads secret *values* (only env-var names). Absent inventory means offline-only: every external
capability is BLOCKED_INTEGRATION, which is the safe default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from saber.catalog.loader import repo_root


class Decision(StrEnum):
    REUSE = "reuse"
    ADAPT = "adapt"
    INSTALL = "install"
    BLOCK = "block"


REQUIRED_CAPABILITIES = (
    "telemetry_search",
    "raw_object_store",
    "case_engine",
    "host_virtualization",
    "rule_testing",
    "emulation",
    "llm_provider",
)

# Which capabilities can be satisfied offline (DEV) vs. require real external infrastructure.
_DEV_SATISFIED = {
    "telemetry_search": "FakeEventStore (in-memory, visibility-aware)",
    "raw_object_store": "local content-addressed dir (dev)",
    "case_engine": "in-memory case/finding DTOs (dev)",
    "rule_testing": "sandboxed regex / yara-subset engines (dev)",
    "llm_provider": "deterministic stub provider (dev)",
}
_LAB_ONLY = {
    "host_virtualization": "requires an approved isolated hypervisor lab (Proxmox or equivalent)",
    "emulation": "requires operator-approved, allowlisted emulation in an isolated lab",
}


@dataclass(frozen=True)
class ServiceInventory:
    capability: str
    name: str
    api_base_url: str
    credential_env_name: str | None
    approved_for_read_only_use: bool
    health_check_path: str | None


@dataclass(frozen=True)
class CapabilityDecision:
    capability: str
    decision: Decision
    rationale: str
    existing_candidate: str | None = None


@dataclass(frozen=True)
class EnvironmentInventory:
    services: tuple[ServiceInventory, ...]
    allow_project_local_dependency_install: bool
    allow_privileged_host_install: bool
    allow_new_vm_provision: bool
    allow_attack_emulation: bool
    allow_stateful_response: bool
    raw: dict[str, Any]

    @property
    def present(self) -> bool:
        return bool(self.raw)


def load_inventory(root: Path | None = None) -> EnvironmentInventory:
    base = root or repo_root()
    path = base / "config" / "existing-environment.json"
    if not path.is_file():
        return EnvironmentInventory((), True, False, False, False, False, {})
    data = json.loads(path.read_text(encoding="utf-8"))
    services = tuple(
        ServiceInventory(
            capability=str(s.get("capability", "unknown")),
            name=str(s.get("name", "")),
            api_base_url=str(s.get("api_base_url", "")),
            credential_env_name=s.get("credential_env_name"),
            approved_for_read_only_use=bool(s.get("approved_for_read_only_use", False)),
            health_check_path=s.get("health_check_path"),
        )
        for s in data.get("services", [])
    )
    return EnvironmentInventory(
        services=services,
        allow_project_local_dependency_install=bool(
            data.get("allow_project_local_dependency_install", True)
        ),
        allow_privileged_host_install=bool(data.get("allow_privileged_host_install", False)),
        allow_new_vm_provision=bool(data.get("allow_new_vm_provision", False)),
        allow_attack_emulation=bool(data.get("allow_attack_emulation", False)),
        allow_stateful_response=bool(data.get("allow_stateful_response", False)),
        raw=data,
    )


def capability_matrix(inventory: EnvironmentInventory | None = None) -> list[CapabilityDecision]:
    inv = inventory or load_inventory()
    approved = {s.capability: s for s in inv.services if s.approved_for_read_only_use}
    decisions: list[CapabilityDecision] = []
    for cap in REQUIRED_CAPABILITIES:
        service = approved.get(cap) or _match_capability(cap, approved)
        if service is not None:
            decisions.append(
                CapabilityDecision(
                    cap,
                    Decision.ADAPT,
                    f"adapt approved service {service.name!r} ({service.api_base_url})",
                    service.name,
                )
            )
        elif cap in _DEV_SATISFIED:
            decisions.append(
                CapabilityDecision(
                    cap, Decision.REUSE, f"satisfied in DEV by {_DEV_SATISFIED[cap]}"
                )
            )
        else:
            decisions.append(
                CapabilityDecision(
                    cap,
                    Decision.BLOCK,
                    f"BLOCKED_INTEGRATION: {_LAB_ONLY.get(cap, 'no approved provider')}",
                )
            )
    return decisions


_CAP_ALIASES = {
    "telemetry_search": {"siem", "opensearch", "elasticsearch", "wazuh_indexer", "log_search"},
    "raw_object_store": {"object_store", "minio", "s3"},
    "case_engine": {"soar", "case_management", "ticketing"},
    "host_virtualization": {"hypervisor", "proxmox", "vmware", "kvm"},
    "rule_testing": {"sigma", "yara", "suricata"},
    "emulation": {"attack_emulation", "caldera", "atomic"},
    "llm_provider": {"llm", "anthropic", "openai"},
}


def _match_capability(cap: str, approved: dict[str, ServiceInventory]) -> ServiceInventory | None:
    aliases = _CAP_ALIASES.get(cap, set())
    for key, service in approved.items():
        if key.lower() in aliases or service.capability.lower() in aliases:
            return service
    return None
