"""`saber` CLI (B005): task list/show, build, run, grade, report, smoke.

Offline-first. No command contacts a network service or a provider unless an adapter is
explicitly configured and approved; the default solvers are the evaluator oracle and the
rules-only reference baseline.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from typing import Any

import click

from saber import __version__
from saber.catalog import load_catalog
from saber.episodes import build_episode, write_episode
from saber.episodes.runner import run_oracle, run_reference, run_stub
from saber.subtasks import implemented_ids, load_subtask


def _echo_json(obj: Any) -> None:
    click.echo(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _force_utf8_stdio() -> None:
    # Source scorer formulas contain Unicode (prime, sigma, multiplication); force UTF-8 so a
    # legacy Windows console codepage does not raise UnicodeEncodeError when printing them.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8")


@click.group(help="SABER SOC benchmark CLI (offline-first, no live infrastructure by default).")
@click.version_option(__version__, prog_name="saber")
def cli() -> None:
    """Root command group."""
    _force_utf8_stdio()


@cli.group(help="Inspect and run benchmark subtasks.")
def task() -> None:
    """Subtask commands."""


@task.command("list", help="List catalog subtasks; --implemented for those with a module.")
@click.option("--service", type=click.Choice(["MON", "CNT", "HUNT", "IR"]), default=None)
@click.option("--environment", type=click.Choice(["file", "soc", "vm"]), default=None)
@click.option(
    "--implemented", is_flag=True, help="Only subtasks that have an implementation module."
)
def task_list(service: str | None, environment: str | None, implemented: bool) -> None:
    cat = load_catalog()
    impl = set(implemented_ids())
    rows = []
    for s in cat.subtasks:
        if service and s.service != service:
            continue
        if environment and s.environment != environment:
            continue
        if implemented and s.id not in impl:
            continue
        rows.append(
            {
                "id": s.id,
                "service": s.service,
                "env": s.environment,
                "implemented": s.id in impl,
                "aggregate": s.score_aggregate_source,
            }
        )
    impl_count = sum(1 for r in rows if r["implemented"])
    for r in rows:
        mark = "*" if r["implemented"] else " "
        click.echo(f"{mark} {r['id']:11s} {r['service']:4s} {r['env']:4s}  {r['aggregate']}")
    click.echo(f"\n{len(rows)} subtasks ({impl_count} implemented).")


@task.command("show", help="Show the frozen source record and parsed scorer for one subtask.")
@click.argument("subtask_id")
def task_show(subtask_id: str) -> None:
    cat = load_catalog()
    s = cat.subtask(subtask_id)
    out = {
        "id": s.id,
        "nice_id": s.nice_id,
        "service": s.service,
        "environment": s.environment,
        "scenario_source": s.scenario_source,
        "inputs": s.input_hv_ids,
        "outputs": s.output_hv_ids,
        "score_items_source": s.score_items_source,
        "score_aggregate_source": s.score_aggregate_source,
        "parsed_aggregate": s.aggregate.model_dump() if s.aggregate else None,
        "implemented": s.id in set(implemented_ids()),
    }
    _echo_json(out)


@task.command(
    "build", help="Build one DEV episode (public manifest + sealed truth) to a directory."
)
@click.argument("subtask_id")
@click.option("--seed", type=int, default=42)
@click.option("--variant", default="default")
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def task_build(subtask_id: str, seed: int, variant: str, out_dir: Path | None) -> None:
    ep = build_episode(subtask_id, seed, variant)
    if out_dir is None:
        out_dir = Path("runs") / subtask_id / f"{variant}-{seed}"
    paths = write_episode(ep, out_dir)
    _echo_json(
        {
            "episode_id": ep.episode_id,
            "subtask_id": subtask_id,
            "variant": variant,
            "seed": seed,
            "truth_sha256": ep.truth_sha256,
            "files": {k: str(v) for k, v in paths.items()},
        }
    )


@task.command("run", help="Run a built-in solver (oracle|reference) and grade it.")
@click.argument("subtask_id")
@click.option("--seed", type=int, default=42)
@click.option("--variant", default="default")
@click.option("--solver", type=click.Choice(["oracle", "reference"]), default="reference")
def task_run(subtask_id: str, seed: int, variant: str, solver: str) -> None:
    ep = build_episode(subtask_id, seed, variant)
    result = run_oracle(ep) if solver == "oracle" else run_reference(ep)
    if result is None:
        raise click.ClickException(f"{subtask_id} has no reference solver; try --solver oracle")
    _echo_json(_score_summary(result.score))


@task.command("grade", help="Grade a submission JSON file against a built episode's sealed truth.")
@click.argument("subtask_id")
@click.argument("submission_json", type=click.Path(exists=True, path_type=Path))
@click.option("--seed", type=int, default=42)
@click.option("--variant", default="default")
def task_grade(subtask_id: str, submission_json: Path, seed: int, variant: str) -> None:
    ep = build_episode(subtask_id, seed, variant)
    payload = json.loads(submission_json.read_text(encoding="utf-8"))
    answer = payload.get("answer", payload)
    refs = payload.get("evidence_refs", [])
    result = run_stub(ep, answer, refs)
    _echo_json(_score_summary(result.score))


@task.command("report", help="Build+grade oracle and reference across seeds; emit a JSON report.")
@click.argument("subtask_id")
@click.option("--seeds", default="1,42", help="Comma-separated seeds.")
def task_report(subtask_id: str, seeds: str) -> None:
    from saber.benchmark.report import subtask_report

    seed_list = [int(x) for x in seeds.split(",") if x.strip()]
    _echo_json(subtask_report(subtask_id, seed_list))


@cli.command(
    "experiment", help="Run offline baselines (B0, ORACLE) over implemented subtasks and aggregate."
)
@click.option("--seeds", default="1,42", help="Comma-separated seeds.")
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the report JSON here.",
)
def experiment(seeds: str, out_path: Path | None) -> None:
    from saber.experiments import run_matrix

    seed_list = [int(x) for x in seeds.split(",") if x.strip()]
    report = run_matrix(seeds=seed_list)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        click.echo(f"wrote {out_path}")
    for row in report["by_baseline"]:
        click.echo(
            f"  {row['baseline']:7s} mean={row['mean']:.3f} CI[{row['ci_low']:.3f},{row['ci_high']:.3f}] n={row['n_subtasks']}"
        )
    click.echo(
        f"blocked (no provider budget): {report['baselines_blocked']}  labels={report['labels']}"
    )


@cli.command(
    "smoke", help="End-to-end DEV smoke: build -> oracle -> reference -> grade for one subtask."
)
@click.option("--subtask", "subtask_id", default="T1112.001")
@click.option("--seed", type=int, default=42)
def smoke(subtask_id: str, seed: int) -> None:
    st = load_subtask(subtask_id)
    failures: list[str] = []
    for variant in st.VARIANTS:
        ep = build_episode(subtask_id, seed, variant)
        oracle = run_oracle(ep)
        if abs(oracle.score.score - 1.0) > 1e-9 or oracle.score.validity.value != "VALID":
            failures.append(
                f"{variant}: oracle score {oracle.score.score} validity {oracle.score.validity.value}"
            )
        ref = run_reference(ep)
        ref_score = None if ref is None else round(ref.score.score, 4)
        click.echo(
            f"  {subtask_id}/{variant}/{seed}: oracle={oracle.score.score:.3f} reference={ref_score}"
        )
    if failures:
        raise click.ClickException("smoke failed: " + "; ".join(failures))
    click.echo(
        f"SMOKE OK ({subtask_id}, DEV_SIMULATION_ONLY): oracle reaches full credit on all variants."
    )


@cli.command(
    "serve", help="Run the read-mostly API (offline). Only event path is the bounded gateway."
)
@click.option("--host", default="127.0.0.1")
@click.option("--port", type=int, default=8000)
def serve(host: str, port: int) -> None:  # pragma: no cover - thin uvicorn wrapper
    import uvicorn

    from saber.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


@cli.group(
    help="Gold Evaluation Pilot v1: domain-faithful artifacts with independently-derived truth."
)
def gold() -> None:
    """Gold pilot commands."""


@gold.command("list", help="List the gold pilot subtasks and their status.")
def gold_list() -> None:
    from saber.gold import load_pilot, pilot_ids

    for sid in pilot_ids():
        p = load_pilot(sid)
        ep = p.build("dev", 1)
        v = p.independent_verify(ep)
        oracle = p.grade(ep, p.answer_from_gold(ep), agent_id="gold_oracle")
        click.echo(
            f"  {sid:11s} verify={'OK' if v.ok else 'FAIL'} oracle={oracle.score:.2f}  {p.instructions()[:66]}"
        )
    click.echo(f"\n{len(pilot_ids())} gold pilots (GOLD_PILOT_V1; not READY_BENCHMARK).")


@gold.command(
    "verify", help="Run independent verification + gold oracle for every pilot and split."
)
def gold_verify() -> None:
    from saber.gold import load_pilot, pilot_ids

    failures = 0
    for sid in pilot_ids():
        p = load_pilot(sid)
        for split_name in ("dev", "hidden"):
            ep = p.build(split_name, 1)
            v = p.independent_verify(ep)
            oracle = p.grade(ep, p.answer_from_gold(ep), agent_id="gold_oracle")
            if not (v.ok and abs(oracle.score - 1.0) < 1e-9):
                failures += 1
                click.echo(
                    f"  FAIL {sid}/{split_name}: verify={v.ok} oracle={oracle.score:.3f} {v.detail}"
                )
    if failures:
        raise click.ClickException(f"{failures} gold verification failures")
    click.echo(
        "GOLD VERIFY OK: all pilots independently verified and oracle reaches full credit (dev+hidden)."
    )


@gold.command(
    "emit", help="Write gold/MANIFEST.json (provenance + checksums) and the adjudication queue."
)
def gold_emit() -> None:
    from saber.gold.emit import write_manifest

    mpath, qpath = write_manifest()
    click.echo(f"wrote {mpath}")
    click.echo(f"wrote {qpath}")


@cli.command(
    "split", help="Show the frozen family-based train/dev/test split and run leakage checks."
)
def split() -> None:
    from saber.benchmark.splits import (
        assert_all_services_represented,
        assert_no_family_crosses_split,
        assert_partition_complete,
        build_split,
    )

    assignment = build_split()
    assert_partition_complete(assignment)
    assert_no_family_crosses_split(assignment)
    assert_all_services_represented(assignment)
    click.echo(f"seed={assignment.seed}  counts={assignment.counts()}")
    click.echo(
        "leakage checks OK: partition complete, no family crosses a split, services represented"
    )


def _score_summary(score: Any) -> dict[str, Any]:
    return {
        "subtask_id": score.subtask_id,
        "episode_id": str(score.episode_id),
        "score": score.score,
        "raw_score": score.raw_score,
        "validity": score.validity.value,
        "invalid_reason": score.invalid_reason,
        "components": [c.model_dump() for c in score.components],
        "gates": [g.model_dump() for g in score.gates],
        "caps_applied": score.caps_applied,
        "scorer_version": score.scorer_version,
        "labels": score.labels,
        "trace": score.trace,
    }


def main() -> None:
    cli(prog_name="saber")


if __name__ == "__main__":
    main()
