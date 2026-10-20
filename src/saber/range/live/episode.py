"""Model for one live lab episode: real telemetry, sealed control-plane truth, hashed evidence."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from saber.domain.base import StrictModel, UtcDatetime


class EvidenceFile(StrictModel):
    """One raw evidence artifact on disk, with integrity hash and byte size."""

    path: str
    kind: str  # "access_log" | "process_record" | "manifest"
    sha256: str
    size_bytes: int


class LiveEpisode(StrictModel):
    """A genuinely executed SOC episode: agent-visible telemetry + sealed, independently-derived truth."""

    schema_version: int = 1
    scenario: str
    seed: int
    backend: str  # "process-local" | "container"
    host_os: str
    started_at: UtcDatetime
    ended_at: UtcDatetime
    # Process telemetry for the service (genuine): pid, bound port, return code, timing.
    service: dict[str, Any] = Field(default_factory=dict)
    # Network telemetry (genuine, loopback): endpoint and request count.
    network: dict[str, Any] = Field(default_factory=dict)
    # Application telemetry: the service's real access log (agent-visible public evidence).
    access_log_lines: list[str] = Field(default_factory=list)
    access_log_sha256: str = ""
    evidence_ids: list[str] = Field(default_factory=list)  # "line-N" ids the agent may cite
    # Sealed, control-plane-derived ground truth + the generation intent it is cross-checked against.
    gold_truth: dict[str, Any] = Field(default_factory=dict)
    control_plane_intent: dict[str, Any] = Field(default_factory=dict)
    cross_check_ok: bool = False
    cross_check_detail: str = ""
    # Lab lifecycle + evidence integrity.
    lab_state: dict[str, Any] = Field(default_factory=dict)
    evidence_dir: str = ""
    evidence_files: list[EvidenceFile] = Field(default_factory=list)
    labels: list[str] = Field(
        default_factory=lambda: ["LIVE_LAB_EXECUTION", "AUTOMATED_LAB_GROUND_TRUTH"]
    )

    def public_inputs(self) -> dict[str, Any]:
        """Agent-visible evidence only (the real access log); never the sealed truth."""
        return {
            "corpus": {
                "lines": list(self.access_log_lines),
                "format": "JSON access-log records: {ts, client, method, target, status, ua}",
                "note": "genuine telemetry from a live local HTTP service (loopback)",
            },
            "objective": "Detect the malicious requests in this real access log.",
        }
