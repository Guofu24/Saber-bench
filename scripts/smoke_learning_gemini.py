"""Opt-in Gemini check: real plans, isolated team pools, reflection and client replay.

The harness deliberately creates three HTTP errors in a synthetic application lab.
They are test setup, not claimed model mistakes. Raw keys, responses and provider
errors are never printed. Existing worlds and repository skills are not modified.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from saber.agents.gemini import _urllib_transport
from saber.population.office import OfficeEmitter
from saber.world import learning
from saber.world.agents import action, llm_messages, parse_plan
from saber.world.key_layout import TeamKeyLayout
from saber.world.learning_eval import install_suite
from saber.world.learning_worker import Learner
from saber.world.models import Actor, WorldConfig
from saber.world.quota import TeamQuotaProvider
from saber.world.runtime import Runner, WorldLock, atomic_json
from saber.world.store import Store


def config() -> WorldConfig:
    return WorldConfig(
        actors=[
            Actor(
                id="check-client",
                team="client",
                role="employee",
                goal="Complete ordinary application work using your own session.",
            ),
            Actor(
                id="check-red",
                team="red",
                role="recon",
                goal="Inspect the local application using granted discovery tools; stay within this synthetic lab.",
            ),
            Actor(
                id="check-blue",
                team="blue",
                role="monitor",
                goal="Review observed telemetry; do not invent a case or conclude an attack from an HTTP status alone.",
            ),
        ],
        learning_interval_ticks=10000,
    )


def exercise(runner: Runner, provider: TeamQuotaProvider) -> dict[str, Any]:
    """Use the production prompt/parser, HTTP tool service, learner and replay gate."""
    runner.world.advance()
    plans = {}
    setup = {
        "client": action("call_app"),
        "red": action("read_document", document="welcome"),
        "blue": action("get_case", case_id="case-not-created"),
    }
    for actor in runner.config.actors:
        client = runner.clients[actor.id]
        result = client.act(setup[actor.team])
        client.act(
            action(
                "write_note",
                kind="observation",
                text=(
                    f"The test harness attempted {result['tool']} and received HTTP {result['status']}. "
                    "This was a controlled setup action, not a model-selected failure. Determine the missing prerequisite before retrying."
                ),
                evidence_ids=[result["event_id"]],
            )
        )
        outcome: dict[str, Any] = {"seed_http_status": result["status"], "executed": []}
        try:
            response = provider.generate_for(
                actor.team,
                llm_messages(
                    actor,
                    client.observe(),
                    pinned=learning.prompt_version(
                        runner.store, learning.actor_skill(runner.world, actor)
                    ),
                ),
            )
            actions, _ = parse_plan(actor, response.text)
            outcome["parsed_actions"] = len(actions)
            for chosen in actions:
                executed = client.act(chosen)
                outcome["executed"].append(
                    {
                        "tool": chosen.tool,
                        "event_id": executed["event_id"],
                        "http_status": executed["status"],
                    }
                )
                if client.observe()["control"]["status"] != "ACTIVE":
                    break
        except Exception as exc:
            outcome["error_kind"] = type(exc).__name__
        with runner.store.transaction():
            learning.seal(runner.world, actor, "run_end")
        plans[actor.team] = outcome
        print(json.dumps({"phase": "plan_execution", "team": actor.team, **outcome}), flush=True)

    learner = Learner(runner.world, provider)
    try:
        for job in range(8):
            if not learner.process_one():
                break
            print(
                json.dumps({"phase": "learning", "job": job + 1, **learning.summary(runner.store)}),
                flush=True,
            )
    finally:
        learner.close()

    episodes = [
        {k: e.get(k) for k in ("id", "team", "status", "model", "error_kind")}
        for e in runner.store.items("learning-episodes").values()
    ]
    proposals = [
        {
            k: p.get(k)
            for k in (
                "id",
                "team",
                "skill",
                "status",
                "evaluation_id",
                "published_version",
                "error_kind",
            )
        }
        for p in runner.store.items("learning-proposals").values()
    ]
    evaluations = list(runner.store.items("learning-evaluations").values())
    client_evaluations = [
        e
        for e in evaluations
        if any(p["id"] == e["proposal_id"] and p["team"] == "client" for p in proposals)
    ]
    planning_ok = all(
        any(200 <= a["http_status"] < 300 for a in outcome["executed"])
        for outcome in plans.values()
    )
    reflection_ok = all(
        any(e["team"] == team and e["status"] in {"REFLECTED", "NO_LESSON"} for e in episodes)
        for team in plans
    )
    # A rejection is a valid gate result, not evidence of a learned improvement.
    pipeline_ok = planning_ok and reflection_ok and bool(client_evaluations)
    return {
        "pipeline_completed": pipeline_ok,
        "plans": plans,
        "episodes": episodes,
        "proposals": proposals,
        "evaluations": evaluations,
        "skill_improved_on_submitted_replay": any(e["passed"] for e in client_evaluations),
        "replay_completed": bool(client_evaluations),
        "scope": "controlled synthetic setup; real Gemini; client next-action replay only; no claim of general SOC improvement",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--key-pool", type=Path, default=Path("keys_pool.txt"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--call-budget", type=int, default=24)
    args = parser.parse_args()
    if not args.live or not 1 <= args.call_budget <= 24:
        parser.error("Requires --live and a call budget between 1 and 24.")
    if args.out.exists():
        parser.error("Use a new output directory.")

    # Credentials remain inside the application. Only ordinal key positions leave this scope.
    layout = TeamKeyLayout.from_file(args.key_pool)
    positions = {key: i + 1 for i, key in enumerate(layout.pool.keys)}
    exchanges: list[dict[str, Any]] = []

    def transport(url, key, body):
        started = time.monotonic()
        item = {"key_position": positions[key]}
        try:
            status, data = _urllib_transport(url, key, body)
        except Exception:
            item["transport_error"] = True
            exchanges.append(item)
            print(json.dumps(item), flush=True)
            raise
        usage = data.get("usageMetadata") or {}
        item.update(
            http_status=status,
            seconds=round(time.monotonic() - started, 2),
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
        )
        exchanges.append(item)
        print(json.dumps(item), flush=True)
        return status, data

    with WorldLock(args.out):
        cfg = config()
        atomic_json(args.out / "config.json", cfg.model_dump(mode="json"))
        store = Store(args.out)
        runner = None
        try:
            # Do not start unrelated background planner/learner work during this bounded harness.
            runner = Runner(store, cfg, emitter=OfficeEmitter(sink=lambda _: None))
            provider = TeamQuotaProvider(
                store, layout, model=args.model, call_budget=args.call_budget, transport=transport
            )
            with store.transaction():
                store.put("meta", "engine", "hybrid")
                store.put("meta", "llm_key_layout", "teams")
            suite_path = Path(__file__).resolve().parents[1] / "config/learning/client-session.json"
            suite_id = install_suite(store, json.loads(suite_path.read_text(encoding="utf-8")))
            result = exercise(runner, provider)
            runner.close()
            report = runner.world.report() | {"stop_reason": "learning_live_check"}
            atomic_json(args.out / "report.json", report)
            result.update(
                model=args.model,
                call_budget=args.call_budget,
                suite_id=suite_id,
                usage=report["llm"],
                pools=report["llm_pools"],
                exchanges=exchanges,
                http_status_counts=dict(
                    Counter(str(x.get("http_status", "transport_error")) for x in exchanges)
                ),
            )
            atomic_json(args.out / "live-learning-check.json", result)
            print(
                json.dumps(
                    {
                        "pipeline_completed": result["pipeline_completed"],
                        "skill_improved_on_submitted_replay": result[
                            "skill_improved_on_submitted_replay"
                        ],
                        "usage": result["usage"],
                        "evidence": str(args.out / "live-learning-check.json"),
                    }
                ),
                flush=True,
            )
            return 0 if result["pipeline_completed"] else 1
        finally:
            if runner is not None:
                runner.close()
            store.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print('{"fatal_error":true,"details":"redacted"}', flush=True)
        raise SystemExit(2) from None
