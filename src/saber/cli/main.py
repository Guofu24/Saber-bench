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
from saber.environments.cli import env
from saber.episodes import build_episode, write_episode
from saber.episodes.runner import run_oracle, run_reference, run_stub
from saber.lab.cli import lab
from saber.subtasks import implemented_ids, load_subtask
from saber.training.cli import training
from saber.world.cli import world


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
        "GOLD VERIFY OK: every pilot's truth re-derived by a second (independent) route and oracle "
        "reaches full credit (dev+hidden). Note: splits share templates (not a blind holdout)."
    )


@gold.command(
    "emit", help="Write gold/MANIFEST.json (provenance + checksums) and the adjudication queue."
)
def gold_emit() -> None:
    from saber.gold.emit import write_manifest

    mpath, qpath = write_manifest()
    click.echo(f"wrote {mpath}")
    click.echo(f"wrote {qpath}")


@gold.command(
    "baseline",
    help="Run the rules baseline (and optional subscription LLM baseline) over gold episodes.",
)
@click.option("--model", default="haiku", help="Fixed Claude model alias/id for the LLM baseline.")
@click.option("--llm/--no-llm", "use_llm", default=False, help="Invoke the subscription CLI LLM.")
@click.option("--split", "split_name", type=click.Choice(["dev", "hidden"]), default="dev")
@click.option("--seeds", default="1", help="Comma-separated seeds (e.g. 1,2,3).")
@click.option("--subtasks", default=None, help="Comma-separated subtask IDs (default: all 12).")
@click.option("--timeout", "timeout_s", type=float, default=120.0, help="Per-call timeout (s).")
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def gold_baseline(
    model: str,
    use_llm: bool,
    split_name: str,
    seeds: str,
    subtasks: str | None,
    timeout_s: float,
    out_dir: Path | None,
) -> None:
    from typing import cast

    from saber.baselines.pilot_runner import run_baselines, write_report
    from saber.gold.base import Split

    ids = [s.strip() for s in subtasks.split(",") if s.strip()] if subtasks else None
    seed_list = [int(x) for x in seeds.split(",") if x.strip()]
    report = run_baselines(
        ids,
        split=cast(Split, split_name),
        seeds=seed_list,
        model=model,
        use_llm=use_llm,
        timeout_s=timeout_s,
    )
    s = report["summary"]
    click.echo(f"oracle={s['oracle']['mean']} rules={s['rules']['mean']} (n={s['n_episodes']})")
    if use_llm:
        click.echo(
            f"llm({report.get('model_used_observed')} via {report.get('providers_observed')}) "
            f"completion={s.get('llm_completion_rate')} "
            f"score_completed={s.get('llm_score_completed', {}).get('mean')} "
            f"latency={s.get('llm_mean_latency_ms')}ms tool_failures={s.get('llm_total_tool_failures')}"
        )
    if split_name == "hidden":
        click.echo("hidden split: report NOT written to disk (sealed split); summary above only.")
        return
    jpath, mpath = write_report(report, out_dir)
    click.echo(f"wrote {jpath}")
    click.echo(f"wrote {mpath}")


