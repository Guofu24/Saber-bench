"""Load and verify the frozen catalog. Standard library + Pydantic only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from saber.catalog.models import CatalogArtifact, CatalogMetadata, CatalogSubtask, CatalogTask
from saber.catalog.parsing import parse_aggregate, parse_score_item
from saber.domain.errors import ValidationError

EXPECTED_SOURCE_SHA256 = "92b53fad8d20909381875c70c8b0d9d198273256d0d2ff86b617c74c68080d6b"


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "catalog" / "subtasks.json").is_file():
            return parent
    raise ValidationError("catalog directory not found relative to package")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Catalog:
    metadata: CatalogMetadata
    tasks: tuple[CatalogTask, ...]
    subtasks: tuple[CatalogSubtask, ...]
    artifacts: tuple[CatalogArtifact, ...]
    catalog_digest: str
    source_verified: bool

    def subtask(self, subtask_id: str) -> CatalogSubtask:
        for row in self.subtasks:
            if row.id == subtask_id:
                return row
        raise ValidationError(f"unknown benchmark subtask {subtask_id!r}")

    def task(self, nice_id: str) -> CatalogTask:
        for row in self.tasks:
            if row.nice_id == nice_id:
                return row
        raise ValidationError(f"unknown NICE task {nice_id!r}")

    def artifact(self, hv_id: str) -> CatalogArtifact:
        for row in self.artifacts:
            if row.id == hv_id:
                return row
        raise ValidationError(f"unknown artifact type {hv_id!r}")

    def by_environment(self, environment: str) -> list[CatalogSubtask]:
        return [s for s in self.subtasks if s.environment == environment]

    def by_service(self, service: str) -> list[CatalogSubtask]:
        return [s for s in self.subtasks if s.service == service]


def load_catalog(root: Path | None = None, *, require_source: bool = False) -> Catalog:
    base = (root or repo_root()) / "catalog"
    meta = CatalogMetadata.model_validate(_read_json(base / "metadata.json"))
    if meta.source_sha256 != EXPECTED_SOURCE_SHA256:
        raise ValidationError("catalog metadata source hash differs from the frozen constant")
    source_path = (root or repo_root()) / meta.source_file
    source_verified = False
    if source_path.is_file():
        if _sha256_file(source_path) != meta.source_sha256:
            raise ValidationError("frozen source HTML checksum mismatch; refuse to load")
        source_verified = True
    elif require_source:
        raise ValidationError("frozen source HTML missing and require_source=True")

    raw_subtasks = _read_json(base / "subtasks.json")
    subtasks: list[CatalogSubtask] = []
    for row in raw_subtasks:
        model = CatalogSubtask.model_validate(row)
        model.score_items = [parse_score_item(item) for item in model.score_items_source]
        model.aggregate = parse_aggregate(model.score_aggregate_source)
        subtasks.append(model)
    tasks = [CatalogTask.model_validate(r) for r in _read_json(base / "tasks.json")]
    artifacts = [CatalogArtifact.model_validate(r) for r in _read_json(base / "artifacts.json")]

    ids = {s.id for s in subtasks}
    if len(subtasks) != 175 or len(ids) != 175:
        raise ValidationError("catalog must contain exactly 175 unique subtasks")
    if len(tasks) != 55 or len(artifacts) != 40:
        raise ValidationError("catalog must contain 55 NICE tasks and 40 artifact types")
    hv_ids = {a.id for a in artifacts}
    for s in subtasks:
        if not set(s.input_hv_ids) <= hv_ids or not set(s.output_hv_ids) <= hv_ids:
            raise ValidationError(f"{s.id} references unknown HV artifact")
        if s.id.split(".")[0] != s.nice_id:
            raise ValidationError(f"{s.id} nice_id prefix mismatch")
    digest = hashlib.sha256()
    for name in ("metadata.json", "tasks.json", "subtasks.json", "artifacts.json"):
        digest.update(name.encode())
        digest.update((base / name).read_bytes())
    return Catalog(
        metadata=meta, tasks=tuple(tasks), subtasks=tuple(subtasks), artifacts=tuple(artifacts),
        catalog_digest=digest.hexdigest(), source_verified=source_verified,
    )  # fmt: skip


@lru_cache(maxsize=1)
def default_catalog() -> Catalog:
    return load_catalog()
