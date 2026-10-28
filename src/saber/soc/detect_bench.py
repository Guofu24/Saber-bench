"""Track A — detection benchmark: blue detectors over families x seeds x client noise.

This is the end-to-end realization of the three populations as a SCORED benchmark:

* the *attacker* population is the allowlisted scenario families (each with a server-side-derived,
  agent-independent label);
* the *client* population overlays benign background traffic (``noise_clients``), so false positives
  are measured against genuine benign activity, not an empty background;
* the *blue* population is the detectors under test (a precise conventional rule vs a naive floor).

For each episode we compute TP/FP/FN/TN against the sealed control-plane truth, then aggregate per
detector with cluster-bootstrap 95% CIs (the cluster is the scenario family, since seeds within a
family are correlated). Everything is deterministic and non-LLM. No detector reads the sealed truth;
it is passed only to the scoring here. Nothing is READY_BENCHMARK: this is automated-lab ground
truth (``AUTOMATED_LAB_GROUND_TRUTH`` / ``DEV_SIMULATION_ONLY``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.baselines.pilot_runner import _agg_clustered
from saber.catalog.loader import repo_root
from saber.range.live import run_episode
from saber.range.live.attack_registry import ALLOWLIST, allowlist_covers_scenarios
from saber.range.live.episode import LiveEpisode
from saber.soc.detectors import conventional_detector, naive_detector

Detector = Callable[[LiveEpisode], dict[str, Any]]

_DETECTORS: dict[str, Detector] = {
    "conventional": conventional_detector,
    "naive": naive_detector,
}


def _score_episode(ep: LiveEpisode, detector: Detector) -> dict[str, Any]:
    """TP/FP/FN/TN + recall/precision for one detector on one episode (truth used only here)."""
    truth = {str(x) for x in ep.gold_truth["malicious_line_ids"]}
    matched = {str(x) for x in detector(ep).get("matched_line_ids", [])}
    total = len(ep.access_log_lines)
    tp = len(matched & truth)
    fp = len(matched - truth)
    fn = len(truth - matched)
    tn = total - len(matched | truth)
    recall = tp / (tp + fn) if (tp + fn) else None
    precision = tp / (tp + fp) if (tp + fp) else None  # None when the detector raised no alarm
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "recall": recall,
        "precision": precision,
        "benign_lines": total - len(truth),
    }


def run_detection_bench(
    *,
    families: list[str] | None = None,
    seeds: list[int] | None = None,
    noise_clients: int = 3,
    detectors: list[str] | None = None,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Run each detector over families x seeds (with client noise) and aggregate with clustered CIs."""
    fams = families or list(ALLOWLIST)
    sds = seeds or [1, 2, 3]
    dets = detectors or list(_DETECTORS)
    wd = workdir or (repo_root() / "runs" / "detect_bench")

    # Run each episode ONCE; score every detector on it (same telemetry, fair comparison).
    episodes: list[dict[str, Any]] = []
    for family in fams:
        for seed in sds:
            ep = run_episode(family, seed, workdir=wd, noise_clients=noise_clients)
            row: dict[str, Any] = {
                "family": family,
                "seed": seed,
                "cross_check_ok": ep.cross_check_ok,
                "reset_ok": ep.lab_state["reset_ok"],
                "lines": len(ep.access_log_lines),
                "noise": ep.network.get("client_noise_requests", 0),
                "malicious": ep.gold_truth["m"],
                "scores": {d: _score_episode(ep, _DETECTORS[d]) for d in dets},
            }
            episodes.append(row)

    # Aggregate per detector, clustering by family for the CI (seeds within a family are correlated).
    summary: dict[str, Any] = {}
    for d in dets:
        by_recall: dict[str, list[float]] = {}
        by_prec: dict[str, list[float]] = {}
        fp_total = fn_total = 0
        episodes_with_fp = 0
        for e in episodes:
            s = e["scores"][d]
            if s["recall"] is not None:
                by_recall.setdefault(e["family"], []).append(float(s["recall"]))
            if s["precision"] is not None:
                by_prec.setdefault(e["family"], []).append(float(s["precision"]))
            fp_total += s["fp"]
            fn_total += s["fn"]
            episodes_with_fp += 1 if s["fp"] > 0 else 0
        summary[d] = {
            "recall": _agg_clustered(by_recall),
            "precision": _agg_clustered(by_prec),
            "fp_total": fp_total,
            "fn_total": fn_total,
            "episodes_with_fp": episodes_with_fp,
            "n_episodes": len(episodes),
        }

    # Per-family breakdown (mean recall/precision per detector).
    per_family: dict[str, Any] = {}
    for family in fams:
        fam_eps = [e for e in episodes if e["family"] == family]
        per_family[family] = {
            d: {
                "recall": _mean([e["scores"][d]["recall"] for e in fam_eps]),
                "precision": _mean([e["scores"][d]["precision"] for e in fam_eps]),
                "fp": sum(e["scores"][d]["fp"] for e in fam_eps),
            }
            for d in dets
        }

    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "track": "A_DETECTION_ONLY",
        "families": fams,
        "seeds": sds,
        "noise_clients": noise_clients,
        "detectors": dets,
        "allowlist_covers_scenarios": allowlist_covers_scenarios(),
        "all_cross_checks_ok": all(e["cross_check_ok"] and e["reset_ok"] for e in episodes),
        "labels": ["LIVE_LAB_EXECUTION", "AUTOMATED_LAB_GROUND_TRUTH", "DEV_SIMULATION_ONLY"],
        "summary": summary,
        "per_family": per_family,
        "caveat": "Genuine live detection benchmark with benign client-noise FP pressure. "
        "Automated-lab ground truth, NOT expert-validated gold; NOT READY_BENCHMARK.",
    }


def _mean(xs: list[Any]) -> float | None:
    vals = [float(x) for x in xs if x is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def write_detection_bench(report: dict[str, Any], out_dir: Path | None = None) -> Path:
    base = out_dir or (repo_root() / "range_evidence" / "soc")
    base.mkdir(parents=True, exist_ok=True)
    seeds = "-".join(str(s) for s in report["seeds"])
    path = base / f"detect_bench_seeds{seeds}_noise{report['noise_clients']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