@gold.command(
    "compare",
    help="Four-way baseline comparison (oracle/naive/strong + LLM single/specialist/multi-agent).",
)
@click.option("--model", default="haiku", help="Fixed Claude model alias/id for the LLM modes.")
@click.option(
    "--llm/--no-llm", "use_llm", default=False, help="Include the subscription LLM modes."
)
@click.option("--split", "split_name", type=click.Choice(["dev", "hidden"]), default="dev")
@click.option("--seeds", default="1", help="Comma-separated seeds.")
@click.option("--subtasks", default=None, help="Comma-separated subtask IDs (default: all 12).")
@click.option("--modes", default="single,specialist,multi_agent", help="LLM modes to run.")
@click.option("--timeout", "timeout_s", type=float, default=150.0, help="Per-call timeout (s).")
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def gold_compare(
    model: str,
    use_llm: bool,
    split_name: str,
    seeds: str,
    subtasks: str | None,
    modes: str,
    timeout_s: float,
    out_dir: Path | None,
) -> None:
    from typing import cast

    from saber.baselines.compare import run_comparison, write_comparison
    from saber.gold.base import Split

    ids = [s.strip() for s in subtasks.split(",") if s.strip()] if subtasks else None
    mode_tuple = tuple(m.strip() for m in modes.split(",") if m.strip())
    report = run_comparison(
        ids,
        split=cast(Split, split_name),
        seeds=[int(x) for x in seeds.split(",") if x.strip()],
        model=model,
        llm_modes=mode_tuple,
        use_llm=use_llm,
        timeout_s=timeout_s,
    )
    for b in report["baselines"]:
        a = report["summary"][b]
        click.echo(f"  {b:12s} score={a['score']['mean']} fp={a['fp_total']} fn={a['fn_total']}")
    if split_name == "hidden":
        click.echo("hidden split: report NOT written to disk (sealed split).")
        return
    jpath, mpath = write_comparison(report, out_dir)
    click.echo(f"wrote {jpath}")
    click.echo(f"wrote {mpath}")


@cli.group("range", help="Operational live lab (Phase F): run genuine local SOC episodes.")
def range_() -> None:
    """Live lab commands."""


@range_.command("scenarios", help="List the live lab scenarios.")
def range_scenarios() -> None:
    from saber.range.live import scenario_ids

    for sid in scenario_ids():
        click.echo(sid)


@range_.command("run", help="Execute one genuine live episode (real loopback service + traffic).")
@click.option("--scenario", "scenario", default="web_sqli_probe")
@click.option("--seed", type=int, default=1)
@click.option(
    "--noise-clients",
    type=int,
    default=0,
    help="Overlay benign background traffic from N client identities (0 = none).",
)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def range_run(scenario: str, seed: int, noise_clients: int, out_dir: Path | None) -> None:
    import json as _json

    from saber.range.live import run_episode

    workdir = out_dir or (Path("runs") / "live")
    ep = run_episode(scenario, seed, workdir=workdir, noise_clients=noise_clients)
    # Write only the TRUTH-FREE public receipt into the evidence dir (safe to upload/publish); the
    # sealed control-plane truth (which lines are malicious) is never persisted here.
    ep_path = Path(ep.evidence_dir) / "episode_public.json"
    ep_path.write_text(_json.dumps(ep.public_receipt(), indent=2) + "\n", encoding="utf-8")
    click.echo(
        f"scenario={ep.scenario} seed={ep.seed} host={ep.host_os}\n"
        f"requests_sent={ep.network['requests_sent']} log_lines={len(ep.access_log_lines)} "
        f"malicious={ep.gold_truth['m']}\n"
        f"cross_check_ok={ep.cross_check_ok} reset_ok={ep.lab_state['reset_ok']} "
        f"client_noise={ep.network.get('client_noise_requests', 0)} "
        f"access_log_sha256={ep.access_log_sha256[:16]}\n"
        f"wrote {ep_path}"
    )


@range_.command("noise", help="Preview the benign client-population noise plan (no service run).")
@click.option("--scenario", "scenario", default="web_sqli_probe")
@click.option("--seed", type=int, default=1)
@click.option("--clients", type=int, default=3)
def range_noise(scenario: str, seed: int, clients: int) -> None:
    from saber.range.live import client_noise
    from saber.subtasks._hv.common import Rng

    plan = client_noise(Rng("live-noise", scenario, str(seed)), clients=clients)
    click.echo(f"scenario={scenario} seed={seed} clients={clients} benign_requests={len(plan)}")
    for req in plan[:12]:
        click.echo(f"  {req['intent']:7s} {req['target']}")
    if len(plan) > 12:
        click.echo(f"  ... (+{len(plan) - 12} more)")


