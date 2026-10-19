"""`saber` CLI entry point. Subcommands are registered progressively by later tasks."""

from __future__ import annotations

import click

from saber import __version__


@click.group(help="SABER SOC benchmark CLI (offline-first, no live infrastructure by default).")
@click.version_option(__version__, prog_name="saber")
def cli() -> None:
    """Root command group."""


def main() -> None:
    cli(prog_name="saber")


if __name__ == "__main__":
    main()
