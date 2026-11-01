"""Container entrypoint: keep STOP semantics and finish in-flight work on SIGTERM."""

from __future__ import annotations

import argparse
import os
import re
import signal
from pathlib import Path
from types import FrameType

from saber.environments.lifecycle import prepare_world
from saber.environments.models import read_config
from saber.world.cli import run_world
from saber.world.runtime import WorldLock, atomic_json


def consume_resume(out: Path, token: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        return
    import json

    with WorldLock(out):
        receipt = out / "resume-request.json"
        previous = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
        if previous.get("token") == token:
            return
        # Record before clearing STOP, so a crash never grants a second clear.
        atomic_json(receipt, {"token": token})
        (out / "STOP").unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--ticks", type=int)
    args = parser.parse_args()
    if args.ticks is not None and args.ticks < 1:
        parser.error("Ticks must be positive.")
    try:
        prepare_world(read_config(args.config), args.out)
    except (OSError, ValueError, RuntimeError):
        parser.error("Cannot prepare world; inspect configuration and data directory.")

    def stop(signum: int, frame: FrameType | None) -> None:
        (args.out / "STOP").write_text("container stop requested\n", encoding="utf-8")

    previous = signal.signal(signal.SIGTERM, stop)
    argv = ["--out", str(args.out)]
    argv += ["--ticks", str(args.ticks)] if args.ticks else ["--forever"]
    consume_resume(args.out, os.environ.get("SABER_ENV_RESUME", "0"))
    if os.environ.get("SABER_ENV_LLM") == "1":
        argv += [
            "--llm",
            "--call-budget",
            os.environ.get("SABER_ENV_CALL_BUDGET", "0"),
            "--key-pool",
            "/run/secrets/gemini-pool",
            "--model",
            os.environ.get("SABER_ENV_MODEL", "gemini-3.5-flash-lite"),
        ]
    try:
        run_world.main(args=argv, prog_name="saber world run")
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    main()