@range_.command(
    "bench", help="Exercise the T0020 contract on live episodes; compare single vs multi-agent."
)
@click.option("--model", default="haiku")
@click.option("--llm/--no-llm", "use_llm", default=False)
@click.option("--seeds", default="1")
@click.option("--modes", default="naive,strong,single,multi_agent")
@click.option("--timeout", "timeout_s", type=float, default=150.0)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def range_bench(
    model: str, use_llm: bool, seeds: str, modes: str, timeout_s: float, out_dir: Path | None
) -> None:
    from saber.range.live import run_live_benchmark, write_live_benchmark

    report = run_live_benchmark(
        seeds=[int(x) for x in seeds.split(",") if x.strip()],
        model=model,
        modes=tuple(m.strip() for m in modes.split(",") if m.strip()),
        use_llm=use_llm,
        timeout_s=timeout_s,
    )
    for mode, a in report["summary"].items():
        click.echo(
            f"  {mode:12s} score={a['score_mean']} completed={a['score_completed_mean']} "
            f"fp={a['fp_total']} fn={a['fn_total']} calls={a['n_calls_total']} "
            f"evidence_valid={a['evidence_valid_all']}"
        )
    path = write_live_benchmark(report, out_dir)
    click.echo(f"wrote {path}")


@cli.group("soc", help="Four-service SOC case workflow over live lab evidence (Phase G).")
def soc() -> None:
    """SOC workflow commands."""


@soc.command("run", help="Run the four-service workflow across scenario families; emit coverage.")
@click.option("--scenarios", default="web_sqli_probe,auth_bruteforce,fs_change,persistence")
@click.option("--seeds", default="1,2")
@click.option("--detector", default="conventional", type=click.Choice(["conventional", "naive"]))
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def soc_run(scenarios: str, seeds: str, detector: str, out_dir: Path | None) -> None:
    from saber.soc import run_soc_suite, write_soc_suite

    report = run_soc_suite(
        [s.strip() for s in scenarios.split(",") if s.strip()],
        [int(x) for x in seeds.split(",") if x.strip()],
        detector=detector,
    )
    for row in report["coverage_matrix"]:
        click.echo(
            f"  {row['scenario']:16s} seed={row['seed']} ok={row['episode_success']} "
            f"mon={row['monitoring_score']}(fp{row['monitoring_fp']}/fn{row['monitoring_fn']}) "
            f"hunt_f1={row['hunting_entity_f1']} ir_exec={row['ir_executed']} ir_verified={row['ir_verified']}"
        )
    path = write_soc_suite(report, out_dir)
    click.echo(f"wrote {path}")


@soc.command(
    "detect-bench",
    help="Track A detection benchmark: detectors over families x seeds x benign client noise.",
)
@click.option("--seeds", default="1,2,3")
@click.option("--noise-clients", type=int, default=3)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def soc_detect_bench(seeds: str, noise_clients: int, out_dir: Path | None) -> None:
    from saber.soc import run_detection_bench, write_detection_bench

    report = run_detection_bench(
        seeds=[int(x) for x in seeds.split(",") if x.strip()],
        noise_clients=noise_clients,
    )
    click.echo(
        f"families={len(report['families'])} seeds={report['seeds']} noise={report['noise_clients']} "
        f"allowlist_ok={report['allowlist_covers_scenarios']} cross_checks_ok={report['all_cross_checks_ok']}"
    )
    for d, a in report["summary"].items():
        rec, prec = a["recall"], a["precision"]
        click.echo(
            f"  {d:12s} recall={rec['mean']} CI{rec['ci95_cluster']} "
            f"precision={prec['mean']} CI{prec['ci95_cluster']} "
            f"fp_total={a['fp_total']} fn_total={a['fn_total']} eps_with_fp={a['episodes_with_fp']}"
        )
    path = write_detection_bench(report, out_dir)
    click.echo(f"wrote {path}")


