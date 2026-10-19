"""NormalizedEvent and EvidenceRef (minimal OCSF-inspired internal subset)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from saber.domain.base import HostId, JsonValue, Sha256Hex, ShortStr, StrictModel, UtcDatetime


class EventSource(StrEnum):
    WINDOWS_SYSMON = "windows_sysmon"
    WINDOWS_SECURITY = "windows_security"
    LINUX_AUDITD = "linux_auditd"
    LINUX_AUTH = "linux_auth"
    LINUX_SYSLOG = "linux_syslog"
    WEB_ACCESS = "web_access"
    WAF = "waf"
    FIREWALL = "firewall"
    PROXY = "proxy"
    VPN = "vpn"
    DNS = "dns"
    NETFLOW = "netflow"
    IDS = "ids"
    EDR = "edr"
    ANTIVIRUS = "antivirus"
    EMAIL = "email"
    CLOUD = "cloud"
    APP_DB = "app_db"
    SIEM_ALERT = "siem_alert"
    CASE_SYSTEM = "case_system"
    GENERIC = "generic"


class EventCategory(StrEnum):
    PROCESS_ACTIVITY = "process_activity"
    AUTHENTICATION = "authentication"
    NETWORK_CONNECTION = "network_connection"
    FILE_ACTIVITY = "file_activity"
    REGISTRY = "registry"
    SERVICE = "service"
    SCHEDULED_TASK = "scheduled_task"
    DNS_QUERY = "dns_query"
    HTTP_REQUEST = "http_request"
    ALERT = "alert"
    EMAIL = "email"
    CONFIGURATION = "configuration"
    SYSTEM = "system"
    CASE = "case"
    OTHER = "other"


class ProcessInfo(StrictModel):
    name: ShortStr | None = None
    pid: int | None = Field(default=None, ge=0)
    parent_pid: int | None = Field(default=None, ge=0)
    parent_name: ShortStr | None = None
    command_line: str | None = Field(default=None, max_length=8192)
    image_path: str | None = Field(default=None, max_length=1024)
    sha256: Sha256Hex | None = None
    user: ShortStr | None = None


class UserInfo(StrictModel):
    id: ShortStr | None = None
    name: ShortStr | None = None
    domain: ShortStr | None = None


class NetworkInfo(StrictModel):
    src_ip: ShortStr | None = None
    src_port: int | None = Field(default=None, ge=0, le=65535)
    dst_ip: ShortStr | None = None
    dst_port: int | None = Field(default=None, ge=0, le=65535)
    protocol: ShortStr | None = None
    direction: Literal["inbound", "outbound", "internal", "unknown"] | None = None
    bytes_out: int | None = Field(default=None, ge=0)
    bytes_in: int | None = Field(default=None, ge=0)
    domain: ShortStr | None = None


class FileInfo(StrictModel):
    path: str | None = Field(default=None, max_length=1024)
    name: ShortStr | None = None
    sha256: Sha256Hex | None = None
    size: int | None = Field(default=None, ge=0)
    mtime: UtcDatetime | None = None


class NormalizedEvent(StrictModel):
    """One normalized telemetry record. `attributes` carries untrusted original fields."""

    schema_version: Literal[1] = 1
    event_id: UUID
    episode_id: UUID
    occurred_at: UtcDatetime
    ingested_at: UtcDatetime
    visible_at: UtcDatetime
    host_id: HostId
    source: EventSource
    category: EventCategory
    action: ShortStr
    process: ProcessInfo | None = None
    user: UserInfo | None = None
    network: NetworkInfo | None = None
    file: FileInfo | None = None
    raw_ref: str = Field(min_length=1, max_length=512)
    raw_sha256: Sha256Hex
    normalizer_version: str = Field(min_length=1, max_length=32)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ordering(self) -> NormalizedEvent:
        if self.visible_at < self.ingested_at:
            raise ValueError("visible_at must not precede ingested_at")
        return self


class EvidenceRef(StrictModel):
    """Verifiable pointer to an indexed event; unsupported refs fail evaluation."""

    event_id: UUID
    sha256: Sha256Hex
    source: EventSource
    visible_at: UtcDatetime
    raw_ref: str | None = Field(default=None, max_length=512)
