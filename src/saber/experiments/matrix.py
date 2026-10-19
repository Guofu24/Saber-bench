"""Run offline baselines over implemented subtasks and aggregate with uncertainty.

Reports per-baseline, per-service and per-environment mean scores with bootstrap CIs over
subtasks, plus validity and coverage. LLM baselines are listed as BLOCKED_INTEGRATION rather than
run. Everything is labelled DEV_SIMULATION_ONLY: these are scorer/ baseline numbers on synthetic
fixtures, not evidence of model quality on a validated benchmark.
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from saber.agents.baselines import BASELINES, BaselineId, solve_episode
from saber.catalog.loader import default_catalog
from saber.domain.base import StrictModel
from saber.domain.errors import IntegrationBlocked
from saber.episodes import build_episode
from saber.experiments.stats import bootstrap_ci
from saber.grading import SCORER_VERSION
from saber.subtasks import implemented_ids, load_subtask


class CellResult(StrictModel):
    subtask_id: str
    service: str
    environment: str
    baseline: str
    mean_score: float
    validity_rate: float
    episodes: int
    abstained: bool = False


class GroupStat(StrictModel):
    group: str
    baseline: str
    mean: float
    ci_low: float
    ci_high: float
    n_subtasks: int
    # A bootstrap CI over fewer than 3 subtasks is not trustworthy; callers should not read it
    # as precision. The CI is still emitted for completeness but flagged.
    reliable_ci: bool = True


class ExperimentReport(StrictModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    scorer_version: str
    catalog_digest: str
    code_commit: str
    labels: list[str] = Field(default_factory=lambda: ["DEV_SIMULATION_ONLY"])
    baselines_run: list[str] = Field(default_factory=list)
    baselines_blocked: list[str] = Field(default_factory=list)
    subtasks: list[str] = Field(default_factory=list)
    cells: list[CellResult] = Field(default_factory=list)
    by_baseline: list[GroupStat] = Field(default_factory=list)
    by_service: list[GroupStat] = Field(default_factory=list)
    by_environment: list[GroupStat] = Field(default_factory=list)
    specialist_coverage: dict[str, int] = Field(default_factory=dict)
    # Subtasks a baseline abstained on (e.g. B0 has no rules oracle); excluded from its aggregate
    # so structural zeros do not masquerade as detection failures.
    abstentions: dict[str, list[str]] = Field(default_factory=dict)
    notes: str = ""


def _commit() -> str:
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


def run_matrix(
    subtask_ids: list[str] | None = None,
    baselines: list[BaselineId] | None = None,
    seeds: list[int] | None = None,
) -> dict[str, Any]:
    from saber.agents.router import SERVICE_TO_SPECIALIST

    ids = subtask_ids or implemented_ids()
    seed_list = seeds or [1, 42]
    # Default: the full protocol baseline set (B0-B4) plus the evaluator oracle. Offline-runnable
    # ones execute; LLM-backed B1-B4 are reported as BLOCKED_INTEGRATION rather than run.
    want = baselines or [
        BaselineId.B0_RULES,
        BaselineId.B1_SINGLE_AGENT,
        BaselineId.B2_SPECIALISTS,
        BaselineId.B3_SPECIALISTS_SHARED,
        BaselineId.B4_WITH_CONTENT,
        BaselineId.ORACLE,
    ]
    cat = default_catalog()

    run_ids: list[str] = []
    blocked: list[str] = []
    for b in want:
        if BASELINES[b].offline:
            run_ids.append(b.value)
        else:
            blocked.append(b.value)

    cells: list[CellResult] = []
    coverage: dict[str, int] = defaultdict(int)
    # scores[baseline][subtask] = mean score; abstained subtasks are excluded from this aggregate.
    scores: dict[str, dict[str, list[float]]] = {bid: defaultdict(list) for bid in run_ids}
    abstentions: dict[str, list[str]] = defaultdict(list)

    for sid in ids:
        st = load_subtask(sid)
        rec = cat.subtask(sid)
        coverage[SERVICE_TO_SPECIALIST.get(rec.service, "monitor")] += 1
        # A baseline "abstains" on a subtask it has no solver for (B0 with no reference_solve);
        # that is structurally different from attempting and failing.
        first_episode = build_episode(sid, seed_list[0], st.VARIANTS[0])
        b0_abstains = st.reference_solve(first_episode.bundle.public_inputs) is None
        for bid in run_ids:
            abstained = bid == BaselineId.B0_RULES.value and b0_abstains
            per_episode: list[float] = []
            per_valid: list[float] = []
            for variant in st.VARIANTS:
                for seed in seed_list:
                    episode = build_episode(sid, seed, variant)
                    try:
                        result = solve_episode(BaselineId(bid), episode)
                    except IntegrationBlocked:
                        continue
                    per_episode.append(result.score.score)
                    per_valid.append(1.0 if result.score.validity.value == "VALID" else 0.0)
            if per_episode:
                mean_score = sum(per_episode) / len(per_episode)
                if abstained:
                    abstentions[bid].append(sid)
                else:
                    scores[bid][sid].append(mean_score)
                cells.append(
                    CellResult(
                        subtask_id=sid,
                        service=rec.service,
                        environment=rec.environment,
                        baseline=bid,
                        mean_score=mean_score,
                        validity_rate=sum(per_valid) / len(per_valid),
                        episodes=len(per_episode),
                        abstained=abstained,
                    )
                )

    scored_cells = [c for c in cells if not c.abstained]
    report = ExperimentReport(
        generated_at=datetime.now(UTC),
        scorer_version=SCORER_VERSION,
        catalog_digest=cat.catalog_digest,
        code_commit=_commit(),
        baselines_run=run_ids,
        baselines_blocked=blocked,
        subtasks=list(ids),
        cells=cells,
        by_baseline=[_group("all", bid, [v[0] for v in scores[bid].values()]) for bid in run_ids],
        by_service=_grouped(scored_cells, run_ids, key="service"),
        by_environment=_grouped(scored_cells, run_ids, key="environment"),
        specialist_coverage=dict(coverage),
        abstentions=dict(abstentions),
        notes="B0 is the rules-only reference (abstains where no rules oracle exists; those are "
        "excluded from its aggregate, not scored 0). ORACLE is the evaluator upper bound, not a "
        "competitor. LLM baselines are BLOCKED_INTEGRATION (subscription-only, no API budget).",
    )
    return report.model_dump(mode="json")


def _group(group: str, baseline: str, values: list[float]) -> GroupStat:
    ci = bootstrap_ci(values)
    return GroupStat(
        group=group,
        baseline=baseline,
        mean=ci.mean,
        ci_low=ci.low,
        ci_high=ci.high,
        n_subtasks=ci.n,
        reliable_ci=ci.n >= 3,
    )


def _grouped(cells: list[CellResult], baselines: list[str], *, key: str) -> list[GroupStat]:
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for c in cells:
        buckets[(getattr(c, key), c.baseline)].append(c.mean_score)
    out: list[GroupStat] = []
    for (group, baseline), values in sorted(buckets.items()):
        if baseline in baselines:
            out.append(_group(group, baseline, values))
    return out