@soc.command(
    "response-bench",
    help="Track B response benchmark: detection quality -> verified containment vs benign impact.",
)
@click.option("--seeds", default="1,2,3")
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def soc_response_bench(seeds: str, out_dir: Path | None) -> None:
    from saber.soc import run_response_bench, write_response_bench

    report = run_response_bench(seeds=[int(x) for x in seeds.split(",") if x.strip()])
    click.echo(f"family={report['family']} seeds={report['seeds']}")
    for d, a in report["summary"].items():
        click.echo(
            f"  {d:12s} containment_recall={a['containment_recall_mean']} "
            f"false_containment={a['false_containment_total']} "
            f"eps_with_false_containment={a['episodes_with_false_containment']} "
            f"verified_rate={a['all_verified_rate']}"
        )
    path = write_response_bench(report, out_dir)
    click.echo(f"wrote {path}")


@soc.command("eval", help="G3 six-config multi-agent evaluation + budget-matched ablation.")
@click.option("--model", default="haiku")
@click.option("--llm/--no-llm", "use_llm", default=False)
@click.option("--seeds", default="1,2,3")
@click.option("--timeout", "timeout_s", type=float, default=180.0)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def soc_eval(model: str, use_llm: bool, seeds: str, timeout_s: float, out_dir: Path | None) -> None:
    from saber.soc import run_g3_evaluation, write_g3_evaluation

    report = run_g3_evaluation(
        seeds=[int(x) for x in seeds.split(",") if x.strip()],
        model=model,
        use_llm=use_llm,
        timeout_s=timeout_s,
    )
    for scenario, fam in report["families"].items():
        click.echo(f"[{scenario}]")
        for c in report["configs"]:
            a = fam["summary"][c]
            click.echo(
                f"  {c:18s} score={a['score_mean']} fp={a['fp_total']} fn={a['fn_total']} "
                f"calls={a['n_calls_total']} cost=${a['cost_listprice']}"
            )
        ab = fam.get("ablation")
        if ab:
            click.echo(
                f"  ABLATION ma-budget_single={ab['multi_agent_vs_budget_single']['mean_delta']} "
                f"ma-multi_no_reviewer={ab['multi_agent_vs_multi_no_reviewer']['mean_delta']}"
            )
    path = write_g3_evaluation(report, out_dir)
    click.echo(f"models_observed={report['models_observed']}")
    click.echo(f"wrote {path}")


@soc.command("adjudicate", help="Build the gold-label adjudication package (NOT auto-approved).")
@click.option("--scenarios", default="web_sqli_probe,auth_bruteforce,fs_change,persistence")
@click.option("--seed", type=int, default=9001)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
def soc_adjudicate(scenarios: str, seed: int, out_dir: Path | None) -> None:
    from saber.soc import build_adjudication_package, write_adjudication_package

    pkg = build_adjudication_package(
        [s.strip() for s in scenarios.split(",") if s.strip()], seed=seed
    )
    jpath, mpath = write_adjudication_package(pkg, out_dir)
    click.echo(
        f"status={pkg['status']} gold_labels={pkg['independently_validated_gold_labels']} "
        f"ready_benchmark={pkg['ready_benchmark_subtasks']} bundles={len(pkg['bundles'])}"
    )
    click.echo(f"wrote {jpath}")
    click.echo(f"wrote {mpath}")


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


# A small, gradeable smoke set: one subtask per service with a variant that materialises a case.
_SMOKE_SET: tuple[tuple[str, str], ...] = (
    ("T1112.001", "tp"),  # MON  — alert TP/FP verdict
    ("T0020.001", "default"),  # CNT  — write a regex rule
    ("T0167.001", "default"),  # HUNT — match files against IOCs
    ("T0173.001", "default"),  # IR   — reorder events across timezones
)


@cli.group("agent", help="Run LLM-backed specialist agents (B1/B2) over episodes.")
def agent() -> None:
    """Agent commands. Paid backends are OFF unless explicitly enabled on the command."""


