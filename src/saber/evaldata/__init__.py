"""Phase E1 — independent evaluation-data ingestion, provenance, and contamination control.

This package ingests GENUINE external security data (event logs, network captures, host
artifacts, detection-test corpora) into normalized records, each carrying a provenance record
(source, license, checksum, retrieval time) and a **label tier** that keeps four kinds of label
separate:

* ``SOURCE_PROVIDED`` — the dataset authors' own label/semantics,
* ``INDEPENDENTLY_VERIFIED`` — re-derived by a distinct route that agrees,
* ``SYNTHETIC`` — labels we constructed (e.g. the gold pilots),
* ``EXPERT_ADJUDICATION_REQUIRED`` — needs a human.

It also fingerprints scenario *lineage* (ATT&CK technique + IOC set + detection logic) so the same
attack cannot cross a train/dev/test split under different NICE/subtask IDs.

Nothing here promotes a subtask to READY_BENCHMARK: external data gives SOURCE_PROVIDED labels,
which are not independently validated gold for SABER's subtasks.
"""

from __future__ import annotations

from saber.evaldata.catalog import CANDIDATE_SOURCES, candidate_by_kind
from saber.evaldata.contamination import (
    LineageGuardError,
    assert_no_lineage_crosses_split,
    lineage_key,
)
from saber.evaldata.importers import ImportResult, import_dataset
from saber.evaldata.provenance import DataSource, LabelTier, ProvenanceRecord, sha256_file

__all__ = [
    "CANDIDATE_SOURCES",
    "DataSource",
    "ImportResult",
    "LabelTier",
    "LineageGuardError",
    "ProvenanceRecord",
    "assert_no_lineage_crosses_split",
    "candidate_by_kind",
    "import_dataset",
    "lineage_key",
    "sha256_file",
]
