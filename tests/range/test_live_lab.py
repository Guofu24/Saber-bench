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


def test_auth_truth_is_threshold_based_not_every_401(tmp_path: Path) -> None:
    from urllib.parse import parse_qs, urlsplit

    from saber.range.live.scenarios import BRUTEFORCE_THRESHOLD

    ep = run_episode("auth_bruteforce", 6, workdir=tmp_path)
    mal = set(ep.gold_truth["malicious_line_ids"])
    # count 401s per user
    fails: dict[str, int] = {}
    for ln in ep.access_log_lines:
        rec = json.loads(ln)
        if rec["status"] == 401:
            u = (parse_qs(urlsplit(rec["target"]).query).get("user") or [""])[0]
            fails[u] = fails.get(u, 0) + 1
    had_benign_single_401 = False
    for i, ln in enumerate(ep.access_log_lines):
        rec = json.loads(ln)
        u = (parse_qs(urlsplit(rec["target"]).query).get("user") or [""])[0]
        if rec["status"] == 401 and fails[u] >= BRUTEFORCE_THRESHOLD:
            assert f"line-{i}" in mal  # brute-force (above threshold) is malicious
        else:
            assert f"line-{i}" not in mal  # 200s AND a single benign typo 401 are NOT malicious
            if rec["status"] == 401:
                had_benign_single_401 = True
    assert had_benign_single_401  # the benign typo hard negative is present and excluded


def test_range_run_public_receipt_has_no_truth(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from saber.cli.main import cli

    out = str(tmp_path / "evidence")
    res = CliRunner().invoke(
        cli, ["range", "run", "--scenario", "web_sqli_probe", "--seed", "1", "--out", out]
    )
    assert res.exit_code == 0, res.output
    public = next(Path(out).rglob("episode_public.json"))
    text = public.read_text(encoding="utf-8")
    # the uploaded/public receipt must NOT carry the answer key
    assert "malicious_line_ids" not in text
    assert "generated_probe_targets" not in text
    assert "line-" not in text  # no per-line truth
    assert '"malicious_count"' in text  # count only is fine


def test_grade_regex_uses_source_formula(tmp_path: Path) -> None:
    from saber.range.live.bench import grade_regex

    lines = [
        '{"target": "/search?q=1=1"}',  # malicious (line-0)
        '{"target": "/products"}',  # benign
        '{"target": "/search?q=laptop"}',  # benign
    ]
    truth = {"line-0"}
    g = grade_regex(r"1=1", lines, truth, ignore_case=True)
    assert g["parse_ok"] and not g["timed_out"]
    assert g["score"] == 1.0 and g["false_positives"] == 0 and g["false_negatives"] == 0
    assert g["matched_refs"] == ["line-0"] and g["evidence_refs_valid"] is True
    # a benign-word regex over-matches -> false positives drag the source formula down
    bad = grade_regex(r"search", lines, truth, ignore_case=True)
    assert bad["false_positives"] >= 1 and bad["score"] < 1.0


def test_live_benchmark_offline_on_real_telemetry(tmp_path: Path) -> None:
    from saber.range.live import run_live_benchmark

    report = run_live_benchmark(
        seeds=[1, 2], modes=("naive", "strong"), use_llm=False, workdir=tmp_path
    )
    assert report["subtask"] == "T0020.001"
    for ep in report["episodes"]:
        assert ep["scenario_success"] is True  # cross-check + reset held
        assert ep["telemetry"]["log_lines"] > 0
    s = report["summary"]
    assert s["strong"]["score_mean"] == 1.0
    assert s["naive"]["score_mean"] <= s["strong"]["score_mean"]
    assert s["strong"]["evidence_valid_all"] is True


def test_fs_change_scenario_real_state_and_truth(tmp_path: Path) -> None:
    ep = run_episode("fs_change", 1, workdir=tmp_path)
    assert ep.scenario == "fs_change" and ep.cross_check_ok and ep.lab_state["reset_ok"]
    fs_state = ep.lab_state["fs_state"]
    assert fs_state, "real files should exist in the webroot"
    assert any(f["is_script"] for f in fs_state)  # the unauthorized webshell upload landed on disk
    # a real script file on disk exists and is hashed
    webroot = Path(ep.evidence_dir) / "webroot"
    for f in fs_state:
        assert (webroot / f["name"]).is_file()
    assert ep.gold_truth["m"] >= 1  # at least one unauthorized change detected from real state


def test_ir_quarantine_is_approved_reversible_and_verified(tmp_path: Path) -> None:
    from saber.range.live import quarantine_file, restore_file

    ep = run_episode("fs_change", 2, workdir=tmp_path)
    webroot = Path(ep.evidence_dir) / "webroot"
    script = next(f["name"] for f in ep.lab_state["fs_state"] if f["is_script"])

    # deny-by-default: no approval id -> refused, no state change
    refused = quarantine_file(webroot, script, approval_id="")
    assert not refused.executed and (webroot / script).is_file()

    # approved: quarantines, verified from REAL state, no collateral
    res = quarantine_file(webroot, script, approval_id="OPS-APPROVAL-1")
    assert res.executed and res.verified and res.reversible
    assert not (webroot / script).is_file()  # webroot no longer serves it
    assert (webroot / ".quarantine" / script).is_file()
    assert res.collateral == []  # other files untouched

    # reversible: restore puts it back, verified
    back = restore_file(webroot, script, approval_id="OPS-APPROVAL-1")
    assert back.executed and back.verified and (webroot / script).is_file()


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
