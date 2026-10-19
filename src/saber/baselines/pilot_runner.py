"""Run the rules + LLM baselines over gold pilot episodes and aggregate the metrics.

Measured per episode (Phase C): field-level component scores, false positives (where
the scorer exposes them), evidence/referential validity, latency, tool failures and
completion (did the model return a gradeable JSON answer). Runs over multiple seeds and
reports bootstrap confidence intervals so the discrimination numbers carry uncertainty.

The LLM runs through the subscription CLI in an isolated empty working directory.

Sealing: component ``detail`` dicts emitted by the scorers can contain truth-derived
values (the gold verdict, the missed/matched element sets). Before anything is stored
or written, those are stripped (:func:`_sanitize_components`), and writing a
hidden-split report to disk is refused outright, so a baseline report can never carry
the sealed answers. Nothing here promotes a subtask to READY_BENCHMARK.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.baselines.claude_cli import CliInvocation, run_claude_cli
from saber.baselines.prompt import build_prompt, extract_answer_json
from saber.baselines.rules import naive_answer
from saber.catalog.loader import default_catalog, repo_root
from saber.gold.base import GoldEpisode, GoldPilot, Split, load_pilot, pilot_ids

# DEV_SIMULATION_ONLY per BENCHMARK_PROTOCOL G6: no real telemetry/emulation backs these.
LABELS = ["GOLD_PILOT_V1", "LLM_BASELINE_CLI_SUBSCRIPTION", "DEV_SIMULATION_ONLY"]

# Component-detail keys that carry gold-truth-derived values; stripped before storage.
_TRUTH_DETAIL_KEYS = {
    "truth",
    "missed",
    "matched",
    "expected",
    "gold",
    "gold_set",
    "predicted",
    "pred",
    "extra",
    "spurious",
    "false_positive_items",
}

# Short verdict/enum labels are answers, not evidence references, so grounding skips them.
_VERDICT_LABELS = {
    "tp",
    "fp",
    "legit",
    "attack",
    "malicious",
    "benign",
    "rule_logic",
    "data_quality",
    "environment_change",
    "run_key",
    "service",
    "scheduled_task",
    "wmi",
    "startup",
    "systemd",
    "regex",
    "text",
    "hex",
    "true",
    "false",
}
_ENTITY_RE = re.compile(
    r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ipv4
    r"|([\\/])"  # path separators
    r"|(\.[a-z]{2,})"  # domain / file extension
    r"|([0-9a-f]{32,})"  # hash
    r"|(cve-\d{4}-\d+)"  # cve
    r"|(^(?:evt|act|line|entry|sample|alert)-)"  # synthetic ids
)

_DEFANG = (("[.]", "."), ("(.)", "."), ("[dot]", "."), ("[@]", "@"), ("[:]", ":"), ("hxxp", "http"))


def _refang(text: str) -> str:
    out = text.lower()
    for a, b in _DEFANG:
        out = out.replace(a, b)
    return out


def _answer_tokens(obj: Any) -> list[str]:
    """Flatten a submission into candidate reference strings (dict keys + string leaves)."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_answer_tokens(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_answer_tokens(v))
    elif isinstance(obj, str):
        out.append(obj)
    return out


def evidence_grounding(episode: GoldEpisode, answer: dict[str, Any]) -> dict[str, Any]:
    """Fraction of entity-like answer tokens that actually appear in the public artifact.

    A COARSE, directional proxy for 'did the answer stay grounded in the evidence', not a
    precise hallucination rate: it only inspects string tokens that look like references
    (ids, hosts, paths, IOCs, hashes, CVEs), is inert when an answer has no such tokens,
    and a correctly transformed value that is not a verbatim substring (e.g. a recomputed
    UTC timestamp) can be counted against grounding. Verdict/enum labels are excluded.
    """
    # Corpus from raw string leaves (not json.dumps) so backslash-heavy registry paths are
    # not mangled by JSON escaping, which would fake hallucinations.
    public_text = _refang("\n".join(_answer_tokens(episode.public_inputs)))
    checked = 0
    grounded = 0
    hallucinated: list[str] = []
    for tok in _answer_tokens(answer):
        low = _refang(tok.strip())
        if not low or low in _VERDICT_LABELS or len(low) < 4:
            continue
        is_entity = bool(_ENTITY_RE.search(low)) or (
            " " not in low and len(low) >= 5 and any(c.isdigit() for c in low)
        )
        if not is_entity:
            continue
        checked += 1
        if low in public_text:
            grounded += 1
        elif len(hallucinated) < 10:
            hallucinated.append(tok.strip())
    fraction = (grounded / checked) if checked else None
    return {
        "checked": checked,
        "grounded": grounded,
        "fraction": fraction,
        "hallucinated": hallucinated,
        "proxy": "coarse: substring grounding of entity-like tokens; inert when none present",
    }


