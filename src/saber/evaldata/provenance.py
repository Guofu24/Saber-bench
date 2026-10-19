"""Provenance and label-tier model for ingested evaluation data."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from saber.domain.base import StrictModel, UtcDatetime

DatasetKind = str  # "event_log" | "network_capture" | "host_artifact" | "detection_test"


class LabelTier(StrEnum):
    """How much a label can be trusted. Only SYNTHETIC/SOURCE_PROVIDED exist until a human signs off.

    A subtask may NOT be called READY_BENCHMARK on SOURCE_PROVIDED or SYNTHETIC labels alone.
    """

    SOURCE_PROVIDED = "source_provided"
    INDEPENDENTLY_VERIFIED = "independently_verified"
    SYNTHETIC = "synthetic"
    EXPERT_ADJUDICATION_REQUIRED = "expert_adjudication_required"


class DataSource(StrictModel):
    """A citable external data source with license + usage terms."""

    name: str
    kind: DatasetKind
    url: str
    license: str
    usage_permitted: bool  # research/eval usage permitted by the license, as reviewed
    commit: str | None = None  # pinned git commit / release for reproducibility
    homepage: str | None = None
    notes: str = ""


class ProvenanceRecord(StrictModel):
    """Evidence that a specific local artifact came from a specific source and validated."""

    source: DataSource
    local_path: str
    sha256: str
    size_bytes: int
    retrieved_at: UtcDatetime | None = None
    label_tier: LabelTier
    record_count: int | None = None
    validated: bool = False
    validation_detail: str = ""
    lineage_keys: list[str] = Field(default_factory=list)


def sha256_file(path: str | Path) -> tuple[str, int]:
    """Return (sha256 hex, size in bytes) for a file, read in chunks (handles large artifacts)."""
    h = hashlib.sha256()
    size = 0
    p = Path(path)
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size
