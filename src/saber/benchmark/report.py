"""Reproducible per-subtask reports (ReportV1 subset).

A report records the scorer version, catalog digest, code commit (if available), and per-episode
scores for the built-in oracle and reference solvers. It is explicitly labelled
DEV_SIMULATION_ONLY: these numbers describe the scorer on synthetic fixtures, not model quality
on a validated benchmark.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from saber.catalog.loader import default_catalog
from saber.domain.base import StrictModel
from saber.episodes import build_episode
from saber.episodes.runner import run_oracle, run_reference
from saber.grading import SCORER_VERSION
from saber.subtasks import load_subtask


class EpisodeScoreRow(StrictModel):
    episode_id: str
    seed: int
    variant: str
    solver: str
    score: float
    raw_score: float
    validity: str
    caps_applied: list[str] = Field(default_factory=list)


class ReportV1(StrictModel):
    schema_version: Literal[1] = 1
    subtask_id: str
    service: str
    environment: str
    scorer_version: str
    source_formula: str
    catalog_digest: str
    code_commit: str
    generated_at: datetime
    labels: list[str] = Field(default_factory=lambda: ["DEV_SIMULATION_ONLY"])
    oracle_full_credit: bool
    rows: list[EpisodeScoreRow] = Field(default_factory=list)
    notes: str = ""


def _code_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def subtask_report(subtask_id: str, seeds: list[int]) -> dict[str, Any]:
    st = load_subtask(subtask_id)
    cat = default_catalog()
    record = cat.subtask(subtask_id)
    rows: list[EpisodeScoreRow] = []
    oracle_full = True
    for variant in st.VARIANTS:
        for seed in seeds:
            ep = build_episode(subtask_id, seed, variant)
            orc = run_oracle(ep)
            if abs(orc.score.score - 1.0) > 1e-9 or orc.score.validity.value != "VALID":
                oracle_full = False
            rows.append(
                EpisodeScoreRow(
                    episode_id=ep.episode_id,
                    seed=seed,
                    variant=variant,
                    solver="oracle",
                    score=orc.score.score,
                    raw_score=orc.score.raw_score,
                    validity=orc.score.validity.value,
                    caps_applied=orc.score.caps_applied,
                )
            )
            ref = run_reference(ep)
            if ref is not None:
                rows.append(
                    EpisodeScoreRow(
                        episode_id=ep.episode_id,
                        seed=seed,
                        variant=variant,
                        solver="reference",
                        score=ref.score.score,
                        raw_score=ref.score.raw_score,
                        validity=ref.score.validity.value,
                        caps_applied=ref.score.caps_applied,
                    )
                )
    report = ReportV1(
        subtask_id=subtask_id,
        service=record.service,
        environment=record.environment,
        scorer_version=SCORER_VERSION,
        source_formula=record.score_aggregate_source,
        catalog_digest=cat.catalog_digest,
        code_commit=_code_commit(),
        generated_at=datetime.now(UTC),
        oracle_full_credit=oracle_full,
        rows=rows,
        notes="Synthetic DEV fixtures; oracle proves the scorer reaches full credit on the intended answer.",
    )
    return report.model_dump(mode="json")
