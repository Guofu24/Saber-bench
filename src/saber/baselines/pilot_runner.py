"""Run the rules + LLM baselines over gold pilot episodes and aggregate the metrics.

Measured per episode (Phase C): field-level component scores, false positives (where
the scorer exposes them), evidence/referential validity, latency, tool failures and
completion (did the model return a gradeable JSON answer). The LLM runs through the
subscription CLI in an isolated empty working directory; the rules baseline is
deterministic. Nothing here promotes a subtask to READY_BENCHMARK.
"""

from __future__ import annotations

import json
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

LABELS = ["GOLD_PILOT_V1", "LLM_BASELINE_CLI_SUBSCRIPTION"]

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


def _refang(text: str) -> str:
    return text.replace("[.]", ".").replace("hxxp", "http").lower()


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

    A heuristic proxy for 'did the answer stay grounded in the evidence'. Verdict/enum
    labels are excluded; a hallucinated host/IOC/path/rule not present in the artifact
    counts against grounding.
    """
    # Build the corpus from raw string leaves (not json.dumps) so backslash-heavy registry
    # paths are not mangled by JSON escaping, which would fake hallucinations.
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
    }


def _false_positive_count(components: list[dict[str, Any]]) -> int | None:
    """Pull a false-positive count out of component detail where the scorer exposes one."""
    total: int | None = None
    for comp in components:
        detail = comp.get("detail") or {}
        if not isinstance(detail, dict):
            continue
        for key in ("fp", "false_positives", "extra", "spurious", "fp_after"):
            if isinstance(detail.get(key), int):
                total = (total or 0) + int(detail[key])
    return total


def _safe_grade(pilot: GoldPilot, episode: GoldEpisode, answer: dict[str, Any], agent_id: str):  # type: ignore[no-untyped-def]
    try:
        return pilot.grade(episode, answer, agent_id=agent_id), None
    except Exception as exc:  # noqa: BLE001 - grading must never crash the run
        return None, f"{type(exc).__name__}: {exc}"


def _components(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []
    return [c.model_dump() for c in result.components]


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
    rules_res, rules_err = _safe_grade(pilot, episode, naive, "rules_baseline")
    rules_components = _components(rules_res)
    out: dict[str, Any] = {
        "subtask_id": subtask_id,
        "service": _service_of(subtask_id),
        "split": split,
        "episode_id": str(episode.episode_id),
        "oracle_score": oracle_score,
        "rules": {
            "score": round(rules_res.score, 4) if rules_res else 0.0,
            "error": rules_err,
            "components": rules_components,
            "false_positives": _false_positive_count(rules_components),
            "grounding": evidence_grounding(episode, naive),
        },
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
    completed = answer is not None and inv.ok and not inv.timed_out
    llm: dict[str, Any] = {
        "requested_model": inv.requested_model,
        "model_used": inv.model_used,
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
        res, err = _safe_grade(pilot, episode, answer, "llm_cli_baseline")
        comps = _components(res)
        llm.update(
            {
                "score": round(res.score, 4) if res else 0.0,
                "grade_error": err,
                "components": comps,
                "false_positives": _false_positive_count(comps),
                "grounding": evidence_grounding(episode, answer),
                "answer_keys": sorted(answer.keys()),
            }
        )
    else:
        llm.update({"score": 0.0, "components": [], "grounding": None})
    return llm


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def run_baselines(
    subtask_ids: list[str] | None = None,
    *,
    split: Split = "dev",
    seed: int = 1,
    model: str = "haiku",
    use_llm: bool = True,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    ids = subtask_ids or pilot_ids()
    episodes = [
        run_episode(sid, split, seed, model=model, use_llm=use_llm, timeout_s=timeout_s)
        for sid in ids
    ]

    oracle_scores = [e["oracle_score"] for e in episodes]
    rules_scores = [e["rules"]["score"] for e in episodes]
    summary: dict[str, Any] = {
        "n": len(episodes),
        "oracle_mean": _mean(oracle_scores),
        "rules_mean": _mean(rules_scores),
        "oracle_minus_rules": round((_mean(oracle_scores) or 0) - (_mean(rules_scores) or 0), 4),
    }
    model_used_observed = None
    if use_llm:
        llm = [e["llm"] for e in episodes if "llm" in e]
        completed = [x for x in llm if x.get("completed")]
        llm_scores = [x["score"] for x in completed]
        latencies = [x["duration_ms"] for x in completed if isinstance(x.get("duration_ms"), int)]
        used = {x.get("model_used") for x in llm if x.get("model_used")}
        model_used_observed = sorted(m for m in used if m)
        summary.update(
            {
                "llm_completion_rate": round(len(completed) / len(llm), 4) if llm else None,
                "llm_mean_score_completed": _mean(llm_scores),
                "llm_mean_score_all": _mean([x.get("score", 0.0) for x in llm]),
                "llm_minus_rules": round((_mean(llm_scores) or 0) - (_mean(rules_scores) or 0), 4),
                "llm_mean_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
                "llm_total_tool_failures": sum(x.get("tool_failures", 0) for x in llm),
                "llm_total_cost_usd_listprice": round(
                    sum(x.get("cost_usd_listprice") or 0.0 for x in llm), 4
                ),
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "labels": LABELS,
        "auth": "claude.ai subscription (API-key env scrubbed); cost figures are LIST price, informational only",
        "model_requested": model,
        "model_used_observed": model_used_observed,
        "split": split,
        "seed": seed,
        "use_llm": use_llm,
        "episodes": episodes,
        "summary": summary,
        "caveat": "Measurement of discrimination only; NOT an externally validated benchmark and NOT READY_BENCHMARK.",
    }


def write_report(report: dict[str, Any], out_dir: Path | None = None) -> tuple[Path, Path]:
    base = out_dir or (repo_root() / "gold" / "baselines")
    base.mkdir(parents=True, exist_ok=True)
    tag = f"{report['model_requested']}_{report['split']}_seed{report['seed']}"
    jpath = base / f"{tag}.json"
    jpath.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mpath = base / f"{tag}.md"
    mpath.write_text(_markdown(report), encoding="utf-8")
    return jpath, mpath


def _markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# Gold baseline run — {report['model_requested']} / {report['split']} / seed {report['seed']}",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Auth: {report['auth']}",
        f"- Models observed: {report.get('model_used_observed')}",
        f"- Labels: {', '.join(report['labels'])}",
        f"- {report['caveat']}",
        "",
        "## Summary",
        "",
        f"- oracle mean: {s.get('oracle_mean')}",
        f"- rules (naive) mean: {s.get('rules_mean')}  (oracle − rules = {s.get('oracle_minus_rules')})",
    ]
    if report["use_llm"]:
        lines += [
            f"- LLM completion rate: {s.get('llm_completion_rate')}",
            f"- LLM mean score (completed): {s.get('llm_mean_score_completed')}  (all episodes: {s.get('llm_mean_score_all')})",
            f"- LLM − rules: {s.get('llm_minus_rules')}",
            f"- LLM mean latency: {s.get('llm_mean_latency_ms')} ms",
            f"- LLM tool failures (denials+errors+timeouts): {s.get('llm_total_tool_failures')}",
            f"- LLM list-price cost (informational): ${s.get('llm_total_cost_usd_listprice')}",
        ]
    lines += [
        "",
        "## Per-episode",
        "",
        "| Subtask | Svc | Oracle | Rules | LLM | Completed | Grounding |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in report["episodes"]:
        llm = e.get("llm", {})
        g = llm.get("grounding") or {}
        frac = g.get("fraction")
        lines.append(
            f"| {e['subtask_id']} | {e['service']} | {e['oracle_score']} | {e['rules']['score']} | "
            f"{llm.get('score', '—')} | {llm.get('completed', '—')} | {frac if frac is not None else '—'} |"
        )
    return "\n".join(lines) + "\n"
