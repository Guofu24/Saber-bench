"""Restart a crashed world worker with backoff; preserve its checkpoint and budget."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from saber.world.runtime import WorldLock


def supervise(
    out: Path,
    worker_args: list[str],
    *,
    max_restarts: int = 3,
    backoff: float = 5,
    emit: Callable[[str], None] = print,
) -> int:
    stop = out / "STOP"
    command = [
        sys.executable,
        "-m",
        "saber.cli.main",
        "world",
        "run",
        "--out",
        str(out),
        "--forever",
        *worker_args,
    ]
    with WorldLock(out / ".supervisor"):
        for attempt in range(max_restarts + 1):
            if stop.exists():
                emit("STOP exists; supervisor stopped.")
                return 0
            emit(f"Starting world worker (restart {attempt}/{max_restarts}).")
            child = subprocess.Popen(command)  # fixed executable/module, no shell
            try:
                code = child.wait()
            except KeyboardInterrupt:
                stop.write_text("supervisor interrupted\n", encoding="utf-8")
                try:
                    child.wait(timeout=65)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=5)
                return 0
            if code == 0 or stop.exists():
                return code
            if attempt == max_restarts:
                emit(
                    f"Worker failed repeatedly (exit {code}); stopped after {max_restarts} restarts."
                )
                return code
            wait = min(backoff * 2**attempt, 60)
            emit(f"Worker exited {code}; resuming checkpoint in {wait:.1f}s.")
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                if stop.exists():
                    return 0
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
    return 0