@agent.command("run", help="Solve episodes with an LLM specialist and grade honestly (DEV).")
@click.option("--provider", type=click.Choice(["gemini"]), default="gemini", show_default=True)
@click.option(
    "--baseline",
    type=click.Choice(["b1", "b2"]),
    default="b2",
    show_default=True,
    help="b1 = generic single agent; b2 = service specialist (loads .claude/skills).",
)
@click.option(
    "--subtask",
    "subtasks",
    multiple=True,
    help="SUBTASK_ID or SUBTASK_ID:variant. Repeatable. Default: the 4-service smoke set.",
)
@click.option("--seed", type=int, default=1, show_default=True)
@click.option("--model", default="gemini-2.5-flash", show_default=True)
@click.option("--key-pool", default="keys_pool.txt", show_default=True, help="Gitignored key file.")
@click.option(
    "--enable-paid",
    is_flag=True,
    help="Operator opt-in to the paid/free-tier API backend. Required to make any call.",
)
@click.option("--budget", type=int, default=8, show_default=True, help="Max billable calls (cap).")
def agent_run(
    provider: str,
    baseline: str,
    subtasks: tuple[str, ...],
    seed: int,
    model: str,
    key_pool: str,
    enable_paid: bool,
    budget: int,
) -> None:
    from saber.agents.baselines import BaselineId, solve_episode
    from saber.agents.gemini import GeminiProvider, KeyPool
    from saber.episodes.runner import run_oracle

    if not enable_paid:
        raise click.ClickException(
            "paid/free-tier LLM backend is OFF. Re-run with --enable-paid (operator opt-in) and a "
            "--budget cap. The agent never enables a billable backend by itself."
        )
    if provider != "gemini":  # pragma: no cover - only choice today
        raise click.ClickException(f"unknown provider {provider!r}")
    pool = KeyPool.from_file(key_pool)
    prov = GeminiProvider(model=model, pool=pool, enabled=True, budget_calls=budget)
    base = BaselineId.B1_SINGLE_AGENT if baseline == "b1" else BaselineId.B2_SPECIALISTS

    targets = [tuple(s.split(":", 1)) if ":" in s else (s, "default") for s in subtasks] or list(
        _SMOKE_SET
    )
    click.echo(
        f"provider=gemini model={model} baseline={base.value} pool={len(pool)} keys "
        f"budget={budget} seed={seed}"
    )
    click.echo(f"{'subtask':12s} {'svc':4s} {'score':>6s} {'oracle':>6s} {'validity':10s} note")
    click.echo("-" * 72)
    rows: list[dict[str, Any]] = []
    for sid, variant in targets:
        ep = build_episode(sid, seed, variant)
        oracle = run_oracle(ep).score.score
        res = solve_episode(base, ep, provider=prov)
        svc = ep.manifest.service
        note = next((t for t in res.score.trace if "invalid" in t.lower()), "")[:28]
        click.echo(
            f"{sid:12s} {svc:4s} {res.score.score:6.3f} {oracle:6.3f} "
            f"{res.score.validity.value:10s} {note}"
        )
        rows.append({"subtask_id": sid, "service": svc, "score": res.score.score, "oracle": oracle})
    mean = round(sum(r["score"] for r in rows) / len(rows), 4) if rows else 0.0
    click.echo("-" * 72)
    click.echo(
        f"episodes={len(rows)} mean_score={mean} billable_calls_used={prov.calls}/{budget} "
        f"keys_active={pool.active()}/{len(pool)} tokens_in/out={prov.input_tokens}/{prov.output_tokens}"
    )
    click.echo(
        "label: DEV_SIMULATION_ONLY — measures that the loop runs; NOT a validated benchmark."
    )


@cli.group("population", help="Run the live Gemini-driven agent population over the range (H5).")
def population() -> None:
    """Agent-population commands. Paid backends are OFF unless explicitly enabled."""


