"""Operator commands for the persistent local world."""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from saber.agents.gemini import KeyPool
from saber.agents.provider import LLMProvider
from saber.domain.errors import SaberError
from saber.population.office import OfficeEmitter
from saber.world.key_layout import TeamKeyLayout
from saber.world.models import WorldConfig, default_config
from saber.world.quota import QuotaProvider, TeamQuotaProvider
from saber.world.runtime import Runner, WorldLock, atomic_json
from saber.world.store import Store


@click.group(
    help="Persistent local client/red/blue world. Synthetic data; real HTTP and durable application effects."
)
def world() -> None:
    pass


@world.command("init", help="Create an editable actor roster and world configuration.")
@click.option(
    "--out", type=click.Path(path_type=Path), default=Path("runs/world"), show_default=True
)
@click.option("--clients", type=click.IntRange(1, 100), default=6, show_default=True)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--tick-seconds", type=click.FloatRange(0.01, 3600), default=2.0, show_default=True)
def init_world(out: Path, clients: int, seed: int, tick_seconds: float) -> None:
    if (out / "config.json").exists() or (out / "world.sqlite3").exists():
        raise click.ClickException(
            "World already exists. Edit its config before first run, or choose a new directory."
        )
    config = default_config(clients, seed).model_copy(update={"tick_seconds": tick_seconds})
    out.mkdir(parents=True, exist_ok=True)
    atomic_json(out / "config.json", config.model_dump(mode="json"))
    click.echo(f"Created {out / 'config.json'} ({len(config.actors)} actors).")


@world.command(
    "run", help="Run/resume one shared world. Default: 30 ticks, scripted. --forever keeps running."
)
@click.option(
    "--out", type=click.Path(path_type=Path), default=Path("runs/world"), show_default=True
)
@click.option("--ticks", type=click.IntRange(1), default=30, show_default=True)
@click.option("--forever", is_flag=True)
@click.option(
    "--resume", is_flag=True, help="Explicitly clear a previous STOP request before resuming."
)
@click.option(
    "--llm",
    is_flag=True,
    help="Opt in to real Gemini API calls under your projects' billing/quota settings.",
)
@click.option(
    "--call-budget",
    type=click.IntRange(1),
    default=None,
    help="Required with --llm. Maximum cumulative HTTP attempts for this world, including restarts.",
)
@click.option(
    "--key-pool", type=click.Path(path_type=Path, dir_okay=False), default=Path("keys_pool.txt")
)
@click.option("--model", default="gemini-3.5-flash-lite", show_default=True)
@click.option(
    "--key-layout",
    type=click.Choice(["teams", "shared"]),
    default="teams",
    show_default=True,
    help="teams: first 200 keys for clients, next 200 red, rest blue; queues never borrow keys.",
)
@click.option("--client-keys", type=click.IntRange(1), default=200, show_default=True)
@click.option("--red-keys", type=click.IntRange(1), default=200, show_default=True)
@click.option(
    "--project-map",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Optional JSON mapping zero-based deduplicated key indices to project aliases.",
)
@click.option("--project-rpm", type=click.IntRange(1), default=2, show_default=True)
@click.option("--project-rpd", type=click.IntRange(1), default=20, show_default=True)
@click.option("--project-tpm", type=click.IntRange(1), default=100000, show_default=True)
@click.option("--office-url", default=None, help="Optional existing agent-office viewer URL.")
def run_world(
    out: Path,
    ticks: int,
    forever: bool,
    resume: bool,
    llm: bool,
    call_budget: int | None,
    key_pool: Path,
    model: str,
    key_layout: str,
    client_keys: int,
    red_keys: int,
    project_map: Path | None,
    project_rpm: int,
    project_rpd: int,
    project_tpm: int,
    office_url: str | None,
) -> None:
    if llm and call_budget is None:
        raise click.ClickException("--llm requires an explicit --call-budget. No API calls made.")
    if not llm and call_budget is not None:
        raise click.ClickException("--call-budget requires --llm.")
    try:
        with ExitStack() as resources:
            resources.enter_context(WorldLock(out))
            path = out / "config.json"
            config = (
                WorldConfig.model_validate_json(path.read_text(encoding="utf-8"))
                if path.exists()
                else default_config()
            )
            if not path.exists():
                atomic_json(path, config.model_dump(mode="json"))
            if resume:
                (out / "STOP").unlink(missing_ok=True)
            elif (out / "STOP").exists():
                raise click.ClickException(
                    "STOP exists. Use --resume when you want this world to continue."
                )
            store = Store(out)
            resources.callback(store.close)
            provider: LLMProvider | None = None
            if llm:
                groups = json.loads(project_map.read_text(encoding="utf-8")) if project_map else {}
                if not isinstance(groups, dict) or any(
                    not isinstance(k, str) or not isinstance(v, str) for k, v in groups.items()
                ):
                    raise ValueError(
                        "Project map must be an object of key-index strings to project alias strings."
                    )
                if key_layout == "teams":
                    layout = TeamKeyLayout.from_file(
                        key_pool, client_keys=client_keys, red_keys=red_keys
                    )
                    provider = TeamQuotaProvider(
                        store,
                        layout,
                        model=model,
                        call_budget=int(call_budget or 0),
                        rpm=project_rpm,
                        rpd=project_rpd,
                        tpm=project_tpm,
                        project_groups=groups,
                    )
                    click.echo(
                        f"Gemini key queues: {layout.counts()} (file order; independent team queues)."
                    )
                else:
                    provider = QuotaProvider(
                        store,
                        KeyPool.from_file(key_pool),
                        model=model,
                        call_budget=int(call_budget or 0),
                        rpm=project_rpm,
                        rpd=project_rpd,
                        tpm=project_tpm,
                        project_groups=groups,
                    )
            runner = Runner(store, config, provider=provider, emitter=OfficeEmitter(office_url))
            resources.callback(runner.close)
            click.echo(
                f"World: {out.resolve()} | actors={len(config.actors)} | engine={'HYBRID' if llm else 'SCRIPTED'}"
            )
            click.echo(
                f'Local tool service: {runner.server.url} (authenticated). Stop: saber world stop --out "{out}"'
            )

            def progress(report: dict[str, Any]) -> None:
                m = report["metrics"]
                click.echo(
                    f"tick={report['tick']} requests={m['requests']} client_failures={m['client_failures']} "
                    f"cases={m['cases']} verified_responses={m['verified_responses']} collected_bytes={m['collected_bytes']}"
                )

            report = runner.run(ticks=None if forever else ticks, on_tick=progress)
            click.echo(f"Stopped: {report['stop_reason']}. Checkpoint and report saved in {out}.")
            click.echo("DEV_SIMULATION_ONLY: local application lab; no READY_BENCHMARK promotion.")
    except (OSError, ValueError, RuntimeError, ValidationError, SaberError) as exc:
        raise click.ClickException(str(exc)) from None


