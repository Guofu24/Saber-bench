"""Operator commands for stateful scenarios: list, show, validate, run, compare."""

from __future__ import annotations

import json
from pathlib import Path

import click

from saber.world import scenario


@click.group(
    "scenario",
    help="Versioned stateful scenarios over the single-app world (DEV_SIMULATION_ONLY).",
)
def scenario_cli() -> None:
    pass


@scenario_cli.command("list", help="List scenario families, split and declared feasibility.")
def list_scenarios() -> None:
    for fam in scenario.FAMILIES:
        s = scenario.make(fam)
        click.echo(
            f"{fam:24} {s.split:7} obj={s.objective:16} expect={s.expected_feasibility:14} :: {s.notes}"
        )


@scenario_cli.command(
    "show", help="Print one scenario spec (operator view, includes private fields)."
)
@click.option("--family", required=True)
@click.option("--seed", type=int, default=1, show_default=True)
def show(family: str, seed: int) -> None:
    try:
        s = scenario.make(family, seed)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(s.model_dump(mode="json"), indent=2, ensure_ascii=False))


@scenario_cli.command("validate", help="Independently check feasibility vs the declared label.")
@click.option("--family", default=None, help="Omit to validate every family.")
@click.option("--seed", type=int, default=1, show_default=True)
def validate_cmd(family: str | None, seed: int) -> None:
    families = [family] if family else list(scenario.FAMILIES)
    ok = True
    for fam in families:
        try:
            v = scenario.validate(scenario.make(fam, seed))
        except ValueError as exc:
            raise click.ClickException(str(exc)) from None
        ok = ok and v["matches_expected"]
        click.echo(f"{fam:24} {v['feasibility']:14} match={v['matches_expected']} :: {v['reason']}")
    if not ok:
        raise click.ClickException("a scenario disagrees with its declared feasibility")


