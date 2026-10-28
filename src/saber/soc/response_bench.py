"""Track B — response benchmark: detection quality -> containment outcome on real lab state.

Track A scores detection; Track B scores what the blue team actually *does about it*. It runs the
full case workflow on `fs_change` — the one family with a verified, reversible IR action — so the
Incident Response service EXECUTES an approved quarantine and the effect is verified from the real
post-action filesystem. Containment targets come from the detector's confirmed findings, so the
response outcome is driven by detection quality:

* a precise detector contains exactly the webshell, with no benign impact;
* a naive over-flagger still contains the webshell but also quarantines authorized scripts — real,
  measured benign operational impact (false containment), which a detection-only score never shows.

This is the operational point of the benchmark: a high recall that comes with heavy false
containment is not a good outcome. Reversible, allowlisted, operator-approved, lab-only; no real
host is touched. AUTOMATED_LAB_GROUND_TRUTH / DEV_SIMULATION_ONLY; nothing is READY_BENCHMARK.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from saber.catalog.loader import repo_root
from saber.range.live import run_episode
from saber.range.live.episode import LiveEpisode
from saber.soc.detectors import conventional_detector, naive_detector
from saber.soc.workflow import run_case_workflow

Detector = Callable[[LiveEpisode], dict[str, Any]]
_DETECTORS: dict[str, Detector] = {"conventional": conventional_detector, "naive": naive_detector}
_RESPONSE_FAMILY = "fs_change"  # the only family with a verified, reversible IR action
_HELDOUT_OFFSET = 1000


def _webshell_names(ep: LiveEpisode) -> set[str]:
    """The true unauthorized file names, from the sealed truth (used only for scoring)."""
    names: set[str] = set()
    for lid in ep.gold_truth["malicious_line_ids"]:
        try:
            rec = json.loads(ep.access_log_lines[int(str(lid).split("-")[1])])
        except (ValueError, IndexError, json.JSONDecodeError):
            continue
        n = (parse_qs(urlsplit(str(rec.get("target", ""))).query).get("name") or [""])[0]
        if n:
            names.add(Path(n).name)
    return names


def _score_response(ep: LiveEpisode, detector: Detector, heldout: LiveEpisode) -> dict[str, Any]:
    """Run the full case workflow and score the executed containment against the real truth."""
    case = run_case_workflow(
        ep,
        heldout,
        detector,
        episode_truth=set(ep.gold_truth["malicious_line_ids"]),
        heldout_truth=set(heldout.gold_truth["malicious_line_ids"]),
    )
    truth_files = _webshell_names(ep)
    verified_q = {
        str(a.get("target"))
        for a in case.response.get("actions", [])
        if a.get("verified") and a.get("target")
    }
    contained_true = verified_q & truth_files
    false_containment = verified_q - truth_files  # benign files wrongly quarantined
    recall = len(contained_true) / len(truth_files) if truth_files else None
    return {
        "true_webshells": len(truth_files),
        "contained_true": len(contained_true),
        "containment_recall": recall,
        "false_containment": len(false_containment),
        "executed": bool(case.response.get("actions")),
        "all_verified": bool(case.response.get("verified")),
    }


def run_response_bench(
    *,
    seeds: list[int] | None = None,
    detectors: list[str] | None = None,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Run Track B over fs_change x seeds for each detector; aggregate containment vs benign impact."""
    sds = seeds or [1, 2, 3]
    dets = detectors or list(_DETECTORS)
    wd = workdir or (repo_root() / "runs" / "response_bench")

    episodes: list[dict[str, Any]] = []
    for seed in sds:
        # The held-out episode (read-only for Content Security) is shared across detectors for a seed.
        heldout = run_episode(_RESPONSE_FAMILY, seed + _HELDOUT_OFFSET, workdir=wd / "heldout")
        for d in dets:
            # A fresh episode per (seed, detector): IR mutates the webroot, so each run starts clean.
            ep = run_episode(_RESPONSE_FAMILY, seed, workdir=wd / d)
            episodes.append(
                {"seed": seed, "detector": d, **_score_response(ep, _DETECTORS[d], heldout)}
            )

    summary: dict[str, Any] = {}
    for d in dets:
        rows = [e for e in episodes if e["detector"] == d]
        recalls = [e["containment_recall"] for e in rows if e["containment_recall"] is not None]
        summary[d] = {
            "containment_recall_mean": round(sum(recalls) / len(recalls), 4) if recalls else None,
            "false_containment_total": sum(e["false_containment"] for e in rows),
            "episodes_with_false_containment": sum(1 for e in rows if e["false_containment"] > 0),
            "all_verified_rate": round(sum(1 for e in rows if e["all_verified"]) / len(rows), 4)
            if rows
            else None,
            "n_episodes": len(rows),
        }

    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "track": "B_RESPONSE_ENABLED",
        "family": _RESPONSE_FAMILY,
        "seeds": sds,
        "detectors": dets,
        "labels": ["LIVE_LAB_EXECUTION", "AUTOMATED_LAB_GROUND_TRUTH", "DEV_SIMULATION_ONLY"],
        "summary": summary,
        "caveat": "Reversible, operator-approved, lab-only containment verified from real fs state. "
        "Benign impact (false containment) is measured, not hidden. NOT READY_BENCHMARK.",
    }


def write_response_bench(report: dict[str, Any], out_dir: Path | None = None) -> Path:
    base = out_dir or (repo_root() / "range_evidence" / "soc")
    base.mkdir(parents=True, exist_ok=True)
    seeds = "-".join(str(s) for s in report["seeds"])
    path = base / f"response_bench_seeds{seeds}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
