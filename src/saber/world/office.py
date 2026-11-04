"""Small operator-only snapshots; no prompts, documents, credentials or private plans."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from saber.world.models import WorldConfig, specialties_for
from saber.world.office_trace import trace
from saber.world.store import Store

USAGE_FIELDS = ("attempts", "successes", "input_tokens", "output_tokens")
ACTION_FIELDS = ("actions_llm", "actions_scripted", "actions_scripted_fallback")


def deployment_profile(root: Path) -> str:
    try:
        profile = json.loads((root / "deployment.json").read_text(encoding="utf-8")).get(
            "selected_profile"
        )
    except (OSError, ValueError, AttributeError):
        return "local"
    return profile if profile in {"local", "sandbox", "vm", "remote"} else "local"


def snapshot(
    store: Store,
    config: WorldConfig,
    report: dict[str, Any],
    *,
    run_id: str,
    profile: str,
    pending: set[str],
    stopped: bool,
    budget_exhausted: bool,
) -> dict[str, Any]:
    usage = report.get("llm", {})
    teams = ("client", "red", "blue")
    roster = []
    with store.lock:
        activity_trace = trace(store, config, report["tick"])
        all_tasks = list(store.items("tasks").values())
        all_proposals = list(store.items("learning-proposals").values())
        for actor in config.actors:
            memory = store.get("memory", actor.id, {})
            control = store.get("actor-control", actor.id, {"status": "ACTIVE"})
            tasks = [t for t in all_tasks if t["assignee"] == actor.id]
            active = next((t for t in tasks if t["status"] == "ACTIVE"), None)
            roster.append(
                {
                    "id": actor.id,
                    "team": actor.team,
                    "role": actor.role,
                    "specialties": list(specialties_for(actor)),
                    "control_status": control["status"],
                    "wake_tick": control.get("until_tick")
                    if control["status"] == "WAITING"
                    else None,
                    "active_specialty": active["specialty"] if active else actor.role,
                    "active_task": active["id"] if active else None,
                    "task_counts": {
                        s.lower(): sum(t["status"] == s for t in tasks)
                        for s in ("OFFERED", "ACTIVE", "BLOCKED", "DONE")
                    },
                    "learning_counts": {
                        "episodes": store.get("learning-counts", actor.id, {}).get("episodes", 0),
                        "proposals": sum(p["actor_id"] == actor.id for p in all_proposals),
                        "published": sum(
                            p["actor_id"] == actor.id and p["status"] == "PUBLISHED"
                            for p in all_proposals
                        ),
                    },
                    "activity": "idle"
                    if stopped
                    else "planning"
                    if actor.id in pending and control["status"] == "ACTIVE"
                    else "idle",
                    "turns": memory.get("turns", 0),
                    "last_tick": memory.get("last_tick"),
                    "last_tool": memory.get("last_tool"),
                    "last_status": memory.get("last_status"),
                    "source": memory.get("source", "none"),
                    **(
                        {
                            "executor": {
                                "host": memory.get("host"),
                                "pid": memory.get("pid"),
                                "job_id": memory.get("job_id"),
                                "exit_code": memory.get("exit_code"),
                                "artifacts": memory.get("artifacts", []),
                                "pending": actor.id in pending,
                            }
                        }
                        if config.execution_mode == "range"
                        else {}
                    ),
                }
            )
    result: dict[str, Any] = {
        "type": "world_snapshot",
        "schema_version": 1,
        "world_id": report["world_id"],
        "run_id": run_id,
        "profile": profile,
        "engine": report["engine"],
        "execution_mode": config.execution_mode,
        "status": "stopped" if stopped else "running",
        "updated_at": time.time(),
        "tick_seconds": config.tick_seconds,
        "tick": report["tick"],
        "actors": roster,
        "trace": activity_trace,
        "actions": {name: report["metrics"].get(name, 0) for name in ACTION_FIELDS},
        "llm": {name: usage.get(name, 0) for name in USAGE_FIELDS},
        "llm_by_team": {
            team: {
                name: usage.get("by_team", {}).get(team, {}).get(name, 0) for name in USAGE_FIELDS
            }
            for team in teams
        },
        "key_layout": report["llm_key_layout"],
        "pools": {
            team: {
                name: pool.get(name)
                for name in ("model", "first_key", "last_key", "keys", "active_key", "state")
            }
            for team, pool in report.get("llm_pools", {}).items()
            if team in teams
        },
        "budget_exhausted": budget_exhausted,
    }
    # The watch transport caps the indented UTF-8 snapshot at 256 KiB. Long
    # imported-log previews must not hide the entire office at a 200-actor roster.
    for event in (row for row in activity_trace["events"] if "forensics" in row):
        wire = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").replace("\n", os.linesep)
        if len(wire.encode()) <= 250000:
            break
        previous = event["forensics"]
        event["forensics"] = {
            "session_id": previous.get("session_id", previous.get("id")),
            "state": previous.get("state"),
            "detail_omitted": "Office snapshot budget: older preview omitted; operator forensics inspect/evidence retains the record.",
        }
    return result