@scenario_cli.command("run", help="Materialise and run one scenario under one red policy.")
@click.option("--family", required=True)
@click.option("--seed", type=int, default=1, show_default=True)
@click.option("--policy", type=click.Choice(["adaptive", "naive", "random"]), default="adaptive")
@click.option(
    "--out", type=click.Path(path_type=Path), default=Path("runs/scenario"), show_default=True
)
def run_cmd(family: str, seed: int, policy: str, out: Path) -> None:
    try:
        res = scenario.run_scenario(scenario.make(family, seed), policy, out)
    except (ValueError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(
        json.dumps(
            {k: v for k, v in res.items() if k != "objectives"}, indent=2, ensure_ascii=False
        )
    )
    click.echo("DEV_SIMULATION_ONLY: local application lab; no READY_BENCHMARK promotion.")


@scenario_cli.command("compare", help="Run adaptive/naive/random red under one scenario.")
@click.option("--family", required=True)
@click.option("--seed", type=int, default=1, show_default=True)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("runs/scenario-compare"),
    show_default=True,
)
def compare_cmd(family: str, seed: int, out: Path) -> None:
    try:
        s = scenario.make(family, seed)
        rows = scenario.compare_policies(s, out)
    except (ValueError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(
        f"family={family} feasibility={rows[0]['feasibility']} expected={s.expected_feasibility}"
    )
    for r in rows:
        click.echo(
            f"  {r['policy']:9} verified={r['verified']}/{r['total']} "
            f"by_blue={r['blocked_by_blue']} by_env={r['blocked_by_environment']} "
            f"rejected={r['rejected_actions']} steps={r['steps_to_objective']} "
            f"util={r['client_mission_utility']}"
        )
    click.echo("DEV_SIMULATION_ONLY: feasibility is measured independently of red competence.")


@scenario_cli.command(
    "witness", help="Execute the candidate path and verify it (structural, no blue)."
)
@click.option("--family", required=True)
@click.option("--seed", type=int, default=1, show_default=True)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("runs/scenario-witness"),
    show_default=True,
)
@click.option("--trace/--no-trace", default=True, help="Include the full executed action trace.")
def witness_cmd(family: str, seed: int, out: Path, trace: bool) -> None:
    from saber.world import witness

    try:
        res = witness.run_witness(scenario.make(family, seed), out)
    except (ValueError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from None
    view = res if trace else {k: v for k, v in res.items() if k != "trace"}
    click.echo(json.dumps(view, indent=2, ensure_ascii=False))
    click.echo("DEV_SIMULATION_ONLY: structural feasibility only; no READY_BENCHMARK promotion.")


@scenario_cli.command(
    "witness-all", help="Run the executable witness over all families; report agreement."
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("runs/scenario-witness-all"),
    show_default=True,
)
def witness_all_cmd(out: Path) -> None:
    from saber.world import witness

    rows = witness.witness_all(out)
    for r in rows:
        click.echo(
            f"{r['family']:24} static={r['static_feasibility']:14} "
            f"witness={r['status']:16} verified={r['verified']} agree={r['agree']}"
        )
    disagree = [r["family"] for r in rows if not r["agree"]]
    tail = f"; disagree={disagree}" if disagree else ""
    click.echo(f"agreement: {len(rows) - len(disagree)}/{len(rows)}{tail}")


@scenario_cli.command(
    "multipath", help="Witness each distinct path to the objective and a recovery episode."
)
@click.option("--family", required=True)
@click.option("--seed", type=int, default=1, show_default=True)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("runs/scenario-multipath"),
    show_default=True,
)
@click.option("--trace/--no-trace", default=True, help="Include the executed action traces.")
def multipath_cmd(family: str, seed: int, out: Path, trace: bool) -> None:
    from saber.world import witness

    try:
        res = witness.witness_multipath(scenario.make(family, seed), out)
    except (ValueError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from None
    if not trace:
        res = {k: v for k, v in res.items() if k not in ("per_path", "after_control", "recovery")}
    click.echo(json.dumps(res, indent=2, ensure_ascii=False))
    click.echo("DEV_SIMULATION_ONLY: structural multi-path feasibility; no READY_BENCHMARK.")


@scenario_cli.command(
    "multipath-all", help="Summarise the multi-path witness over every multi-path family."
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("runs/scenario-multipath-all"),
    show_default=True,
)
def multipath_all_cmd(out: Path) -> None:
    from saber.world import witness

    for r in witness.witness_multipath_all(out):
        rec = r["recovery"]
        click.echo(
            f"{r['family']:30} static={r['static_feasibility']:14} paths={r['distinct_paths']} "
            f"verified={r['verified_paths']} blocked={r['blocked_paths']} "
            f"recovery={rec['status']} via={rec['verified_path']}"
        )
    click.echo("DEV_SIMULATION_ONLY: feasibility is measured independently of red competence.")


@scenario_cli.command(
    "evaluate", help="Compare all red policies on a family over several seeds (Phase 4.1B-2)."
)
@click.option("--family", required=True)
@click.option("--seeds", type=int, default=8, show_default=True, help="Seeds 1..N (permutations).")
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("runs/scenario-evaluate"),
    show_default=True,
)
def evaluate_cmd(family: str, seeds: int, out: Path) -> None:
    from saber.world import red_eval

    try:
        res = red_eval.compare_policies(
            scenario.make(family), out, seeds=tuple(range(1, seeds + 1))
        )
    except (ValueError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(
        f"family={family} budget={res['budget']} optimal_witness={res['optimal_witness_length']}"
    )
    for policy, a in res["policies"].items():
        click.echo(
            f"  {policy:9} verified={a['verified']}/{a['n']} rate={a['verified_rate']} "
            f"ci95={a['verified_rate_ci95']} steps={a['mean_steps_when_verified']} "
            f"diag={a['diagnoses']}"
        )
    click.echo("DEV_SIMULATION_ONLY: the offline witness length is a clairvoyant upper bound.")


@scenario_cli.command(
    "budget-sweep", help="Sweep one family's config across action budgets; online vs adaptive."
)
@click.option("--family", default="gated_longer_alternative", show_default=True)
@click.option("--budgets", default="6,8,10,12,15", show_default=True)
@click.option("--seeds", type=int, default=8, show_default=True)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("runs/scenario-budget-sweep"),
    show_default=True,
)
def budget_sweep_cmd(family: str, budgets: str, seeds: int, out: Path) -> None:
    from saber.world import red_eval

    try:
        parsed = tuple(int(b) for b in budgets.split(","))
        rows = red_eval.budget_sweep(
            scenario.make(family), out, budgets=parsed, seeds=tuple(range(1, seeds + 1))
        )
    except (ValueError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from None
    for r in rows:
        a, o = r["policies"]["adaptive"], r["policies"]["online"]
        click.echo(
            f"budget={r['budget']:>2} feas={r['feasibility']:14} W={r['optimal_witness_length']} "
            f"adaptive={a['verified']}/{a['n']} online={o['verified']}/{o['n']} "
            f"ci95={o['verified_rate_ci95']} diag={o['diagnoses']}"
        )
    click.echo("DEV_SIMULATION_ONLY: the scenario config is identical across budgets.")


@scenario_cli.command(
    "observability",
    help="Compare policies on one family across O0/O1/O2 observability (Phase 4.1C-1).",
)
@click.option("--family", default="prereq_multiple_candidates", show_default=True)
@click.option("--seeds", type=int, default=32, show_default=True, help="Seeds 1..N (permutations).")
@click.option("--policies", default="online,adaptive", show_default=True)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("runs/scenario-observability"),
    show_default=True,
)
def observability_cmd(family: str, seeds: int, policies: str, out: Path) -> None:
    from saber.world import red_eval

    try:
        chosen = tuple(p.strip() for p in policies.split(","))
        study = red_eval.observability_study(
            scenario.make(family), out, seeds=tuple(range(1, seeds + 1)), policies=chosen
        )
    except (ValueError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(
        f"family={study['scenario_family']} split={study['split']} budget={study['budget']} "
        f"optimal_witness={study['optimal_witness_length']} seeds={len(study['seeds'])}"
    )
    for level, policies_agg in study["levels"].items():
        click.echo(f"  [{level}]")
        for policy, a in policies_agg.items():
            click.echo(
                f"    {policy:9} verified={a['verified']}/{a['n']} ci95={a['verified_rate_ci95']} "
                f"probes={a['mean_public_probes']} overhead={a['mean_actions_over_optimal']} "
                f"ident={a['dependency_identification']} diag={a['diagnoses']}"
            )
    click.echo("DEV_SIMULATION_ONLY: identical structure across levels; only evidence changes.")
