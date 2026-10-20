"""Run the four-service SOC workflow across scenario families and emit a coverage matrix + receipts."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.catalog.loader import repo_root
from saber.range.live import run_episode
from saber.range.live.episode import LiveEpisode
from saber.soc.detectors import conventional_detector, naive_detector
from saber.soc.workflow import run_case_workflow

_DETECTORS: dict[str, Callable[[LiveEpisode], dict[str, Any]]] = {
    "conventional": conventional_detector,
    "naive": naive_detector,
}
_HELDOUT_OFFSET = 1000  # the held-out episode uses a disjoint seed


def run_soc_suite(
    scenarios: list[str],
    seeds: list[int],
    *,
    detector: str = "conventional",
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Execute the end-to-end workflow on each scenario x seed; return cases + a coverage matrix."""
    detect = _DETECTORS[detector]
    wd = workdir or (repo_root() / "runs" / "soc")
    cases: list[dict[str, Any]] = []
    for scenario in scenarios:
        for seed in seeds:
            ep = run_episode(scenario, seed, workdir=wd)
            heldout = run_episode(scenario, seed + _HELDOUT_OFFSET, workdir=wd)
            case = run_case_workflow(
                ep,
                heldout,
                detect,
                episode_truth=set(ep.gold_truth["malicious_line_ids"]),
                heldout_truth=set(heldout.gold_truth["malicious_line_ids"]),
            )
            cases.append(
                {
                    "case": case.to_dict(),
                    "episode_success": ep.cross_check_ok and ep.lab_state["reset_ok"],
                    "telemetry_sha256": ep.access_log_sha256,
                    "malicious_truth_count": ep.gold_truth["m"],
                }
            )

    # Coverage matrix: one row per (scenario, seed) with the four services' outcomes.
    matrix = []
    for c in cases:
        case = c["case"]
        mon = case["monitoring"]
        cnt = case["content_security"]
        hunt = case["hunting"]
        resp = case["response"]
        matrix.append(
            {
                "scenario": case["scenario"],
                "seed": case["seed"],
                "episode_success": c["episode_success"],
                "monitoring_subtask": mon.get("subtask"),
                "monitoring_score": mon.get("score"),
                "monitoring_fp": mon.get("false_positives"),
                "monitoring_fn": mon.get("false_negatives"),
                "evidence_valid": mon.get("evidence_refs_valid"),
                "hunting_entity_f1": hunt.get("entity_f1_reported"),
                "hunting_proactive": hunt.get("proactive"),
                "content_subtask": cnt.get("subtask"),
                "content_heldout_precision": cnt.get("heldout_precision"),
                "content_heldout_recall": cnt.get("heldout_recall"),
                "ir_eligible": resp.get("eligible"),
                "ir_executed": bool(resp.get("actions")),
                "ir_verified": resp.get("verified"),
                "ir_collateral": resp.get("collateral", []),
            }
        )
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "detector": detector,
        "scenarios": scenarios,
        "seeds": seeds,
        "labels": ["LIVE_LAB_EXECUTION", "AUTOMATED_LAB_GROUND_TRUTH", "DEV_SIMULATION_ONLY"],
        "bound_contracts": {"monitoring": "T1347.001", "content_security": "T0020.001"},
        "unscored_services": {
            "threat_hunting": "timeline + entities artifact (entity F1 reported, not a source-contract score)",
            "incident_response": "verified reversible lab action (fs_change); proposed-only elsewhere — not a source-contract score",
        },
        "coverage_matrix": matrix,
        "cases": cases,
        "caveat": "Genuine live workflow. Monitoring/Content Security scored vs real set_delta "
        "contracts; Hunting/IR are workflow artifacts, NOT claimed as source-contract coverage. "
        "NOT independently validated gold; NOT READY_BENCHMARK.",
    }


def _sanitize_for_publish(report: dict[str, Any]) -> dict[str, Any]:
    """Drop the detection ANSWER KEY (cited line ids, timeline line ids, entities) from the written
    cases — for a perfect detector these equal the control-plane truth. Scores/counts and the IR
    verified-action audit (the point of the workflow) are kept."""
    import hashlib

    out: dict[str, Any] = json.loads(json.dumps(report))
    for c in out.get("cases", []):
        case = c.get("case", {})
        case.get("monitoring", {}).pop("cited_evidence", None)
        hunt = case.get("hunting", {})
        hunt.pop("timeline", None)
        hunt.pop("affected_entities", None)
        # The IR action target is the implicated filename (= the answer for fs_change); hash it so
        # the audit trail is preserved without publishing the malicious filename.
        for act in case.get("response", {}).get("actions", []):
            if act.get("target"):
                act["target"] = "sha256:" + hashlib.sha256(act["target"].encode()).hexdigest()[:12]
        for a in case.get("audit", []):
            if a.get("tool") == "quarantine" and a.get("target"):
                a["target"] = "sha256:" + hashlib.sha256(a["target"].encode()).hexdigest()[:12]
    return out


def write_soc_suite(report: dict[str, Any], out_dir: Path | None = None) -> Path:
    base = out_dir or (repo_root() / "range_evidence" / "soc")
    base.mkdir(parents=True, exist_ok=True)
    seeds = "-".join(str(s) for s in report["seeds"])
    path = base / f"soc_suite_{report['detector']}_seeds{seeds}.json"
    path.write_text(
        json.dumps(_sanitize_for_publish(report), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
