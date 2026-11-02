"""Small operator-only snapshots; no prompts, documents, credentials or private plans."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saber.world.models import WorldConfig
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
        for actor in config.actors:
            memory = store.get("memory", actor.id, {})
            roster.append(
                {
                    "id": actor.id,
                    "team": actor.team,
                    "role": actor.role,
                    "activity": "idle"
                    if stopped
                    else "planning"
                    if actor.id in pending
                    else "idle",
                    "turns": memory.get("turns", 0),
                    "last_tick": memory.get("last_tick"),
                    "last_tool": memory.get("last_tool"),
                    "last_status": memory.get("last_status"),
                    "source": memory.get("source", "none"),
                }
            )
    return {
        "type": "world_snapshot",
        "schema_version": 1,
        "world_id": report["world_id"],
        "run_id": run_id,
        "profile": profile,
        "engine": report["engine"],
        "status": "stopped" if stopped else "running",
        "updated_at": time.time(),
        "tick_seconds": config.tick_seconds,
        "tick": report["tick"],
        "actors": roster,
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
