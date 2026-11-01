"""Opt-in live check: three real agents, isolated queues, restart and local-quota failover.

Only status codes, key positions and counters are printed. Credentials are loaded
by the application and sent only through the existing Gemini transport.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

from saber.agents.gemini import _urllib_transport
from saber.population.office import OfficeEmitter
from saber.world.key_layout import TeamKeyLayout
from saber.world.models import Actor, WorldConfig
from saber.world.quota import TeamQuotaProvider
from saber.world.runtime import Runner, WorldLock, atomic_json
from saber.world.store import Store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Actually call Gemini.")
    parser.add_argument("--key-pool", type=Path, default=Path("keys_pool.txt"))
    parser.add_argument("--out", type=Path, required=True, help="New output directory.")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--call-budget", type=int, default=12)
    parser.add_argument("--rounds", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    if not args.live or not 1 <= args.call_budget <= 12:
        parser.error("Requires --live and a call budget between 1 and 12.")
    if args.out.exists():
        parser.error("Use a new output directory; existing worlds are never overwritten.")

    layout = TeamKeyLayout.from_file(args.key_pool)
    positions = {key: index + 1 for index, key in enumerate(layout.pool.keys)}
    config = WorldConfig(
        actors=[
            Actor(
                id="check-client", team="client", role="employee", goal="Do ordinary document work."
            ),
            Actor(
                id="check-red",
                team="red",
                role="recon",
                goal="Discover the local lab application using its granted tools.",
            ),
            Actor(
                id="check-blue",
                team="blue",
                role="monitor",
                goal="Review lab telemetry and share findings with your team.",
            ),
        ],
        red_start_tick=1,
        profile_refresh_ticks=100000,
        llm_workers=3,
    )
    exchanges = []
    output_lock = threading.Lock()

    def transport(url, key, body):
        started = time.monotonic()
        entry = {"key_position": positions[key]}
        try:
            status, data = _urllib_transport(url, key, body)
        except Exception:
            entry["transport_error"] = True
            with output_lock:
                exchanges.append(entry)
                print(json.dumps(entry), flush=True)
            raise
        candidates = data.get("candidates") or []
        candidate = candidates[0] if candidates else {}
        finish = candidate.get("finishReason")
        entry.update(
            http_status=status,
            seconds=round(time.monotonic() - started, 2),
            finish_reason=finish
            if finish in {"STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER"}
            else None,
            response_characters=sum(
                len(str(p.get("text", "")))
                for p in candidate.get("content", {}).get("parts", [])
                if not p.get("thought")
            ),
            input_tokens=int(data.get("usageMetadata", {}).get("promptTokenCount", 0)),
            output_tokens=int(data.get("usageMetadata", {}).get("candidatesTokenCount", 0)),
            thought_tokens=int(data.get("usageMetadata", {}).get("thoughtsTokenCount", 0)),
        )
        with output_lock:
            exchanges.append(entry)
            print(json.dumps(entry), flush=True)
        return status, data

    rounds = []
    with WorldLock(args.out):
        atomic_json(args.out / "config.json", config.model_dump(mode="json"))
        for number in range(1, args.rounds + 1):
            store = Store(args.out)
            runner = None
            try:
                # Test-only cap forces queued-key selection without exhausting Google quota.
                provider = TeamQuotaProvider(
                    store,
                    layout,
                    model=args.model,
                    call_budget=args.call_budget,
                    rpd=1,
                    transport=transport,
                )
                with store.transaction():
                    for actor in config.actors:
                        memory = store.get("memory", actor.id, {})
                        memory["next_plan"] = 0
                        memory.pop("plan_source", None)
                        store.put("memory", actor.id, memory)
                runner = Runner(
                    store,
                    config,
                    provider=provider,
                    emitter=OfficeEmitter(sink=lambda events: None),
                )
                start_tick = runner.world.tick
                started = time.monotonic()
                next_progress = 20.0
                while time.monotonic() - started < 190:
                    runner.step()
                    finished = all(
                        "plan_source" in store.get("memory", a.id, {})
                        and not store.get("plans", a.id, [])
                        for a in config.actors
                    )
                    if finished:
                        break
                    if time.monotonic() - started >= next_progress:
                        print(
                            json.dumps(
                                {
                                    "round": number,
                                    "waiting": True,
                                    "usage": store.get("meta", "llm_usage", {}),
                                }
                            ),
                            flush=True,
                        )
                        next_progress += 20
                    time.sleep(1)
                runner.close()
                report = runner.world.report() | {"stop_reason": "live_smoke_complete"}
                atomic_json(args.out / "report.json", report)
                actions = {}
                events = {
                    e["id"]: e for e in store.events(through_tick=runner.world.tick, limit=2000)
                }
                for actor in config.actors:
                    journal = store.get("journals", actor.id, [])
                    actions[actor.team] = [
                        {
                            "tool": item["action"]["tool"],
                            "event_id": item["event_id"],
                            "http_status": events[item["event_id"]]["status"],
                        }
                        for item in journal
                        if item["tick"] > start_tick and item["source"] == "llm"
                    ]
                result = {
                    "round": number,
                    "usage": report["llm"],
                    "pools": report["llm_pools"],
                    "llm_actions": actions,
                }
                rounds.append(result)
                print(json.dumps(result), flush=True)
                atomic_json(
                    args.out / "live-check.json",
                    {
                        "model": args.model,
                        "rounds": rounds,
                        "exchanges": exchanges,
                        "local_calls_per_key_per_day": 1,
                    },
                )
            finally:
                if runner is not None:
                    runner.close()
                store.close()
    passed = len(rounds) == args.rounds and all(
        all(
            any(200 <= action["http_status"] < 300 for action in actions)
            for actions in r["llm_actions"].values()
        )
        for r in rounds
    )
    if args.rounds == 2:
        passed = passed and all(
            rounds[0]["pools"][team]["active_key"] != rounds[1]["pools"][team]["active_key"]
            for team in layout.indices
        )
    atomic_json(
        args.out / "live-check.json",
        {
            "model": args.model,
            "passed": passed,
            "rounds": rounds,
            "exchanges": exchanges,
            "local_calls_per_key_per_day": 1,
        },
    )
    print(json.dumps({"passed": passed, "evidence": str(args.out / "live-check.json")}), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # No traceback/provider payload may accidentally reveal request credentials.
        print('{"fatal_error":true,"details":"redacted"}', flush=True)
        raise SystemExit(2) from None