@world.command("status", help="Read the latest operator report without exposing it to agents.")
@click.option(
    "--out", type=click.Path(path_type=Path), default=Path("runs/world"), show_default=True
)
def status_world(out: Path) -> None:
    path = out / "report.json"
    if not path.exists():
        raise click.ClickException("No world report yet.")
    click.echo(path.read_text(encoding="utf-8"))


@world.command("stop", help="Request a graceful stop. Data and checkpoints are preserved.")
@click.option(
    "--out", type=click.Path(path_type=Path), default=Path("runs/world"), show_default=True
)
def stop_world(out: Path) -> None:
    if not (out / "config.json").exists():
        raise click.ClickException("No world found at this path.")
    (out / "STOP").write_text("operator stop\n", encoding="utf-8")
    click.echo(f"Stop requested: {out / 'STOP'}")


@world.command(
    "supervise",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    help="Run forever with bounded crash restarts. Extra options are passed to 'world run'.",
)
@click.option(
    "--out", type=click.Path(path_type=Path), default=Path("runs/world"), show_default=True
)
@click.option("--max-restarts", type=click.IntRange(0, 20), default=3, show_default=True)
@click.option("--backoff", type=click.FloatRange(0, 60), default=5.0, show_default=True)
@click.pass_context
def supervise_world(ctx: click.Context, out: Path, max_restarts: int, backoff: float) -> None:
    from saber.world.supervisor import supervise

    # Resuming a STOP request is an explicit operator action, not a crash-restart behavior.
    extra = list(ctx.args)
    if "--resume" in extra:
        (out / "STOP").unlink(missing_ok=True)
        extra.remove("--resume")
    try:
        code = supervise(out, extra, max_restarts=max_restarts, backoff=backoff, emit=click.echo)
    except (OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from None
    if code:
        raise click.ClickException(f"World worker exited {code}; see the worker error above.")
