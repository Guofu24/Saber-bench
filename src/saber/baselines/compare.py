"""Controlled four-way baseline comparison on the same gold episodes (Phase E2).

Baselines, all graded on identical episodes:

* ``oracle`` — answer from gold (upper bound),
* ``naive`` — weak rules floor (:mod:`saber.baselines.rules`),
* ``strong`` — competent conventional non-LLM detection (:mod:`saber.baselines.strong`),
* ``single`` / ``specialist`` / ``multi_agent`` — LLM modes (:mod:`saber.baselines.agents`).

Reports per-pilot score, false-positive/false-negative counts (where the scorer exposes them),
evidence grounding, completion, latency, tool failures, resource consumption (LLM calls, list-price
cost), and cluster-bootstrap CIs over pilots. Measurement only; nothing is READY_BENCHMARK.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.baselines.agents import run_mode
from saber.baselines.pilot_runner import (
    _agg_clustered,
    _by_cluster,
    _false_negative_count,
    _false_positive_count,
    _mean,
    _pctl,
    _raw_components,
    _safe_grade,
    _sanitize_components,
    evidence_grounding,
)
from saber.baselines.rules import naive_answer
from saber.baselines.strong import strong_answer
from saber.catalog.loader import default_catalog, repo_root
from saber.gold.base import Split, load_pilot, pilot_ids

DETERMINISTIC = ("oracle", "naive", "strong")
LLM_MODES = ("single", "specialist", "multi_agent")
LABELS = ["GOLD_PILOT_V1", "STRONG_BASELINE_COMPARISON", "DEV_SIMULATION_ONLY"]


def _grade_summary(
    pilot: Any, episode: Any, answer: dict[str, Any] | None, agent_id: str
) -> dict[str, Any]:
    if answer is None:
        return {
            "score": 0.0,
            "false_positives": None,
            "false_negatives": None,
            "components": [],
            "grounding": None,
        }
    res, err = _safe_grade(pilot, episode, answer, agent_id)
    raw = _raw_components(res)
    return {
        "score": round(res.score, 4) if res else 0.0,
        "error": err,
        "false_positives": _false_positive_count(raw),
        "false_negatives": _false_negative_count(raw),
        "components": _sanitize_components(raw),
        "grounding": evidence_grounding(episode, answer),
    }


def run_episode(
    subtask_id: str,
    split: Split,
    seed: int,
    *,
    model: str,
    llm_modes: tuple[str, ...],
    timeout_s: float,
) -> dict[str, Any]:
    pilot = load_pilot(subtask_id)
    ep = pilot.build(split, seed)
    results: dict[str, dict[str, Any]] = {
        "oracle": _grade_summary(pilot, ep, pilot.answer_from_gold(ep), "oracle"),
        "naive": _grade_summary(pilot, ep, naive_answer(subtask_id, ep), "naive"),
        "strong": _grade_summary(pilot, ep, strong_answer(subtask_id, ep), "strong"),
    }
    for mode in llm_modes:
        run = run_mode(mode, pilot, ep, model=model, timeout_s=timeout_s)
        summ = _grade_summary(pilot, ep, run["answer"], f"llm_{mode}")
        summ.update(
            {
                "completed": run["completed"],
                "n_calls": run["n_calls"],
                "wall_ms": run["wall_ms"],
                "duration_ms": run["duration_ms"],
                "tool_failures": run["tool_failures"],
                "model_used": run["model_used"],
                "provider": run["provider"],
                "cost_usd_listprice": run["cost_usd_listprice"],
                "parse_note": run["parse_note"],
            }
        )
        if not run["completed"]:
            summ["score"] = 0.0
        results[mode] = summ
    return {
        "subtask_id": subtask_id,
        "service": default_catalog().subtask(subtask_id).service,
        "seed": seed,
        "episode_id": str(ep.episode_id),
        "results": results,
    }


def _agg_baseline(episodes: list[dict[str, Any]], baseline: str, is_llm: bool) -> dict[str, Any]:
    by = _by_cluster(episodes, lambda e: e["results"][baseline]["score"])
    agg = _agg_clustered(by)
    fps = [e["results"][baseline].get("false_positives") for e in episodes]
    fns = [e["results"][baseline].get("false_negatives") for e in episodes]
    out: dict[str, Any] = {
        "score": agg,
        "fp_total": sum(x for x in fps if isinstance(x, int)),
        "fn_total": sum(x for x in fns if isinstance(x, int)),
    }
    if is_llm:
        entries = [e["results"][baseline] for e in episodes]
        completed = [x for x in entries if x.get("completed")]
        lat = [x["duration_ms"] for x in completed if isinstance(x.get("duration_ms"), int)]
        # Separate capability (completed-only) from reliability (all, incompletes scored 0) so the
        # blended `score` is not read as pure capability.
        by_completed = _by_cluster(
            [e for e in episodes if e["results"][baseline].get("completed")],
            lambda e: e["results"][baseline]["score"],
        )
        out.update(
            {
                "score_completed": _agg_clustered(by_completed),
                "completion_rate": round(len(completed) / len(entries), 4) if entries else None,
                "n_calls_total": sum(x.get("n_calls", 0) for x in entries),
                "tool_failures_total": sum(x.get("tool_failures", 0) for x in entries),
                "latency_mean_ms": int(sum(lat) / len(lat)) if lat else None,
                "latency_p95_ms": _pctl(lat, 0.95),
                "cost_listprice": round(
                    sum(x.get("cost_usd_listprice") or 0.0 for x in entries), 4
                ),
                "models": sorted({x["model_used"] for x in entries if x.get("model_used")}),
            }
        )
    return out


def run_comparison(
    subtask_ids: list[str] | None = None,
    *,
    split: Split = "dev",
    seeds: list[int] | None = None,
    model: str = "haiku",
    llm_modes: tuple[str, ...] = LLM_MODES,
    use_llm: bool = True,
    timeout_s: float = 150.0,
) -> dict[str, Any]:
    ids = subtask_ids or pilot_ids()
    seed_list = seeds or [1]
    modes = llm_modes if use_llm else ()
    episodes = [
        run_episode(sid, split, s, model=model, llm_modes=modes, timeout_s=timeout_s)
        for sid in ids
        for s in seed_list
    ]
    baselines = list(DETERMINISTIC) + list(modes)
    summary = {b: _agg_baseline(episodes, b, is_llm=(b in modes)) for b in baselines}
    per_pilot = [
        {
            "subtask_id": sid,
            "service": default_catalog().subtask(sid).service,
            **{
                b: _mean([e["results"][b]["score"] for e in episodes if e["subtask_id"] == sid])
                for b in baselines
            },
        }
        for sid in ids
    ]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "labels": LABELS,
        "auth": "claude.ai subscription CLI (API-key env scrubbed); cost is LIST price, informational",
        "model_requested": model,
        "split": split,
        "seeds": seed_list,
        "baselines": baselines,
        "episodes": episodes,
        "summary": summary,
        "per_pilot": per_pilot,
        "caveat": "Controlled discrimination comparison on SYNTHETIC gold episodes; NOT an externally "
        "validated benchmark and NOT READY_BENCHMARK.",
    }


def write_comparison(report: dict[str, Any], out_dir: Path | None = None) -> tuple[Path, Path]:
    if report["split"] == "hidden":
        raise ValueError("refusing to write a hidden-split comparison report (sealed split)")
    base = out_dir or (repo_root() / "gold" / "baselines")
    base.mkdir(parents=True, exist_ok=True)
    seeds = "-".join(str(s) for s in report["seeds"])
    tag = f"compare_{report['model_requested']}_{report['split']}_seeds{seeds}"
    jpath = base / f"{tag}.json"
    jpath.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mpath = base / f"{tag}.md"
    mpath.write_text(_markdown(report), encoding="utf-8")
    return jpath, mpath


def _ci(agg: dict[str, Any]) -> str:
    c = agg["score"].get("ci95_cluster")
    return f"{agg['score']['mean']}{f' CI95{c}' if c else ''}"


def _completed_str(agg: dict[str, Any]) -> str:
    sc = agg.get("score_completed")
    if not sc:
        return "—"
    c = sc.get("ci95_cluster")
    return f"{sc.get('mean')}{f' CI95{c}' if c else ''}"


def _markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# Strong-baseline comparison — {report['model_requested']} / {report['split']} / seeds {report['seeds']}",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Auth: {report['auth']}",
        f"- Labels: {', '.join(report['labels'])}",
        f"- {report['caveat']}",
        "",
        "## Score by baseline (cluster-bootstrap 95% CI over pilots)",
        "",
        "Score = all episodes (LLM incompletes scored 0, mixes capability + reliability); "
        "Score(completed) = capability on completed episodes only. FP/FN totals are only where the "
        "scorer exposes them (accuracy/enum/order-less pilots show blank), so are not comparable "
        "across all pilots. The `strong` arm is a conventional CEILING — see strong.py docstring.",
        "",
        "| Baseline | Score | Score(completed) | FP total | FN total | Completion | LLM calls | Tool fails | Latency mean/p95 ms | Cost$ |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for b in report["baselines"]:
        a = s[b]
        lines.append(
            f"| {b} | {_ci(a)} | {_completed_str(a)} | {a.get('fp_total')} | {a.get('fn_total')} | "
            f"{a.get('completion_rate', '—')} | {a.get('n_calls_total', '—')} | "
            f"{a.get('tool_failures_total', '—')} | "
            f"{a.get('latency_mean_ms', '—')}/{a.get('latency_p95_ms', '—')} | {a.get('cost_listprice', '—')} |"
        )
    lines += [
        "",
        "## Per-pilot score (mean over seeds)",
        "",
        "| Subtask | Svc | " + " | ".join(report["baselines"]) + " |",
        "|---|---|" + "---|" * len(report["baselines"]),
    ]
    for row in report["per_pilot"]:
        cells = " | ".join(str(row[b]) for b in report["baselines"])
        lines.append(f"| {row['subtask_id']} | {row['service']} | {cells} |")
    return "\n".join(lines) + "\n"