# A scorer may expose a count as an int OR the elements as a list (never both should be summed).
# Keys are ordered so the canonical int is preferred; each component contributes AT MOST ONE value.
_FP_KEYS = ("fp", "false_positives", "extra", "spurious")
_FN_KEYS = ("fn", "false_negatives", "missed", "missing")


def _count_one(detail: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    """First present key's value as a count (int as-is, list as len); None if no key present."""
    for key in keys:
        v = detail.get(key)
        if isinstance(v, bool):  # guard: bool is an int subclass
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, (list, tuple)):
            return len(v)
    return None


def _tally(components: list[dict[str, Any]], keys: tuple[str, ...]) -> int | None:
    total: int | None = None
    for comp in components:
        detail = comp.get("detail") or {}
        if not isinstance(detail, dict):
            continue
        c = _count_one(detail, keys)
        if c is not None:
            total = (total or 0) + c
    return total


def _false_positive_count(components: list[dict[str, Any]]) -> int | None:
    """False positives from RAW component detail (one value per component; None if not exposed)."""
    return _tally(components, _FP_KEYS)


def _false_negative_count(components: list[dict[str, Any]]) -> int | None:
    """False negatives from RAW component detail (one value per component; None if not exposed)."""
    return _tally(components, _FN_KEYS)


