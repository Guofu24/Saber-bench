"""Phase F2/F3 — exercise a real subtask contract against LIVE lab telemetry.

Binds subtask **T0020.001** (author a detection rule; source aggregate
``max(0, M'/M - N'/(N'+M'))`` over a line corpus) to the ``web_sqli_probe`` live episode: the
corpus is the service's REAL access log, M is the control-plane's malicious-line set, and the
agent's regex is run (sandboxed) over the real lines. The contract is used verbatim, not weakened.

Baselines compared on identical episodes: naive regex, strong conventional regex, and the
subscription LLM in single and coordinated multi-agent modes. Every observation carries valid
evidence references (the matched line ids, ⊆ the episode's evidence ids); agent-visible evidence is
the access log only — the control-plane truth stays sealed. Measurement only; not READY_BENCHMARK.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.baselines.claude_cli import CliInvocation, run_claude_cli
from saber.baselines.prompt import extract_answer_json
from saber.baselines.strong import strong_answer  # reuse the conventional WAF regex (T0020)
from saber.catalog.loader import repo_root
from saber.grading.execsandbox import run_regex_rule
from saber.range.live.controlplane import run_episode

SUBTASK_ID = "T0020.001"
SOURCE_AGGREGATE = "max(0, M'/M - N'/(N'+M'))"
LABELS = ["LIVE_LAB_EXECUTION", "T0020_CONTRACT", "DEV_SIMULATION_ONLY"]

_NAIVE_PATTERN = r"select|union|drop|or|sleep"  # weak word-level floor (trips on benign words)


def _llm_prompt(log_lines: list[str]) -> str:
    corpus = "\n".join(log_lines)
    return (
        "You are a SOC detection engineer. Below is a REAL web access log (one JSON record per "
        "line) captured from a live service. Some requests are SQL-injection probes.\n\n"
        f"ACCESS LOG:\n{corpus}\n\n"
        "Write a single Python regular expression that matches the SQL-injection request lines and "
        "NOT the benign ones. Respond with ONLY this JSON object, no commentary:\n"
        '{"rule": {"engine": "regex", "pattern": "<regex>", "ignore_case": true}}'
    )


def _reviewer_prompt(log_lines: list[str], draft: dict[str, Any]) -> str:
    return (
        "You are a senior detection reviewer. Improve the junior analyst's regex to reduce false "
        "positives (benign lines matched) and false negatives (missed probes).\n\n"
        f"ACCESS LOG:\n{chr(10).join(log_lines)}\n\n"
        f"DRAFT: {json.dumps(draft)}\n\n"
        'Return ONLY the corrected JSON: {"rule": {"engine": "regex", "pattern": "<regex>", '
        '"ignore_case": true}}'
    )


def _pattern_of(answer: dict[str, Any] | None) -> tuple[str, bool]:
    rule = (answer or {}).get("rule") or {}
    pat = rule.get("pattern")
    ic = bool(rule.get("ignore_case", True))
    return (pat if isinstance(pat, str) else ""), ic


def _call(
    prompt: str, *, model: str, timeout_s: float
) -> tuple[dict[str, Any] | None, CliInvocation, int]:
    tmp = tempfile.mkdtemp(prefix="saber-live-agent-")
    t0 = time.monotonic()
    try:
        inv = run_claude_cli(prompt, model=model, cwd=tmp, timeout_s=timeout_s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    answer = extract_answer_json(inv.result_text)[0] if inv.ok else None
    return answer, inv, int((time.monotonic() - t0) * 1000)


def grade_regex(
    pattern: str, log_lines: list[str], truth_ids: set[str], *, ignore_case: bool
) -> dict[str, Any]:
    """Run the regex (sandboxed) over the real log and score with the T0020 source formula."""
    res = run_regex_rule(pattern, log_lines, ignore_case=ignore_case)
    matched_ids = {f"line-{i}" for i in res.matched}
    m = len(truth_ids)
    m_hit = len(matched_ids & truth_ids)  # M'
    n_fp = len(matched_ids - truth_ids)  # N'
    score = 0.0
    if res.parse_ok and not res.timed_out and m:
        score = max(0.0, (m_hit / m) - (n_fp / (n_fp + m_hit) if (n_fp + m_hit) else 0.0))
    return {
        "score": round(score, 4),
        "parse_ok": res.parse_ok,
        "timed_out": res.timed_out,
        "error": res.error,
        "matched_refs": sorted(matched_ids),
        "false_positives": n_fp,
        "false_negatives": m - m_hit,
        "evidence_refs_valid": matched_ids <= set(f"line-{i}" for i in range(len(log_lines))),
    }


def _baseline_answer(mode: str, episode: Any, *, model: str, timeout_s: float) -> dict[str, Any]:
    """Return {answer, calls:[inv], wall_ms, completed} for one baseline on one episode."""
    log = episode.access_log_lines
    if mode == "naive":
        return {
            "answer": {"rule": {"engine": "regex", "pattern": _NAIVE_PATTERN, "ignore_case": True}},
            "calls": [],
            "wall_ms": 0,
            "completed": True,
        }
    if mode == "strong":
        return {
            "answer": strong_answer(SUBTASK_ID, episode),
            "calls": [],
            "wall_ms": 0,
            "completed": True,
        }
    if mode == "single":
        ans, inv, w = _call(_llm_prompt(log), model=model, timeout_s=timeout_s)
        return {
            "answer": ans,
            "calls": [inv],
            "wall_ms": w,
            "completed": ans is not None and not inv.timed_out,
        }
    if mode == "multi_agent":
        draft, inv1, w1 = _call(_llm_prompt(log), model=model, timeout_s=timeout_s)
        calls = [inv1]
        wall = w1
        answer = draft
        if draft is not None:
            final, inv2, w2 = _call(_reviewer_prompt(log, draft), model=model, timeout_s=timeout_s)
            calls.append(inv2)
            wall += w2
            if final is not None:
                answer = final
        return {
            "answer": answer,
            "calls": calls,
            "wall_ms": wall,
            "completed": answer is not None and not inv1.timed_out,
        }
    raise ValueError(f"unknown mode {mode!r}")


def run_live_benchmark(
    *,
    seeds: list[int],
    model: str = "haiku",
    modes: tuple[str, ...] = ("naive", "strong", "single", "multi_agent"),
    use_llm: bool = True,
    timeout_s: float = 150.0,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Run T0020 on live web_sqli_probe episodes across seeds; compare baselines; full receipts."""
    wd = workdir or (repo_root() / "runs" / "live-bench")
    active = tuple(m for m in modes if use_llm or m in ("naive", "strong"))
    episodes_out: list[dict[str, Any]] = []
    for seed in seeds:
        ep = run_episode("web_sqli_probe", seed, workdir=wd)
        truth = set(ep.gold_truth["malicious_line_ids"])
        receipts: dict[str, Any] = {}
        for mode in active:
            run = _baseline_answer(mode, ep, model=model, timeout_s=timeout_s)
            pat, ic = _pattern_of(run["answer"])
            graded = (
                grade_regex(pat, ep.access_log_lines, truth, ignore_case=ic)
                if run["completed"]
                else {
                    "score": 0.0,
                    "parse_ok": False,
                    "timed_out": any(c.timed_out for c in run["calls"]),
                    "matched_refs": [],
                    "false_positives": None,
                    "false_negatives": None,
                    "evidence_refs_valid": None,
                }
            )
            receipts[mode] = {
                **graded,
                "completed": run["completed"],
                "n_calls": len(run["calls"]),
                "wall_ms": run["wall_ms"],
                "tool_failures": sum(c.tool_failures() for c in run["calls"]),
                "duration_ms": sum(c.duration_ms or 0 for c in run["calls"]) or None,
                "model_used": next((c.model_used for c in run["calls"] if c.model_used), None),
                "cost_usd_listprice": round(sum(c.total_cost_usd or 0.0 for c in run["calls"]), 6),
                "pattern": pat,
            }
        episodes_out.append(
            {
                "scenario": ep.scenario,
                "seed": seed,
                "host_os": ep.host_os,
                "scenario_success": ep.cross_check_ok and ep.lab_state["reset_ok"],
                "telemetry": {
                    "log_lines": len(ep.access_log_lines),
                    "access_log_sha256": ep.access_log_sha256,
                },
                "control_plane_truth": {
                    "m": ep.gold_truth["m"],
                    "cross_check_ok": ep.cross_check_ok,
                },
                "lab_state": ep.lab_state,
                "evidence_ids": len(ep.evidence_ids),
                "results": receipts,
            }
        )

    def mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 4) if xs else None

    summary = {}
    for mode in active:
        rs = [e["results"][mode] for e in episodes_out]
        done = [r for r in rs if r["completed"]]
        summary[mode] = {
            "score_mean": mean([r["score"] for r in rs]),
            "score_completed_mean": mean([r["score"] for r in done]),
            "completion_rate": round(len(done) / len(rs), 4) if rs else None,
            "fp_total": sum(
                r["false_positives"] for r in rs if isinstance(r["false_positives"], int)
            ),
            "fn_total": sum(
                r["false_negatives"] for r in rs if isinstance(r["false_negatives"], int)
            ),
            "n_calls_total": sum(r["n_calls"] for r in rs),
            "tool_failures_total": sum(r["tool_failures"] for r in rs),
            "evidence_valid_all": all(
                r["evidence_refs_valid"] for r in rs if r["evidence_refs_valid"] is not None
            ),
            "cost_listprice": round(sum(r["cost_usd_listprice"] for r in rs), 4),
        }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "subtask": SUBTASK_ID,
        "source_aggregate": SOURCE_AGGREGATE,
        "labels": LABELS,
        "model_requested": model,
        "seeds": seeds,
        "scenario": "web_sqli_probe",
        "episodes": episodes_out,
        "summary": summary,
        "caveat": "Real telemetry, automated-lab ground truth; T0020 source contract exercised "
        "verbatim. Measurement only; NOT independently validated gold; NOT READY_BENCHMARK.",
    }


def write_live_benchmark(report: dict[str, Any], out_dir: Path | None = None) -> Path:
    base = out_dir or (repo_root() / "gold" / "range")
    base.mkdir(parents=True, exist_ok=True)
    seeds = "-".join(str(s) for s in report["seeds"])
    path = base / f"live_bench_{report['model_requested']}_seeds{seeds}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
