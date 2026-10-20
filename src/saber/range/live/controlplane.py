"""Live lab control/observation plane: run a real service, drive traffic, collect genuine evidence.

The control plane is independent of the agent: it starts the loopback service, sends the scenario's
benign + inert-probe traffic, collects the service's REAL access log, derives ground truth from the
server-side observations (not from the agent and not merely from the generation labels — those are
kept only for a consistency cross-check), kills the service (clean reset), and writes hashed +
timestamped raw evidence. No telemetry is fabricated; nothing external is contacted.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlsplit

from saber.range.live.episode import EvidenceFile, LiveEpisode
from saber.range.live.scenarios import BRUTEFORCE_THRESHOLD, SCENARIOS
from saber.subtasks._hv.common import Rng

_READY_TIMEOUT_S = 15.0
_REQ_TIMEOUT_S = 5.0


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sqli_target(target: str) -> bool:
    """Independent server-side SQLi detector (distinct from the agent's rule and the gen labels)."""
    d = unquote_plus(unquote_plus(target)).lower()
    checks = (
        bool(re.search(r"union\s+select", d)),
        bool(re.search(r"drop\s+table", d)),
        "sleep(" in d,
        bool(re.search(r"admin'\s*--", d)),
        bool(re.search(r"'\s*or\s+", d)),
        bool(re.search(r"\bor\s+1\s*=\s*1", d)),
        bool(re.search(r"'1'\s*=\s*'1", d)),
    )
    return any(checks)


class LiveLab:
    """Owns the service subprocess and the evidence directory for one episode."""

    def __init__(
        self, evidence_dir: Path, *, backend: str = "process-local", fs_root: Path | None = None
    ) -> None:
        self.evidence_dir = evidence_dir
        self.backend = backend
        self.access_log = evidence_dir / "access.log"
        self.fs_root = fs_root  # sandboxed webroot for fs-change scenarios (optional)
        self._ready_file = evidence_dir / "port.txt"
        self._proc: subprocess.Popen[bytes] | None = None
        self.port: int | None = None

    def start(self) -> None:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        argv = [
            sys.executable,
            "-I",
            "-m",
            "saber.range.live.service_main",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--log",
            str(self.access_log),
            "--ready-file",
            str(self._ready_file),
        ]
        if self.fs_root is not None:
            self.fs_root.mkdir(parents=True, exist_ok=True)
            argv += ["--fsroot", str(self.fs_root)]
        self._ready_file.unlink(missing_ok=True)  # never attach to a prior run's port
        self._proc = subprocess.Popen(argv)  # noqa: S603 - fixed argv, no shell
        deadline = time.monotonic() + _READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if self._ready_file.exists() and self._ready_file.read_text(encoding="utf-8").strip():
                self.port = int(self._ready_file.read_text(encoding="utf-8").strip())
                return
            if self._proc.poll() is not None:
                raise RuntimeError(f"service exited early rc={self._proc.returncode}")
            time.sleep(0.1)
        raise TimeoutError("service did not become ready in time")

    def send(self, plan: list[dict[str, Any]]) -> int:
        """Send each planned request at the loopback service; return count actually sent."""
        if self.port is None:
            raise RuntimeError("lab not started")
        sent = 0
        for req in plan:
            target = str(req["target"])
            if not target.startswith("/"):
                # Guard the loopback guarantee: a non-"/"-prefixed target (e.g. "@evil/x" or a full
                # URL) could redirect the request off-box. Refuse rather than dispatch.
                raise ValueError(f"refusing non-path request target {target!r}")
            url = f"http://127.0.0.1:{self.port}{target}"
            try:
                r = urllib.request.urlopen(url, timeout=_REQ_TIMEOUT_S)  # noqa: S310 - loopback only
                r.read()
                r.close()
            except urllib.error.HTTPError:
                pass  # a 401 is an expected, logged outcome
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
            sent += 1
        return sent

    def stop(self) -> int | None:
        """Terminate the service (clean reset) and return its exit code."""
        if self._proc is None:
            return None
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - fallback
                self._proc.kill()
                self._proc.wait(timeout=5)
        return self._proc.returncode

    def process_dead(self) -> bool:
        """Definitive reset signal: the service subprocess has exited."""
        return self._proc is not None and self._proc.poll() is not None

    def confirm_reset(self, timeout_s: float = 3.0) -> bool:
        """Reset is clean iff the process is dead AND the port stops accepting (retried to settle)."""
        if not self.process_dead():
            return False
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not self.is_listening():
                return True
            time.sleep(0.1)
        return not self.is_listening()

    def is_listening(self) -> bool:
        """True iff the service port still accepts a connection (used to verify reset)."""
        if self.port is None:
            return False
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", self.port)) == 0

    def read_log_lines(self) -> list[str]:
        if not self.access_log.exists():
            return []
        return [ln for ln in self.access_log.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _login_user(target: str) -> str:
    return (parse_qs(urlsplit(target).query).get("user") or [""])[0]


def _put_name(target: str) -> str:
    return Path((parse_qs(urlsplit(target).query).get("name") or [""])[0]).name


_SCRIPT_EXTS = (".php", ".aspx", ".jsp", ".cgi")


def _is_unauthorized_file(fs_root: Path, name: str) -> bool:
    """Independent server-side-state check: a webroot file is unauthorized iff it is a server-side
    script that actually exists on disk carrying the (inert) webshell marker."""
    if not name.lower().endswith(_SCRIPT_EXTS):
        return False
    f = fs_root / name
    return f.is_file() and "<?php" in f.read_text(encoding="utf-8", errors="replace")


def _derive_truth(
    scenario: str, lines: list[dict[str, Any]], fs_root: Path | None = None
) -> set[int]:
    """Server-side ground truth: indices of malicious log lines, derived from observations.

    web_sqli_probe: malicious iff the decoded target carries a SQL token COMBINATION (a SQL *word*
    in a benign request is NOT flagged). auth_bruteforce: brute force is a VOLUME phenomenon — a 401
    is malicious only above BRUTEFORCE_THRESHOLD per user (a single benign typo is a hard negative).
    fs_change: a /fs/put line is malicious iff it wrote a server-side script that actually exists in
    the webroot with the webshell marker (derived from the REAL resulting filesystem state).
    """
    probe: set[int] = set()
    if scenario == "web_sqli_probe":
        for i, rec in enumerate(lines):
            if _is_sqli_target(str(rec.get("target", ""))):
                probe.add(i)
    elif scenario == "auth_bruteforce":
        fails: dict[str, int] = {}
        for rec in lines:
            if rec.get("status") == 401:
                u = _login_user(str(rec.get("target", "")))
                fails[u] = fails.get(u, 0) + 1
        for i, rec in enumerate(lines):
            if (
                rec.get("status") == 401
                and fails.get(_login_user(str(rec.get("target", ""))), 0) >= BRUTEFORCE_THRESHOLD
            ):
                probe.add(i)
    elif scenario == "fs_change" and fs_root is not None:
        for i, rec in enumerate(lines):
            if "/fs/put" in str(rec.get("target", "")) and _is_unauthorized_file(
                fs_root, _put_name(str(rec.get("target", "")))
            ):
                probe.add(i)
    return probe


def run_episode(
    scenario: str,
    seed: int,
    *,
    workdir: Path,
    backend: str = "process-local",
) -> LiveEpisode:
    """Execute one genuine episode end to end and return it with hashed evidence + sealed truth."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    evidence_dir = workdir / scenario / f"seed-{seed}"
    if evidence_dir.exists():
        for p in sorted(evidence_dir.glob("*")):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)  # e.g. a prior webroot/ with quarantine
            else:
                p.unlink()
    rng = Rng("live", scenario, str(seed))
    plan = SCENARIOS[scenario](rng)

    fs_root = (evidence_dir / "webroot") if scenario == "fs_change" else None
    lab = LiveLab(evidence_dir, backend=backend, fs_root=fs_root)
    started = datetime.now(UTC)
    lab.start()
    sent = lab.send(plan)
    rc = lab.stop()
    reset_ok = lab.confirm_reset()
    ended = datetime.now(UTC)

    raw_lines = lab.read_log_lines()
    parsed: list[dict[str, Any]] = []
    for ln in raw_lines:
        try:
            parsed.append(json.loads(ln))
        except json.JSONDecodeError:
            parsed.append({})
    probe_idx = _derive_truth(scenario, parsed, fs_root)

    # Capture the REAL resulting filesystem state (for fs_change) as hashed evidence.
    fs_state: list[dict[str, Any]] = []
    if fs_root is not None and fs_root.is_dir():
        for f in sorted(fs_root.glob("*")):
            if f.is_file():
                b = f.read_bytes()
                fs_state.append(
                    {
                        "name": f.name,
                        "sha256": _sha256_bytes(b),
                        "size_bytes": len(b),
                        "is_script": f.name.lower().endswith(_SCRIPT_EXTS),
                    }
                )

    # Independent consistency cross-check: the server-derived probe TARGETS must equal the targets
    # the scenario generated with intent "probe" (two routes agreeing), else flag it.
    sent_probe_targets = {r["target"] for r in plan if r["intent"] == "probe"}
    derived_probe_targets = {str(parsed[i].get("target", "")) for i in probe_idx}
    cross_ok = derived_probe_targets == sent_probe_targets
    cross_detail = (
        f"server-derived {len(derived_probe_targets)} probe targets == {len(sent_probe_targets)} generated"
        if cross_ok
        else f"MISMATCH derived={sorted(derived_probe_targets)} generated={sorted(sent_probe_targets)}"
    )

    log_bytes = lab.access_log.read_bytes() if lab.access_log.exists() else b""
    log_sha = _sha256_bytes(log_bytes)

    # Store a hashed, timestamped evidence manifest alongside the raw log.
    evidence_files = [
        EvidenceFile(
            path=str(lab.access_log), kind="access_log", sha256=log_sha, size_bytes=len(log_bytes)
        )
    ]
    if fs_root is not None:
        fs_state_bytes = (json.dumps(fs_state, indent=2) + "\n").encode()
        fs_state_path = evidence_dir / "fs_state.json"
        fs_state_path.write_bytes(fs_state_bytes)
        evidence_files.append(
            EvidenceFile(
                path=str(fs_state_path),
                kind="fs_state",
                sha256=_sha256_bytes(fs_state_bytes),
                size_bytes=len(fs_state_bytes),
            )
        )
    manifest = {
        "scenario": scenario,
        "seed": seed,
        "collected_at": ended.isoformat(),
        "files": [f.model_dump() for f in evidence_files],
    }
    man_path = evidence_dir / "manifest.json"
    man_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    man_path.write_bytes(man_bytes)
    evidence_files.append(
        EvidenceFile(
            path=str(man_path),
            kind="manifest",
            sha256=_sha256_bytes(man_bytes),
            size_bytes=len(man_bytes),
        )
    )

    return LiveEpisode(
        scenario=scenario,
        seed=seed,
        backend=backend,
        host_os=platform.platform(),
        started_at=started,
        ended_at=ended,
        service={
            "pid": lab._proc.pid if lab._proc else None,
            "port": lab.port,
            "returncode": rc,
            "executable": sys.executable,
        },
        network={"endpoint": f"127.0.0.1:{lab.port}", "requests_sent": sent, "loopback_only": True},
        access_log_lines=raw_lines,
        access_log_sha256=log_sha,
        evidence_ids=[f"line-{i}" for i in range(len(raw_lines))],
        gold_truth={
            "malicious_line_ids": sorted(f"line-{i}" for i in probe_idx),
            "m": len(probe_idx),
        },
        control_plane_intent={"generated_probe_targets": sorted(sent_probe_targets)},
        cross_check_ok=cross_ok,
        cross_check_detail=cross_detail,
        lab_state={"reset_ok": reset_ok, "service_returncode": rc, "fs_state": fs_state},
        evidence_dir=str(evidence_dir),
        evidence_files=evidence_files,
    )
