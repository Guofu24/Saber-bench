"""Run one live population episode: red + client act, the range runs for real, blue investigates,
the orchestrator routes, and blue is scored against the SERVER-DERIVED truth.

LLM calls per episode (all against one budget-capped provider): red(1) + client(1) + orchestrator
routing(1) + blue(1) = 4. The case record is assembled deterministically from blue's findings and
the orchestrator's severity, so no extra billable call is spent on bookkeeping.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.agents.provider import LLMProvider
from saber.domain.errors import BudgetExceeded, IntegrationBlocked
from saber.population.agents import (
    BLUE_TEAM,
    AgentCall,
    BlueAgent,
    ClientAgent,
    Orchestrator,
    RedAgent,
)
from saber.population.menus import FAMILY_MENUS
from saber.population.office import ROLE_AGENTS, OfficeEmitter
from saber.range.live.controlplane import LiveLab, _derive_truth
from saber.range.live.scenarios import SCENARIOS
from saber.subtasks._hv.common import Rng

LABELS = ("AGENT_POPULATION_H5", "LIVE_RANGE", "DEV_SIMULATION_ONLY")


def _usage(call: AgentCall) -> dict[str, int]:
    return {"in": call.input_tokens, "out": call.output_tokens}


@dataclass
class PopulationEpisode:
    scenario: str
    seed: int
    blue_team: str  # the team(s) that worked the case ("MON" or "MON+HUNT+IR")
    requests_sent: int
    log_lines: int
    truth_malicious: int
    blue_tp: int
    blue_fp: int
    blue_fn: int
    precision: float
    recall: float
    f1: float
    case: dict[str, Any]
    red_goal: str
    blue_summary: str
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cross_check_ok: bool
    reset_ok: bool
    all_targets_on_menu: bool
    n_clients: int = 1
    blue_teams: list[str] = field(default_factory=list)

    def row(self) -> dict[str, Any]:
        return asdict(self)


# Team name -> the operational skill it loads (reverse of BLUE_TEAM).
SKILL_FOR_TEAM = {team: skill for skill, team in BLUE_TEAM.items()}


def _prf(pred: set[str], truth: set[str]) -> tuple[int, int, int, float, float, float]:
    tp = len(pred & truth)
    fp = len(pred - truth)
    fn = len(truth - pred)
    precision = tp / (tp + fp) if (tp + fp) else (1.0 if not truth else 0.0)
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return tp, fp, fn, round(precision, 4), round(recall, 4), round(f1, 4)


def run_population_episode(
    scenario: str,
    seed: int,
    provider: LLMProvider,
    *,
    workdir: Path | None = None,
    emitter: OfficeEmitter | None = None,
    n_clients: int = 1,
    blue_teams: list[str] | None = None,
) -> PopulationEpisode:
    """Drive one full population episode over the real loopback range.

    ``n_clients`` benign client agents and either a single orchestrator-routed blue team
    (``blue_teams=None``) or several named blue teams investigating the same case
    (``blue_teams=["MON","HUNT","IR"]``, aggregated as the union of what they flag).
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    base = Path(workdir) if workdir is not None else (Path("runs") / "population")
    evidence_dir = base / scenario / f"seed-{seed}"
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir, ignore_errors=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    em = emitter or OfficeEmitter()  # disabled no-op when no office is attached
    model = getattr(provider, "model_id", "llm")
    n_clients = max(1, n_clients)
    client_ids = ["client"] if n_clients == 1 else [f"client-{i + 1}" for i in range(n_clients)]

    # Register the office roster for this episode (red, range, orchestrator, each client, each blue).
    em.agent("red", *ROLE_AGENTS["red"])
    em.agent("range", *ROLE_AGENTS["range"])
    em.agent("orchestrator", *ROLE_AGENTS["orchestrator"])
    for cid in client_ids:
        label = ROLE_AGENTS["client"][0] if cid == "client" else f"Client {cid.split('-')[-1]}"
        em.agent(cid, label, ROLE_AGENTS["client"][1], ROLE_AGENTS["client"][2])
    em.message(None, f"=== Episode {scenario} (seed {seed}) · {n_clients} client(s) ===")

    red = RedAgent(provider)
    orchestrator = Orchestrator(provider)
    all_calls: list[AgentCall] = []

    # 1) Red decides its attack (from the inert allowlist only).
    em.task("red", f"Tấn công {scenario}")
    em.status("red", "think")
    em.llm_start("red", model)
    t0 = time.monotonic()
    attack_plan, red_call = red.plan(scenario)
    all_calls.append(red_call)
    goal = str((red_call.obj or {}).get("goal", "")) if red_call.obj else ""
    em.llm_end("red", int((time.monotonic() - t0) * 1000), goal or "chose attack", _usage(red_call))
    em.message("red", f"{len(attack_plan)} inert actions · goal: {goal[:80]}")
    em.handoff("red", "range", "send_attack")

    # Each client agent adds its own benign cover traffic.
    benign_plan: list[dict[str, str]] = []
    for cid in client_ids:
        client = ClientAgent(provider)
        em.task(cid, f"Hoạt động nền {scenario}")
        em.status(cid, "think")
        em.llm_start(cid, model)
        t0 = time.monotonic()
        c_plan, c_call = client.plan(scenario)
        all_calls.append(c_call)
        benign_plan += c_plan
        em.llm_end(cid, int((time.monotonic() - t0) * 1000), f"{len(c_plan)} benign reqs", _usage(c_call))
        em.handoff(cid, "range", "benign_traffic")

    rng = Rng("population", scenario, str(seed))
    plan = rng.shuffle(attack_plan + benign_plan)

    # Safety invariant: every target actually sent must be a pre-vetted menu target for this family.
    allowed_targets = {a.target for a in FAMILY_MENUS[scenario]}
    on_menu = all(r["target"] in allowed_targets for r in plan)
    if not on_menu:  # refuse to send anything off-menu; keep only vetted entries
        plan = [r for r in plan if r["target"] in allowed_targets]

    # 2) Run the real range and derive ground truth server-side (independent of all agents).
    em.status("range", "tool", "🔧 run_episode")
    em.tool("range", "run_episode")
    fs_root = (evidence_dir / "webroot") if scenario == "fs_change" else None
    cron_root = (evidence_dir / "cronroot") if scenario == "persistence" else None
    lab = LiveLab(evidence_dir, fs_root=fs_root, cron_root=cron_root)
    lab.start()
    sent = lab.send(plan)
    lab.stop()
    reset_ok = lab.confirm_reset()
    raw_lines = lab.read_log_lines()
    parsed = [json.loads(ln) if ln.strip() else {} for ln in raw_lines]
    truth_idx = _derive_truth(scenario, parsed, fs_root, cron_root)
    truth_ids = {f"line-{i}" for i in truth_idx}
    em.message("range", f"{sent} requests · {len(raw_lines)} log lines · {len(truth_ids)} malicious (server-derived)")
    em.status("range", "idle")
    em.handoff("range", "orchestrator", "telemetry")

    # 3) Orchestrator routes: it always picks a primary team (severity too); in multi-team mode the
    #    whole named set works the case, otherwise just the routed team does.
    em.task("orchestrator", f"Route: {scenario}")
    em.status("orchestrator", "think")
    em.llm_start("orchestrator", model)
    t0 = time.monotonic()
    routed_skill, route_call = orchestrator.route(scenario, len(raw_lines))
    all_calls.append(route_call)
    routed_team = BLUE_TEAM.get(routed_skill, "MON")
    em.llm_end("orchestrator", int((time.monotonic() - t0) * 1000), f"route → {routed_team}", _usage(route_call))
    severity = str((route_call.obj or {}).get("severity", "medium")) if route_call.obj else "medium"

    if blue_teams:
        teams = [t.upper() for t in blue_teams if t.upper() in SKILL_FOR_TEAM]
    else:
        teams = [routed_team]
    if not teams:  # all names invalid -> fall back to what the orchestrator routed to
        teams = [routed_team]
    team_skills = [(t, SKILL_FOR_TEAM[t]) for t in teams]

    # 4) Each assigned team investigates the same real access log; findings are the union (hunt
    #    posture: do not miss). Per-team detail is kept in the case record.
    union_pred: set[str] = set()
    per_team: list[dict[str, Any]] = []
    summaries: list[str] = []
    for team, skill in team_skills:
        bid = "blue" if (not blue_teams and len(teams) == 1) else f"blue-{team}"
        em.agent(bid, f"Blue · {team}", ROLE_AGENTS["blue"][1], ROLE_AGENTS["blue"][2])
        em.handoff("orchestrator", bid, f"assign_{team}")
        em.task(bid, f"Điều tra {scenario}")
        em.status(bid, "tool", "🔧 read_access_log")
        em.tool(bid, "read_access_log")
        em.llm_start(bid, model)
        t0 = time.monotonic()
        findings, b_call = BlueAgent(provider).investigate(scenario, raw_lines, skill)
        all_calls.append(b_call)
        t_pred = {x for x in findings["malicious_line_ids"] if x.startswith("line-")}
        union_pred |= t_pred
        t_tp, t_fp, t_fn, t_p, t_r, t_f1 = _prf(t_pred, truth_ids)
        per_team.append({"team": team, "flagged": sorted(t_pred), "f1": t_f1, "fp": t_fp, "fn": t_fn,
                         "verdict": findings["verdict"]})
        summaries.append(f"{team}: {findings['summary']}" if findings["summary"] else team)
        em.llm_end(bid, int((time.monotonic() - t0) * 1000), findings["summary"] or f"{team} findings", _usage(b_call))
        em.message(bid, f"{team} flagged {len(t_pred)} · f1={t_f1} (fp={t_fp} fn={t_fn})")
        em.handoff(bid, "orchestrator", "report")

    # Aggregate (union across teams) is the case outcome.
    tp, fp, fn, precision, recall, f1 = _prf(union_pred, truth_ids)
    team_label = "+".join(teams)
    case = {
        "scenario": scenario,
        "assigned_team": team_label,
        "severity": severity,
        "status": "CLOSED_FP" if not truth_ids else ("CONTAINED" if f1 >= 0.99 else "INVESTIGATING"),
        "truth_malicious_lines": sorted(truth_ids),
        "blue_flagged_lines": sorted(union_pred),
        "f1": f1,
        "per_team": per_team,
        "opened_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (evidence_dir / "case.json").write_text(
        json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    em.message("orchestrator", f"case {case['status']} · severity={severity} · teams={team_label} · f1={f1}")
    for aid in ("red", "orchestrator", *client_ids, *[f"blue-{t}" for t in teams], "blue"):
        em.status(aid, "idle")

    return PopulationEpisode(
        scenario=scenario,
        seed=seed,
        blue_team=team_label,
        requests_sent=sent,
        log_lines=len(raw_lines),
        truth_malicious=len(truth_ids),
        blue_tp=tp,
        blue_fp=fp,
        blue_fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        case=case,
        red_goal=goal[:160],
        blue_summary=" | ".join(summaries)[:200],
        llm_calls=len(all_calls),
        input_tokens=sum(c.input_tokens for c in all_calls),
        output_tokens=sum(c.output_tokens for c in all_calls),
        cross_check_ok=True,  # targets are menu-vetted; truth is server-derived
        reset_ok=reset_ok,
        all_targets_on_menu=on_menu,
        n_clients=n_clients,
        blue_teams=teams,
    )


@dataclass
class PopulationReport:
    episodes: list[PopulationEpisode] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        eps = self.episodes
        n = len(eps) or 1
        return {
            "labels": list(LABELS),
            "n_episodes": len(eps),
            "blue_f1_mean": round(sum(e.f1 for e in eps) / n, 4),
            "blue_recall_mean": round(sum(e.recall for e in eps) / n, 4),
            "blue_precision_mean": round(sum(e.precision for e in eps) / n, 4),
            "total_llm_calls": sum(e.llm_calls for e in eps),
            "total_tokens_in": sum(e.input_tokens for e in eps),
            "total_tokens_out": sum(e.output_tokens for e in eps),
            "all_targets_on_menu": all(e.all_targets_on_menu for e in eps),
            "all_reset_ok": all(e.reset_ok for e in eps),
            "caveat": "DEV_SIMULATION_ONLY: living loop over the real range; NOT a validated benchmark.",
        }


def run_population(
    scenarios: list[str],
    seeds: list[int],
    provider: LLMProvider,
    *,
    workdir: Path | None = None,
    emitter: OfficeEmitter | None = None,
    n_clients: int = 1,
    blue_teams: list[str] | None = None,
) -> PopulationReport:
    """Run the population over several scenarios x seeds and collect the episodes."""
    report = PopulationReport()
    for scenario in scenarios:
        for seed in seeds:
            report.episodes.append(
                run_population_episode(
                    scenario, seed, provider, workdir=workdir, emitter=emitter,
                    n_clients=n_clients, blue_teams=blue_teams,
                )
            )
    return report


def run_forever(
    scenarios: list[str],
    provider: LLMProvider,
    *,
    workdir: Path | None = None,
    emitter: OfficeEmitter | None = None,
    n_clients: int = 3,
    blue_teams: list[str] | None = None,
    interval_s: float = 8.0,
    stop_file: Path | None = None,
    on_episode: Callable[[PopulationEpisode, int], None] | None = None,
    on_wait: Callable[[str], None] | None = None,
) -> PopulationReport:
    """Run episodes continuously until stopped: Ctrl+C, a STOP file, or the provider's billable-call
    budget cap (the safety valve). A 429'd key cools down and returns, so the pool is not burned out;
    when every key is momentarily cooling, the loop waits for the soonest one instead of failing.

    Each round reuses the SAME provider, so ``provider.calls`` accumulates toward ``budget_calls``;
    set that budget high as the hard safety valve. Returns the collected report when it stops.
    """
    report = PopulationReport()
    pool = getattr(provider, "pool", None)
    round_i = 0
    seed = 1
    while True:
        if stop_file is not None and Path(stop_file).exists():
            if on_wait:
                on_wait(f"stop file present ({stop_file}); stopping")
            break
        scenario = scenarios[round_i % len(scenarios)]
        try:
            ep = run_population_episode(
                scenario, seed, provider, workdir=workdir, emitter=emitter,
                n_clients=n_clients, blue_teams=blue_teams,
            )
        except BudgetExceeded:
            if on_wait:
                on_wait("billable-call budget reached (safety valve); stopping")
            break
        except IntegrationBlocked as exc:
            # Likely all keys cooling (quota) or a transient wall; wait for the soonest key and retry.
            eta = pool.next_cooldown_eta() if pool is not None else None
            wait = min(max(eta or interval_s, interval_s), 120.0)
            if on_wait:
                on_wait(f"paused {wait:.0f}s ({str(exc)[:60]})")
            time.sleep(wait)
            round_i += 1
            seed += 1
            continue
        report.episodes.append(ep)
        if on_episode:
            on_episode(ep, round_i)
        round_i += 1
        seed += 1
        if interval_s:
            time.sleep(interval_s)
    return report
