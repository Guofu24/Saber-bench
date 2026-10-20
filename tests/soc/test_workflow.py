"""Tests for the Phase G four-service SOC case workflow."""

from __future__ import annotations

import json
from pathlib import Path

from saber.range.live import run_episode
from saber.soc import run_case_workflow, run_soc_suite
from saber.soc.detectors import conventional_detector, naive_detector
from saber.soc.suite import write_soc_suite


def test_workflow_end_to_end_web(tmp_path: Path) -> None:
    ep = run_episode("web_sqli_probe", 1, workdir=tmp_path)
    heldout = run_episode("web_sqli_probe", 1001, workdir=tmp_path)
    case = run_case_workflow(
        ep,
        heldout,
        conventional_detector,
        episode_truth=set(ep.gold_truth["malicious_line_ids"]),
        heldout_truth=set(heldout.gold_truth["malicious_line_ids"]),
    )
    assert case.monitoring["subtask"] == "T1347.001"
    assert case.monitoring["evidence_refs_valid"] is True
    assert case.monitoring["score"] == 1.0  # conventional detector solves the bound contract
    assert case.content_security["subtask"] == "T0020.001"
    assert "heldout_precision" in case.content_security
    assert case.hunting["proactive"] is False
    # IR for web = proposed only (no reversible lab action), honest
    assert case.response["eligible"] is True and not case.response.get("actions")


def test_workflow_ir_executes_and_verifies_on_fs(tmp_path: Path) -> None:
    ep = run_episode("fs_change", 2, workdir=tmp_path)
    heldout = run_episode("fs_change", 1002, workdir=tmp_path)
    case = run_case_workflow(
        ep,
        heldout,
        conventional_detector,
        episode_truth=set(ep.gold_truth["malicious_line_ids"]),
        heldout_truth=set(heldout.gold_truth["malicious_line_ids"]),
    )
    assert case.response["eligible"] is True
    assert case.response["actions"], "fs_change IR should execute a reversible quarantine"
    assert case.response["verified"] is True
    assert case.response["collateral"] == []
    assert any(
        a["action"] == "quarantine_webroot_file" and a["verified"] for a in case.response["actions"]
    )


def test_no_service_reads_truth() -> None:
    # The detectors must not reference gold_truth (they take only the episode's public evidence).
    import inspect

    for fn in (conventional_detector, naive_detector):
        src = inspect.getsource(fn)
        assert "gold_truth" not in src


def test_g3_offline_conventional_and_ablation_shape(tmp_path: Path) -> None:
    from saber.soc import run_g3_evaluation
    from saber.soc.evaluation import _ablation

    r = run_g3_evaluation(seeds=[1, 2], use_llm=False, workdir=tmp_path)
    assert r["configs"] == ["conventional"]
    assert r["summary"]["conventional"]["score_mean"] == 1.0
    assert r["subtask"] == "T1347.001"
    assert "significance" in r["caveat"].lower()
    # ablation paired-delta logic (synthetic): multi_agent beats budget_single on both seeds
    pc = {
        "multi_agent": [{"seed": 1, "score": 1.0}, {"seed": 2, "score": 1.0}],
        "budget_single": [{"seed": 1, "score": 0.8}, {"seed": 2, "score": 0.6}],
        "multi_no_reviewer": [{"seed": 1, "score": 0.9}, {"seed": 2, "score": 0.9}],
        "single": [{"seed": 1, "score": 0.8}, {"seed": 2, "score": 0.6}],
    }
    ab = _ablation(pc)
    assert ab["multi_agent_vs_budget_single"]["mean_delta"] == 0.3
    assert ab["multi_agent_vs_multi_no_reviewer"]["mean_delta"] == 0.1


def test_suite_coverage_and_sanitized_receipt(tmp_path: Path) -> None:
    report = run_soc_suite(
        ["web_sqli_probe", "fs_change"], [1], detector="conventional", workdir=tmp_path
    )
    matrix = report["coverage_matrix"]
    assert {r["scenario"] for r in matrix} == {"web_sqli_probe", "fs_change"}
    fs_row = next(r for r in matrix if r["scenario"] == "fs_change")
    assert fs_row["ir_executed"] and fs_row["ir_verified"]
    # written report must not publish the detection answer key
    path = write_soc_suite(report, tmp_path / "out")
    text = path.read_text(encoding="utf-8")
    obj = json.loads(text)
    for c in obj["cases"]:
        assert "cited_evidence" not in c["case"]["monitoring"]
        assert "timeline" not in c["case"]["hunting"]