def _sanitize_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip truth-derived values from component detail so reports carry no gold answers."""
    clean: list[dict[str, Any]] = []
    for comp in components:
        detail = comp.get("detail")
        if isinstance(detail, dict):
            safe = {
                k: v
                for k, v in detail.items()
                if k not in _TRUTH_DETAIL_KEYS and isinstance(v, (int, float, bool, str))
            }
        else:
            safe = {}
        clean.append(
            {
                "field": comp.get("field"),
                "score": comp.get("score"),
                "weight": comp.get("weight"),
                "detail": safe,
            }
        )
    return clean


def _safe_grade(pilot: GoldPilot, episode: GoldEpisode, answer: dict[str, Any], agent_id: str):  # type: ignore[no-untyped-def]
    try:
        return pilot.grade(episode, answer, agent_id=agent_id), None
    except Exception as exc:  # noqa: BLE001 - grading must never crash the run
        return None, f"{type(exc).__name__}: {exc}"


def _raw_components(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    return [c.model_dump() for c in result.components]


def _graded(
    pilot: GoldPilot, episode: GoldEpisode, answer: dict[str, Any], agent_id: str
) -> dict[str, Any]:
    """Grade an answer and return a sanitized, report-safe summary (score + fp + components)."""
    res, err = _safe_grade(pilot, episode, answer, agent_id)
    raw = _raw_components(res)
    return {
        "score": round(res.score, 4) if res else 0.0,
        "error": err,
        "false_positives": _false_positive_count(raw),
        "components": _sanitize_components(raw),
        "grounding": evidence_grounding(episode, answer),
    }


def _service_of(subtask_id: str) -> str:
    return default_catalog().subtask(subtask_id).service


def run_episode(
    subtask_id: str,
    split: Split,
    seed: int,
    *,
    model: str,
    use_llm: bool,
    timeout_s: float,
) -> dict[str, Any]:
    pilot = load_pilot(subtask_id)
    episode = pilot.build(split, seed)

    oracle_res, _ = _safe_grade(pilot, episode, pilot.answer_from_gold(episode), "oracle")
    oracle_score = round(oracle_res.score, 4) if oracle_res else 0.0

    naive = naive_answer(subtask_id, episode)
    out: dict[str, Any] = {
        "subtask_id": subtask_id,
        "service": _service_of(subtask_id),
        "split": split,
        "seed": seed,
        "episode_id": str(episode.episode_id),
        "oracle_score": oracle_score,
        "rules": _graded(pilot, episode, naive, "rules_baseline"),
    }

    if use_llm:
        prompt = build_prompt(pilot, episode)
        tmp = tempfile.mkdtemp(prefix="saber-llm-")
        t0 = time.monotonic()
        try:
            inv = run_claude_cli(prompt, model=model, cwd=tmp, timeout_s=timeout_s)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        wall_ms = int((time.monotonic() - t0) * 1000)
        out["llm"] = _summarize_llm(pilot, episode, inv, wall_ms)
    return out


def _summarize_llm(
    pilot: GoldPilot, episode: GoldEpisode, inv: CliInvocation, wall_ms: int
) -> dict[str, Any]:
    answer, parse_note = (None, inv.error_detail or "no output")
    if inv.ok:
        answer, parse_note = extract_answer_json(inv.result_text)
    completed = answer is not None and inv.ok and not inv.timed_out and not inv.is_error
    llm: dict[str, Any] = {
        "requested_model": inv.requested_model,
        "model_used": inv.model_used,
        "provider": inv.provider,
        "cost_basis": inv.cost_basis,
        "completed": completed,
        "parse_note": parse_note,
        "is_error": inv.is_error,
        "timed_out": inv.timed_out,
        "tool_failures": inv.tool_failures(),
        "permission_denials": inv.permission_denials,
        "duration_ms": inv.duration_ms,
        "wall_ms": wall_ms,
        "num_turns": inv.num_turns,
        "cost_usd_listprice": inv.total_cost_usd,
        "returncode": inv.returncode,
        "error_detail": inv.error_detail,
    }
    if answer is not None:
        graded = _graded(pilot, episode, answer, "llm_cli_baseline")
        graded["answer_keys"] = sorted(answer.keys())
        llm.update(graded)
    else:
        llm.update({"score": 0.0, "components": [], "grounding": None})
    return llm


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _cluster_bootstrap_ci(
    by_cluster: dict[str, list[float]], iters: int = 2000, alpha: float = 0.05
) -> list[float] | None:
    """Percentile CI resampling CLUSTERS (pilots) with replacement, not individual episodes.

    The seeds within a pilot are correlated (same templates), so an i.i.d. episode bootstrap would
    understate uncertainty. This resamples whole pilots, pooling their episodes, then takes the
    mean — the appropriate block bootstrap for a few pilots × a few seeds.
    """
    clusters = [c for c in by_cluster.values() if c]
    if len(clusters) < 2:
        return None
    rng = random.Random(20261019)
    k = len(clusters)
    means: list[float] = []
    for _ in range(iters):
        pooled: list[float] = []
        for _ in range(k):
            pooled.extend(rng.choice(clusters))
        if pooled:
            means.append(sum(pooled) / len(pooled))
    means.sort()
    return [
        round(means[int((alpha / 2) * iters)], 4),
        round(means[int((1 - alpha / 2) * iters) - 1], 4),
    ]


def _agg_clustered(by_cluster: dict[str, list[float]]) -> dict[str, Any]:
    flat = [v for c in by_cluster.values() for v in c]
    return {
        "mean": _mean(flat),
        "n_episodes": len(flat),
        "n_clusters": len([c for c in by_cluster.values() if c]),
        "ci95_cluster": _cluster_bootstrap_ci(by_cluster),
    }


def _pctl(xs: list[int], q: float) -> int | None:
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def _by_cluster(episodes: list[dict[str, Any]], val: Any) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for e in episodes:
        v = val(e)
        if v is not None:
            out.setdefault(e["subtask_id"], []).append(v)
    return out


def _by_seed(
    episodes: list[dict[str, Any]], seeds: list[int], use_llm: bool
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for s in seeds:
        es = [e for e in episodes if e["seed"] == s]
        row: dict[str, Any] = {
            "seed": s,
            "oracle_mean": _mean([e["oracle_score"] for e in es]),
            "rules_mean": _mean([e["rules"]["score"] for e in es]),
        }
        if use_llm:
            comp = [e["llm"] for e in es if "llm" in e and e["llm"].get("completed")]
            row["llm_mean_completed"] = _mean([x["score"] for x in comp])
            row["llm_completion"] = (
                round(sum(1 for e in es if "llm" in e and e["llm"].get("completed")) / len(es), 4)
                if es
                else None
            )
        rows.append(row)
    return rows


def summarize_episodes(
    episodes: list[dict[str, Any]], subtask_ids: list[str], seeds: list[int], use_llm: bool
) -> dict[str, Any]:
    """Pure aggregation of collected episodes (so a saved run can be re-aggregated identically)."""
    summary: dict[str, Any] = {
        "n_episodes": len(episodes),
        "n_pilots": len(subtask_ids),
        "seeds": list(seeds),
        "ci_method": "cluster bootstrap resampling the pilots (seeds within a pilot are correlated)",
        "oracle": _agg_clustered(_by_cluster(episodes, lambda e: e["oracle_score"])),
        "rules": _agg_clustered(_by_cluster(episodes, lambda e: e["rules"]["score"])),
        "oracle_minus_rules": _agg_clustered(
            _by_cluster(episodes, lambda e: e["oracle_score"] - e["rules"]["score"])
        ),
        "by_seed": _by_seed(episodes, seeds, use_llm),
    }
    if not use_llm:
        return summary
    llm = [e["llm"] for e in episodes if "llm" in e]
    completed = [x for x in llm if x.get("completed")]
    llm_all_by: dict[str, list[float]] = {}
    llm_comp_by: dict[str, list[float]] = {}
    lr_by: dict[str, list[float]] = {}
    incomplete: list[dict[str, Any]] = []
    for e in episodes:
        if "llm" not in e:
            continue
        x = e["llm"]
        sid = e["subtask_id"]
        llm_all_by.setdefault(sid, []).append(float(x.get("score", 0.0)))
        if x.get("completed"):
            llm_comp_by.setdefault(sid, []).append(float(x["score"]))
            lr_by.setdefault(sid, []).append(float(x["score"]) - float(e["rules"]["score"]))
        else:
            incomplete.append(
                {
                    "subtask_id": sid,
                    "seed": e["seed"],
                    "reason": "timeout"
                    if x.get("timed_out")
                    else ("is_error" if x.get("is_error") else x.get("parse_note")),
                }
            )
    latencies = [x["duration_ms"] for x in completed if isinstance(x.get("duration_ms"), int)]
    summary.update(
        {
            "llm_completion_rate": round(len(completed) / len(llm), 4) if llm else None,
            "llm_incomplete": incomplete,
            "llm_score_completed": _agg_clustered(llm_comp_by),
            "llm_score_all": _agg_clustered(llm_all_by),
            "llm_minus_rules": _agg_clustered(lr_by),
            "llm_mean_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
            "llm_latency_p95_ms": _pctl(latencies, 0.95),
            "llm_total_tool_failures": sum(x.get("tool_failures", 0) for x in llm),
            "llm_total_cost_usd_listprice": round(
                sum(x.get("cost_usd_listprice") or 0.0 for x in llm), 4
            ),
        }
    )
    return summary


def run_baselines(
    subtask_ids: list[str] | None = None,
    *,
    split: Split = "dev",
    seed: int = 1,
    seeds: list[int] | None = None,
    model: str = "haiku",
    use_llm: bool = True,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    ids = subtask_ids or pilot_ids()
    seed_list = seeds if seeds else [seed]
    episodes = [
        run_episode(sid, split, s, model=model, use_llm=use_llm, timeout_s=timeout_s)
        for sid in ids
        for s in seed_list
    ]

    summary = summarize_episodes(episodes, ids, seed_list, use_llm)
    llm = [e["llm"] for e in episodes if "llm" in e]
    model_used_observed = sorted({x["model_used"] for x in llm if x.get("model_used")}) or None
    providers_observed = sorted({x["provider"] for x in llm if x.get("provider")}) or None

    return {
        "schema_version": 2,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "labels": LABELS,
        "auth": (
            "claude.ai subscription CLI; the runner scrubs API-key/provider env vars and does not "
            "itself introduce API billing, but cannot override operator apiKeyHelper/settings/stored "
            "credentials (operator responsibility). provider/cost_basis recorded for audit; cost is "
            "LIST price, informational only."
        ),
        "model_requested": model,
        "model_used_observed": model_used_observed,
        "providers_observed": providers_observed,
        "split": split,
        "seeds": seed_list,
        "per_pilot": _per_pilot(episodes, ids, use_llm),
        "episodes": episodes,
        "summary": summary,
        "caveat": "Measurement of discrimination only; NOT an externally validated benchmark and NOT READY_BENCHMARK.",
    }


def _per_pilot(
    episodes: list[dict[str, Any]], ids: list[str], use_llm: bool
) -> list[dict[str, Any]]:
    rows = []
    for sid in ids:
        es = [e for e in episodes if e["subtask_id"] == sid]
        row: dict[str, Any] = {
            "subtask_id": sid,
            "service": es[0]["service"] if es else None,
            "oracle_mean": _mean([e["oracle_score"] for e in es]),
            "rules_mean": _mean([e["rules"]["score"] for e in es]),
        }
        if use_llm:
            comp = [e["llm"] for e in es if "llm" in e and e["llm"].get("completed")]
            row["llm_mean_completed"] = _mean([x["score"] for x in comp])
            row["llm_completion"] = round(
                sum(1 for e in es if "llm" in e and e["llm"].get("completed")) / len(es), 4
            )
        rows.append(row)
    return rows


def write_report(report: dict[str, Any], out_dir: Path | None = None) -> tuple[Path, Path]:
    if report["split"] == "hidden":
        raise ValueError(
            "refusing to write a hidden-split baseline report to disk (sealed split); "
            "run against 'dev', or consume the in-memory summary only."
        )
    base = out_dir or (repo_root() / "gold" / "baselines")
    base.mkdir(parents=True, exist_ok=True)
    seeds = "-".join(str(s) for s in report["seeds"])
    tag = f"{report['model_requested']}_{report['split']}_seeds{seeds}"
    jpath = base / f"{tag}.json"
    jpath.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mpath = base / f"{tag}.md"
    mpath.write_text(_markdown(report), encoding="utf-8")
    return jpath, mpath


def _ci_str(agg: dict[str, Any] | None) -> str:
    if not agg:
        return "—"
    ci = agg.get("ci95_cluster")
    cis = f" clusterCI95[{ci[0]},{ci[1]}]" if ci else ""
    return f"{agg.get('mean')}{cis}"


def _markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# Gold baseline run — {report['model_requested']} / {report['split']} / seeds {report['seeds']}",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Auth: {report['auth']}",
        f"- Models observed: {report.get('model_used_observed')}  providers: {report.get('providers_observed')}",
        f"- Labels: {', '.join(report['labels'])}",
        f"- {report['caveat']}",
        "",
        "## Summary (mean over episodes; 95% CI = cluster bootstrap over pilots)",
        "",
        f"- episodes: {s.get('n_episodes')} ({s.get('n_pilots')} pilots x {len(report['seeds'])} seeds)",
        f"- CI method: {s.get('ci_method')}",
        f"- oracle: {_ci_str(s.get('oracle'))}",
        f"- rules (naive): {_ci_str(s.get('rules'))}",
        f"- oracle − rules (paired): {_ci_str(s.get('oracle_minus_rules'))}",
    ]
    if report["summary"].get("llm_score_all") is not None:
        lines += [
            f"- LLM completion rate: {s.get('llm_completion_rate')}",
            f"- LLM score (completed): {_ci_str(s.get('llm_score_completed'))}",
            f"- LLM score (all episodes): {_ci_str(s.get('llm_score_all'))}",
            f"- LLM − rules (paired, completed): {_ci_str(s.get('llm_minus_rules'))}",
            f"- LLM latency: mean {s.get('llm_mean_latency_ms')} ms, p95 {s.get('llm_latency_p95_ms')} ms  tool failures: {s.get('llm_total_tool_failures')}",
            f"- LLM incomplete episodes: {s.get('llm_incomplete')}",
            f"- LLM list-price cost (informational): ${s.get('llm_total_cost_usd_listprice')}",
        ]
    lines += [
        "",
        "## Per-seed (run-to-run variability; 3 seeds = limited evidence of stability)",
        "",
    ]
    lines += ["| Seed | Oracle | Rules | LLM completed | Completion |", "|---|---|---|---|---|"]
    for r in s.get("by_seed", []):
        lines.append(
            f"| {r['seed']} | {r['oracle_mean']} | {r['rules_mean']} | "
            f"{r.get('llm_mean_completed', '—')} | {r.get('llm_completion', '—')} |"
        )
    lines += [
        "",
        "## Per-pilot (mean over seeds)",
        "",
        "| Subtask | Svc | Oracle | Rules | LLM | Completion |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["per_pilot"]:
        lines.append(
            f"| {row['subtask_id']} | {row['service']} | {row['oracle_mean']} | {row['rules_mean']} | "
            f"{row.get('llm_mean_completed', '—')} | {row.get('llm_completion', '—')} |"
        )
    return "\n".join(lines) + "\n"
