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
