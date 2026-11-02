"""Independent Linux namespace process/socket and workspace-file polling sensor.

Polling can miss short-lived activity; kernel audit/Sysmon guest collectors supplement
it. This component never claims kernel-wide visibility or fabricates missing events.
"""

from __future__ import annotations

import hashlib
import os
import socket
import threading
from pathlib import Path
from typing import Any

from saber.lab.events import Emitter


class PollSensor:
    def __init__(self, emitter: Emitter, workspace: Path, interval: float = 1) -> None:
        self.emitter, self.workspace, self.interval = emitter, workspace, interval
        self.processes: dict[str, str] = {}
        self.files: dict[str, str] = {}
        self.connections: set[str] = set()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def scan(self) -> None:
        if os.name == "posix" and Path("/proc").exists():
            observed = {}
            for path in Path("/proc").iterdir():
                if not path.name.isdecimal():
                    continue
                try:
                    stat = (path / "stat").read_text()
                    fields = stat[stat.rfind(")") + 2 :].split()
                    start = fields[19]
                    observed[path.name] = start
                    if self.processes.get(path.name) == start:
                        continue
                    command = (
                        (path / "cmdline")
                        .read_bytes()[:4096]
                        .replace(b"\0", b" ")
                        .decode(errors="replace")
                    )
                    self.emitter.emit(
                        "process.observed",
                        {
                            "pid": int(path.name),
                            "ppid": int(fields[1]),
                            "start_ticks": start,
                            "command_line": command,
                        },
                        "linux-proc-poll-v1",
                    )
                except (OSError, ValueError, IndexError):
                    continue
            self.processes = observed
            connections = set()
            try:
                for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
                    fields = line.split()
                    identity = ":".join([fields[1], fields[2], fields[3], fields[9]])
                    connections.add(identity)
                    if identity in self.connections:
                        continue

                    def address(value: str) -> str:
                        ip, port = value.split(":")
                        return f"{socket.inet_ntoa(bytes.fromhex(ip)[::-1])}:{int(port, 16)}"

                    self.emitter.emit(
                        "network.observed",
                        {
                            "local": address(fields[1]),
                            "remote": address(fields[2]),
                            "state_hex": fields[3],
                            "inode": fields[9],
                            "protocol": "tcp4",
                        },
                        "linux-proc-poll-v1",
                    )
            except (OSError, ValueError, IndexError):
                pass
            self.connections = connections
        observed_files = {}
        for path in self.workspace.rglob("*") if self.workspace.exists() else []:
            if (
                path.is_symlink()
                or not path.is_file()
                or not path.resolve().is_relative_to(self.workspace.resolve())
            ):
                continue
            try:
                size = path.stat().st_size
                if size > 2_000_000:
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                relative = path.relative_to(self.workspace).as_posix()
                observed_files[relative] = digest
                if self.files.get(relative) != digest:
                    self.emitter.emit(
                        "file.observed",
                        {"path": relative, "bytes": size, "sha256": digest},
                        "workspace-fim-poll-v1",
                    )
            except OSError:
                continue
        for name in self.files.keys() - observed_files.keys():
            self.emitter.emit("file.removed", {"path": name}, "workspace-fim-poll-v1")
        self.files = observed_files

    def start(self) -> None:
        def loop() -> None:
            while not self.stop.wait(self.interval):
                try:
                    self.scan()
                except OSError:
                    self.stop.set()  # exhausted evidence budget must not silently lose logs

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)


def sensor_coverage() -> dict[str, Any]:
    return {
        "process_network": "linux-namespace-polling"
        if os.name == "posix"
        else "requires-windows-event-collector",
        "file": "workspace-only-polling",
        "kernel_capture": False,
        "short_lived_events_may_be_missed": True,
    }
