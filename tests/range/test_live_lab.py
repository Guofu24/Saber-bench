"""Tests for the Phase F live lab: genuine execution, sealed truth, hashed evidence, clean reset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from saber.range.live import run_episode, scenario_ids, service_main


def test_scenarios_exist() -> None:
    assert set(scenario_ids()) >= {"web_sqli_probe", "auth_bruteforce"}


def test_live_episode_executes_and_resets(tmp_path: Path) -> None:
    ep = run_episode("web_sqli_probe", 3, workdir=tmp_path)
    # genuine execution: a real service bound a loopback port, real requests were logged
    assert ep.service.get("port") and ep.service.get("returncode") is not None
    assert ep.network["loopback_only"] is True and ep.network["requests_sent"] > 0
    assert len(ep.access_log_lines) == ep.network["requests_sent"]
    # each logged line is a real JSON access record
    rec = json.loads(ep.access_log_lines[0])
    assert rec["client"] == "127.0.0.1" and rec["method"] == "GET"
    # clean reset verified (process dead + port closed)
    assert ep.lab_state["reset_ok"] is True
    # control-plane ground truth cross-checks against the generation intent (two routes agree)
    assert ep.cross_check_ok is True
    assert ep.gold_truth["m"] >= 1


def test_ground_truth_sealed_from_public_inputs(tmp_path: Path) -> None:
    ep = run_episode("web_sqli_probe", 4, workdir=tmp_path)
    pub = json.dumps(ep.public_inputs())
    for line_id in ep.gold_truth["malicious_line_ids"]:
        # the agent-visible evidence must not reveal WHICH lines are malicious
        assert f'"{line_id}"' not in pub
    assert "malicious_line_ids" not in pub


def test_evidence_is_hashed_and_timestamped(tmp_path: Path) -> None:
    ep = run_episode("auth_bruteforce", 5, workdir=tmp_path)
    log = Path(ep.evidence_dir) / "access.log"
    assert log.exists()
    assert hashlib.sha256(log.read_bytes()).hexdigest() == ep.access_log_sha256
    kinds = {f.kind for f in ep.evidence_files}
    assert {"access_log", "manifest"} <= kinds
    for f in ep.evidence_files:
        assert len(f.sha256) == 64 and f.size_bytes > 0
    assert ep.started_at <= ep.ended_at


def test_auth_scenario_truth_is_failed_logins(tmp_path: Path) -> None:
    ep = run_episode("auth_bruteforce", 6, workdir=tmp_path)
    mal = set(ep.gold_truth["malicious_line_ids"])
    for i, ln in enumerate(ep.access_log_lines):
        rec = json.loads(ln)
        if rec["status"] == 401:
            assert f"line-{i}" in mal  # every failed login is flagged malicious
        else:
            assert f"line-{i}" not in mal


def test_service_refuses_non_loopback(tmp_path: Path) -> None:
    rc = service_main.main(
        [
            "--host",
            "0.0.0.0",
            "--port",
            "0",
            "--log",
            str(tmp_path / "a.log"),
            "--ready-file",
            str(tmp_path / "r"),
        ]
    )
    assert rc == 2  # binds loopback only; refuses 0.0.0.0