_POP_HEADER = (
    f"{'scenario':16s} {'seed':>4s} {'teams':14s} {'reqs':>4s} {'truth':>5s} "
    f"{'f1':>5s} {'prec':>5s} {'rec':>5s} {'status':12s} onmenu"
)


def _pop_row(ep: Any) -> str:
    return (
        f"{ep.scenario:16s} {ep.seed:4d} {ep.blue_team:14s} {ep.requests_sent:4d} "
        f"{ep.truth_malicious:5d} {ep.f1:5.2f} {ep.precision:5.2f} {ep.recall:5.2f} "
        f"{ep.case['status']:12s} {'yes' if ep.all_targets_on_menu else 'NO!'}"
    )


@population.command(
    "run", help="Red+clients+blue teams+orchestrator over live scenarios (+ --forever)."
)
@click.option("--scenarios", "scenarios_s", default="all", help="Comma list or 'all'.")
@click.option("--seeds", "seeds_s", default="1", show_default=True, help="Batch mode only.")
@click.option("--model", default="gemini-2.5-flash", show_default=True)
@click.option("--key-pool", default="keys_pool.txt", show_default=True)
@click.option("--enable-paid", is_flag=True, help="Operator opt-in to the API backend. Required.")
@click.option(
    "--budget",
    type=int,
    default=60,
    show_default=True,
    help="Max billable calls (hard safety valve; raise it for --forever).",
)
@click.option("--clients", type=int, default=1, show_default=True, help="Number of client agents.")
@click.option(
    "--blue-teams", "blue_teams_s", default="", help="Comma teams e.g. MON,HUNT,IR (else routed)."
)
@click.option(
    "--forever", is_flag=True, help="Run continuously until Ctrl+C, STOP file, or budget."
)
@click.option(
    "--interval",
    "interval_s",
    type=float,
    default=8.0,
    show_default=True,
    help="Seconds between episodes in --forever.",
)
@click.option(
    "--stop-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Create this file to stop a --forever run (default <out>/STOP).",
)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--office-url",
    default=None,
    help="agent-office viewer URL for 3D visualization (else $AGENT_OFFICE_URL if set).",
)
def population_run(
    scenarios_s: str,
    seeds_s: str,
    model: str,
    key_pool: str,
    enable_paid: bool,
    budget: int,
    clients: int,
    blue_teams_s: str,
    forever: bool,
    interval_s: float,
    stop_file: Path | None,
    out_dir: Path | None,
    office_url: str | None,
) -> None:
    from saber.agents.gemini import GeminiProvider, KeyPool
    from saber.domain.errors import BudgetExceeded, IntegrationBlocked
    from saber.population import OfficeEmitter, run_forever, run_population_episode
    from saber.population.loop import PopulationReport
    from saber.range.live import scenario_ids

    if not enable_paid:
        raise click.ClickException(
            "paid/free-tier LLM backend is OFF. Re-run with --enable-paid (operator opt-in) and a "
            "--budget cap. The agent never enables a billable backend by itself."
        )
    scenarios = (
        scenario_ids()
        if scenarios_s == "all"
        else [s.strip() for s in scenarios_s.split(",") if s.strip()]
    )
    seeds = [int(x) for x in seeds_s.split(",") if x.strip()]
    blue_teams = [t.strip().upper() for t in blue_teams_s.split(",") if t.strip()] or None
    pool = KeyPool.from_file(key_pool)
    prov = GeminiProvider(model=model, pool=pool, enabled=True, budget_calls=budget)
    workdir = out_dir or (Path("runs") / "population")
    emitter = OfficeEmitter(office_url)
    stopf = stop_file or (workdir / "STOP")

    click.echo(
        f"provider=gemini model={model} pool={len(pool)} keys budget={budget} "
        f"clients={clients} blue_teams={blue_teams or 'routed'} scenarios={scenarios}"
    )
    click.echo(
        f"agent-office viewer: {'ON @ ' + (emitter.url or '') if emitter.enabled else 'off'}"
    )
    if forever:
        click.echo(
            f"FOREVER mode: Ctrl+C or create {stopf} to stop; budget {budget} is the safety valve."
        )
    click.echo(_POP_HEADER)
    click.echo("-" * 96)

    def _print_ep(ep: Any, round_i: int = 0) -> None:
        click.echo(_pop_row(ep))

    report = PopulationReport()
    if forever:
        try:
            report = run_forever(
                scenarios,
                prov,
                workdir=workdir,
                emitter=emitter,
                n_clients=clients,
                blue_teams=blue_teams,
                interval_s=interval_s,
                stop_file=stopf,
                on_episode=_print_ep,
                on_wait=lambda msg: click.echo(f"… {msg}"),
            )
        except KeyboardInterrupt:
            click.echo("\n^C — stopping.")
    else:
        for scenario in scenarios:
            for seed in seeds:
                try:
                    ep = run_population_episode(
                        scenario,
                        seed,
                        prov,
                        workdir=workdir,
                        emitter=emitter,
                        n_clients=clients,
                        blue_teams=blue_teams,
                    )
                except (IntegrationBlocked, BudgetExceeded) as exc:
                    click.echo(f"{scenario:16s} {seed:4d} BLOCKED: {str(exc)[:60]}")
                    continue
                report.episodes.append(ep)
                _print_ep(ep)

    s = report.summary()
    click.echo("-" * 96)
    click.echo(
        f"episodes={s['n_episodes']} blue_f1_mean={s['blue_f1_mean']} "
        f"recall_mean={s['blue_recall_mean']} precision_mean={s['blue_precision_mean']}"
    )
    click.echo(
        f"billable_calls_used={prov.calls}/{budget} keys_active={pool.active()}/{len(pool)} "
        f"keys_disabled={pool.permanently_disabled()} tokens_in/out={s['total_tokens_in']}/{s['total_tokens_out']}"
    )
    click.echo(
        f"safety: all_targets_on_menu={s['all_targets_on_menu']} all_reset_ok={s['all_reset_ok']}"
    )
    rpath = workdir / "population_report.json"
    workdir.mkdir(parents=True, exist_ok=True)
    rpath.write_text(
        json.dumps(
            {"summary": s, "episodes": [e.row() for e in report.episodes]},
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    click.echo(f"label: {', '.join(s['labels'])}")
    click.echo(f"wrote {rpath}")


@population.command(
    "active-client",
    help="One always-on benign machine producing a continuous real log (scripted; --enable-paid=hybrid).",
)
@click.option("--seed", type=int, default=1, show_default=True)
@click.option(
    "--interval",
    "interval_s",
    type=float,
    default=20.0,
    show_default=True,
    help="Base seconds between ticks (jittered 0.6x-1.4x).",
)
@click.option(
    "--intensity",
    type=float,
    default=None,
    help="Requests/minute for the scripted profile (1-30). Default profile uses 8.",
)
@click.option(
    "--ticks",
    type=int,
    default=0,
    show_default=True,
    help="Stop after N ticks; 0 = run forever (until Ctrl+C or STOP file).",
)
@click.option(
    "--rhythm",
    type=click.Choice(["real", "flat"]),
    default="real",
    show_default=True,
    help="'real' shapes intensity by local hour (office hours busy, night idle).",
)
@click.option(
    "--enable-paid",
    is_flag=True,
    help="Operator opt-in: use the LLM profiler (HYBRID). Off = pure scripted, no quota.",
)
@click.option("--model", default="gemini-2.5-flash", show_default=True)
@click.option("--key-pool", default="keys_pool.txt", show_default=True)
@click.option(
    "--budget",
    type=int,
    default=200,
    show_default=True,
    help="Max billable profiler calls (hard safety valve; sparse by design).",
)
@click.option(
    "--profile-refresh",
    "profile_refresh_s",
    type=float,
    default=900.0,
    show_default=True,
    help="Seconds between LLM profile refreshes (hybrid only).",
)
@click.option(
    "--stop-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Create this file to stop a forever run (default <out>/STOP).",
)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
@click.option(
    "--office-url", default=None, help="agent-office viewer URL (else $AGENT_OFFICE_URL if set)."
)
def population_active_client(
    seed: int,
    interval_s: float,
    intensity: float | None,
    ticks: int,
    rhythm: str,
    enable_paid: bool,
    model: str,
    key_pool: str,
    budget: int,
    profile_refresh_s: float,
    stop_file: Path | None,
    out_dir: Path | None,
    office_url: str | None,
) -> None:
    from saber.population import OfficeEmitter, run_active_client

    workdir = out_dir or (Path("runs") / "population")
    stopf = stop_file or (workdir / "STOP")
    emitter = OfficeEmitter(office_url)

    provider: Any = None
    pool = None
    if enable_paid:
        from saber.agents.gemini import GeminiProvider, KeyPool

        pool = KeyPool.from_file(key_pool)
        provider = GeminiProvider(model=model, pool=pool, enabled=True, budget_calls=budget)
        click.echo(f"engine=HYBRID provider=gemini model={model} pool={len(pool)} keys "
                   f"budget={budget} refresh={profile_refresh_s:.0f}s")  # fmt: skip
    else:
        click.echo("engine=SCRIPTED (no LLM, no quota). Add --enable-paid for the hybrid profiler.")
    click.echo(f"seed={seed} interval={interval_s:.0f}s rhythm={rhythm} "
               f"ticks={'forever' if ticks <= 0 else ticks}")  # fmt: skip
    click.echo(
        f"agent-office viewer: {'ON @ ' + (emitter.url or '') if emitter.enabled else 'off'}"
    )
    if ticks <= 0:
        click.echo(f"Running until Ctrl+C or create {stopf}.")
    click.echo(f"{'tick':>5s} {'hour':>4s} {'phase':>5s} {'sent':>4s} {'total':>6s} "
               f"{'profile':16s} {'int':>4s} llm")  # fmt: skip
    click.echo("-" * 60)

    def _on_tick(tick: int, st: dict[str, Any]) -> None:
        click.echo(
            f"{st['tick']:5d} {st['hour']:4d} {st['phase']:5.2f} {st['sent']:4d} "
            f"{st['requests_sent']:6d} {st['profile_source']:16s} {st['intensity']:4.0f} "
            f"{st['llm_calls']}"
        )

    try:
        report = run_active_client(
            provider,
            workdir=workdir,
            seed=seed,
            base_interval_s=interval_s,
            base_intensity=intensity,
            profile_refresh_s=profile_refresh_s,
            rhythm=rhythm,
            max_ticks=None if ticks <= 0 else ticks,
            stop_file=stopf,
            emitter=emitter,
            on_tick=_on_tick,
        )
    except KeyboardInterrupt:
        click.echo("\n^C — stopping.")
        return

    click.echo("-" * 60)
    click.echo(f"ticks={report.ticks} benign_requests={report.requests_sent} "
               f"log_lines={report.log_lines} reset_ok={report.reset_ok}")  # fmt: skip
    click.echo(f"by_category={report.by_category}")
    if enable_paid and provider is not None and pool is not None:
        click.echo(f"billable_profiler_calls={provider.calls}/{budget} "
                   f"keys_active={pool.active()}/{len(pool)}")  # fmt: skip
    rpath = workdir / "active_client_report.json"
    workdir.mkdir(parents=True, exist_ok=True)
    rpath.write_text(
        json.dumps(report.row(), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    click.echo(f"label: {', '.join(report.labels)}")
    click.echo(f"wrote {rpath}")


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


cli.add_command(world)
cli.add_command(env)
cli.add_command(lab)
cli.add_command(training)


if __name__ == "__main__":
    main()
