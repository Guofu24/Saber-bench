"""G3 — six-configuration multi-agent evaluation on matched live episodes (web_sqli_probe).

Configs on identical episodes: conventional (non-LLM), single, specialist, multi_agent,
budget_single (budget-matched to multi_agent), multi_no_reviewer (budget-matched, no reviewer).
Scored with T1347.001's set_delta contract on the real telemetry. Reports per-config score, FP/FN,
evidence validity, completion, calls, latency, cost, and the call-budget-matched ablation isolating
whether coordination (the reviewer) beats simply spending a second call. Three seeds, one family:
explicitly NOT a significance claim.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.catalog.loader import repo_root
from saber.range.live import run_episode
from saber.soc.detectors import conventional_detector
from saber.soc.llm_detectors import make_detector
from saber.soc.workflow import MON_SUBTASK, _set_delta_score

_LLM_MODES = ("single", "specialist", "multi_agent", "budget_single", "multi_no_reviewer")
# Families where the detection task is a regex-authoring task (so the LLM configs apply). auth is a
# threshold rule, not a regex task, and is excluded from the six-config LLM eval (see note_auth).
_SCENARIOS = ("web_sqli_probe", "fs_change")


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _ci95(xs: list[float]) -> list[float] | None:
    if len(xs) < 2:
        return None
    rng = random.Random(20261020)
    n = len(xs)
    means = sorted(sum(rng.choice(xs) for _ in range(n)) / n for _ in range(2000))
    return [round(means[int(0.025 * 2000)], 4), round(means[int(0.975 * 2000) - 1], 4)]


def _run_family(
    scenario: str, seeds: list[int], configs: dict[str, Any], wd: Path
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    per_config: dict[str, list[dict[str, Any]]] = {c: [] for c in configs}
    models: set[str] = set()
    for seed in seeds:
        ep = run_episode(scenario, seed, workdir=wd)
        truth = set(ep.gold_truth["malicious_line_ids"])
        valid_episode = ep.cross_check_ok and ep.lab_state["reset_ok"]
        for cname, det in configs.items():
            d = det(ep)
            matched = {str(x) for x in d.get("matched_line_ids", [])}
            completed = d.get("completed", True)
            sd = _set_delta_score(matched, truth)
            models.update(c.get("model") for c in d.get("calls", []) if c.get("model"))
            per_config[cname].append(
                {
                    "seed": seed,
                    "episode_valid": valid_episode,
                    "completed": completed,
                    "score": sd["score"] if completed else 0.0,
                    "false_positives": sd["false_positives"],
                    "false_negatives": sd["false_negatives"],
                    "evidence_refs_valid": matched <= set(ep.evidence_ids),
                    "n_calls": d.get("n_calls", 0),
                    "tool_failures": d.get("tool_failures", 0),
                    "duration_ms": sum(c.get("duration_ms") or 0 for c in d.get("calls", []))
                    or None,
                    "wall_ms": d.get("wall_ms", 0),
                    "cost_usd_listprice": d.get("cost_usd_listprice", 0.0),
                }
            )
    return per_config, models


def _summarize(per_config: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    summary = {}
    for cname, rows in per_config.items():
        valid = [r for r in rows if r["episode_valid"]]  # invalidation gating
        done = [r for r in valid if r["completed"]]
        scores = [r["score"] for r in valid]
        summary[cname] = {
            "score_mean": _mean(scores),
            "score_ci95": _ci95(scores),
            "score_completed_mean": _mean([r["score"] for r in done]),
            "completion_rate": round(len(done) / len(valid), 4) if valid else None,
            "fp_total": sum(r["false_positives"] for r in valid),
            "fn_total": sum(r["false_negatives"] for r in valid),
            "evidence_valid_all": all(r["evidence_refs_valid"] for r in valid),
            "n_calls_total": sum(r["n_calls"] for r in valid),
            "tool_failures_total": sum(r["tool_failures"] for r in valid),
            "latency_mean_ms": _mean([r["duration_ms"] for r in done if r["duration_ms"]]),
            "cost_listprice": round(sum(r["cost_usd_listprice"] for r in valid), 4),
        }
    return summary


def run_g3_evaluation(
    *,
    seeds: list[int],
    scenarios: list[str] | None = None,
    model: str = "haiku",
    use_llm: bool = True,
    timeout_s: float = 180.0,
    workdir: Path | None = None,
) -> dict[str, Any]:
    wd = workdir or (repo_root() / "runs" / "g3")
    fams = scenarios or list(_SCENARIOS)
    configs: dict[str, Any] = {"conventional": conventional_detector}
    if use_llm:
        for m in _LLM_MODES:
            configs[m] = make_detector(m, model=model, timeout_s=timeout_s)

    families: dict[str, Any] = {}
    models_observed: set[str] = set()
    for scenario in fams:
        per_config, models = _run_family(scenario, seeds, configs, wd)
        models_observed |= models
        families[scenario] = {
            "subtask": MON_SUBTASK,
            "summary": _summarize(per_config),
            "ablation": _ablation(per_config) if use_llm else {},
            "per_config": per_config,
        }

    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "subtask": MON_SUBTASK,
        "source_aggregate": "set_delta max(0, M'/M - N'/(N'+M'))",
        "scenarios": fams,
        "model_requested": model,
        "models_observed": sorted(models_observed),
        "seeds": seeds,
        "labels": ["LIVE_LAB_EXECUTION", "AUTOMATED_LAB_GROUND_TRUTH", "DEV_SIMULATION_ONLY"],
        "configs": list(configs),
        "families": families,
        "note_auth": "auth_bruteforce is a volume/threshold rule, not a regex-authoring task, so the "
        "six LLM configs are not run on it; its conventional baseline is in the SOC coverage matrix.",
        "caveat": (
            f"{len(seeds)} seeds x {len(fams)} scenario families — point estimates with wide "
            "bootstrap CIs, explicitly NOT a statistical-significance claim. All configs run on "
            "identical episodes with equal data access, tool permissions, first-turn context and "
            "measured budgets (n_calls/cost). AUTOMATED_LAB_GROUND_TRUTH, not expert gold; NOT "
            "READY_BENCHMARK."
        ),
    }


def _ablation(per_config: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Call-budget-matched ablation: does the reviewer (coordination) beat spending a 2nd call?"""

    def paired_delta(a: str, b: str) -> dict[str, Any]:
        ra = {r["seed"]: r["score"] for r in per_config.get(a, [])}
        rb = {r["seed"]: r["score"] for r in per_config.get(b, [])}
        common = sorted(set(ra) & set(rb))
        diffs = [ra[s] - rb[s] for s in common]
        return {
            "pairs": len(common),
            "mean_delta": _mean(diffs),
            "per_seed_delta": {s: round(ra[s] - rb[s], 4) for s in common},
        }

    calls = {
        c: _mean([r.get("n_calls", 0) for r in per_config.get(c, [])])
        for c in ("multi_agent", "budget_single", "multi_no_reviewer", "single")
    }
    return {
        "budget_note": f"mean calls: {calls}",
        "multi_agent_vs_budget_single": paired_delta("multi_agent", "budget_single"),
        "multi_agent_vs_multi_no_reviewer": paired_delta("multi_agent", "multi_no_reviewer"),
        "multi_agent_vs_single": paired_delta("multi_agent", "single"),
        "interpretation": (
            "multi_agent, budget_single and multi_no_reviewer all spend 2 calls AND share the same "
            "specialist first-turn prompt, so the comparison isolates the second step: reviewer "
            "(multi_agent) vs self-refine (budget_single) vs a second independent analyst "
            "(multi_no_reviewer). If multi_agent does not beat the other two, coordination adds no "
            "value beyond the extra call. Caveat: multi_no_reviewer OR-ensembles the two regexes, "
            "which biases toward recall and can inflate false positives. Read the per-seed deltas, "
            "not a mean over 3 seeds; this is not a significance claim."
        ),
    }


def write_g3_evaluation(report: dict[str, Any], out_dir: Path | None = None) -> Path:
    base = out_dir or (repo_root() / "range_evidence" / "g3")
    base.mkdir(parents=True, exist_ok=True)
    seeds = "-".join(str(s) for s in report["seeds"])
    path = base / f"g3_eval_{report['model_requested']}_seeds{seeds}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
