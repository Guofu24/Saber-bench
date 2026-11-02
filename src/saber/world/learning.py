"""Private experience journals and immutable, world-local skill releases.

This module never reads evaluator labels or writes repository skills. Generated
lessons are advisory extensions; the HTTP capability remains the authority.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from saber.agents.skills import MAX_WORLD_CHARS
from saber.agents.specialties import BLUE_SKILLS

if TYPE_CHECKING:
    from saber.world.environment import World
    from saber.world.models import Actor
    from saber.world.store import Store


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def actor_skill(world: World, actor: Actor) -> str:
    if actor.team == "client":
        return "client-user"
    if actor.team == "red":
        return "redteam-post-exploitation" if actor.role == "impact" else "redteam-initial-access"
    specialty = next(
        (
            t["specialty"]
            for t in world.store.items("tasks").values()
            if t["assignee"] == actor.id and t["status"] == "ACTIVE"
        ),
        actor.role,
    )
    return BLUE_SKILLS[specialty]


class Lesson(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    failure_kind: Literal[
        "reasoning", "tool_contract", "environment", "insufficient_evidence", "unknown"
    ]
    applicability: str = Field(min_length=10, max_length=400)
    guidance: str = Field(min_length=10, max_length=1000)
    evidence_ids: list[int] = Field(min_length=1, max_length=20)
    limitations: str = Field(min_length=5, max_length=500)


def initialize(world: World, playbooks: dict[str, str]) -> None:
    """Keep the original base even when checkout files change across a restart."""
    with world.store.transaction():
        for skill, base in playbooks.items():
            if world.store.get("skill-heads", skill) is not None:
                continue
            version: dict[str, Any] = {"skill": skill, "base": base, "lessons": [], "parent": None}
            vid = digest(version)
            world.store.put("skill-versions", vid, version | {"id": vid})
            world.store.put("skill-heads", skill, vid)
        activate(world)


def quiescent(world: World) -> bool:
    return not any(
        c["status"] != "CLOSED" for c in world.store.items("cases").values()
    ) and not any(
        t["status"] in {"OFFERED", "ACTIVE", "BLOCKED"} for t in world.store.items("tasks").values()
    )


def activate(world: World) -> bool:
    """One atomic epoch for the shared world, never a mid-case skill replacement."""
    old = world.store.get("learning-meta", "epoch")
    if old and (not quiescent(world) or world.tick < old["next_tick"]):
        return False
    heads = world.store.items("skill-heads")
    if old and old["versions"] != heads:
        from saber.world.work import control, set_control

        for actor in world.config.actors:
            current = control(world, actor.id)
            set_control(
                world,
                actor.id,
                current["status"],
                "Skill epoch changed.",
                current.get("until_tick", 0),
            )
    world.store.put(
        "learning-meta",
        "epoch",
        {
            "versions": heads,
            "tick": world.tick,
            "next_tick": world.tick + world.config.learning_interval_ticks,
        },
    )
    return True


def version(store: Store, vid: str) -> dict[str, Any]:
    row = store.get("skill-versions", vid)
    if (
        row is None
        or row.get("id") != vid
        or digest({k: v for k, v in row.items() if k != "id"}) != vid
    ):
        raise ValueError("Unknown or corrupt skill version")
    return dict(row)


def prompt_version(store: Store, skill: str) -> dict[str, Any] | None:
    epoch = store.get("learning-meta", "epoch", {})
    vid = epoch.get("versions", {}).get(skill)
    return version(store, vid) if vid else None


def candidate_version(base: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    # Duplicate ideas do not grow the prompt indefinitely.
    lesson = {k: proposal["lesson"][k] for k in ("applicability", "guidance", "limitations")}
    lessons = list(base["lessons"])
    if lesson in lessons:
        raise ValueError("Duplicate lesson")
    lessons.append(lesson)
    if (
        len(lessons) > 8
        or len(base["base"]) + len(json.dumps(lessons, ensure_ascii=False)) > MAX_WORLD_CHARS
    ):
        raise ValueError("Skill lesson/context limit reached; curate before adding more")
    result = {
        "skill": base["skill"],
        "base": base["base"],
        "lessons": lessons,
        "parent": base["id"],
    }
    return result | {"id": digest(result)}


def seal(world: World, actor: Actor, reason: str) -> str | None:
    current = world.store.get("learning-journal", actor.id, [])
    if not current:
        return None
    counters = world.store.get("learning-counts", actor.id, {"episodes": 0, "saturated": 0})
    # Keep bounded pending work. Original application logs still follow normal retention.
    pending = sum(e["status"] == "PENDING" for e in world.store.items("learning-episodes").values())
    if pending >= 200:
        counters["saturated"] += 1
        world.store.put("learning-counts", actor.id, counters)
        return None
    counters["episodes"] += 1
    eid = f"{actor.id}-{counters['episodes']:08d}"
    errors = sum(r["status"] >= 400 for r in current)
    episode = {
        "id": eid,
        "actor_id": actor.id,
        "team": actor.team,
        "skill": current[-1]["skill"],
        "version": current[-1]["version"],
        "through_tick": world.tick,
        "reason": reason,
        "records": current,
        "notes": world.store.get("notebook", actor.id, [])[-5:],
        "summary": {
            "actions": len(current),
            "http_errors": errors,
            "status_counts": dict(Counter(str(r["status"]) for r in current)),
        },
        "status": "PENDING"
        if errors or reason in {"complete_task", "block_task", "finish", "close_case"}
        else "RECORDED",
        "attempts": 0,
    }
    world.store.put("learning-episodes", eid, episode)
    world.store.put("learning-journal", actor.id, [])
    world.store.put("learning-counts", actor.id, counters)
    return eid


def capture(world: World, actor: Actor, result: dict[str, Any], target: str, skill: str) -> None:
    if not world.config.learning_enabled:
        return
    pin = prompt_version(world.store, skill)
    records = world.store.get("learning-journal", actor.id, [])
    if records and (
        records[-1]["skill"] != skill or records[-1]["version"] != (pin or {}).get("id")
    ):
        seal(world, actor, "specialty_change")
        records = world.store.get("learning-journal", actor.id, [])
    if len(records) >= 50:
        # Explicit backpressure: never overwrite an unsealed experience.
        seal(world, actor, "capacity")
        records = world.store.get("learning-journal", actor.id, [])
        if len(records) >= 50:
            return
    # Only this actor's observable result, never plan text, another actor's notes,
    # document bodies, raw model errors, credentials or evaluator effects.
    records.append(
        {
            "event_id": result["event_id"],
            "tick": world.tick,
            "tool": result["tool"],
            "status": result["status"],
            "target": target,
            "message": str(result.get("error", result.get("message", "")))[:200],
            "skill": skill,
            "version": (pin or {}).get("id"),
        }
    )
    world.store.put("learning-journal", actor.id, records)
    if result["status"] < 400 and result["tool"] in {
        "complete_task",
        "block_task",
        "finish",
        "close_case",
    }:
        seal(world, actor, result["tool"])
    elif (
        world.tick - records[0]["tick"] >= world.config.learning_interval_ticks
        or len(records) >= 50
    ):
        seal(world, actor, "interval")


def propose(world: World, actor: Actor, episode_id: str, raw: Any) -> dict[str, Any]:
    episode = world.store.get("learning-episodes", episode_id)
    if not episode or episode["actor_id"] != actor.id:
        raise ValueError("Episode is not owned by this actor")
    lesson = Lesson.model_validate(raw)
    ids = {r["event_id"] for r in episode["records"]}
    if not set(lesson.evidence_ids) <= ids or any(type(i) is not int for i in lesson.evidence_ids):
        raise ValueError("Citations must belong to this episode")
    if not episode["version"]:
        raise ValueError("Episode has no pinned skill version")
    value = {
        "actor_id": actor.id,
        "team": actor.team,
        "skill": episode["skill"],
        "base_version": episode["version"],
        "episode_id": episode_id,
        "lesson": lesson.model_dump(),
    }
    pid = digest(value)
    existing = world.store.get("learning-proposals", pid)
    if existing:
        return dict(existing)
    candidate_version(version(world.store, value["base_version"]), value)
    proposal = value | {"id": pid, "status": "AWAITING_SUITE", "created_tick": world.tick}
    world.store.put("learning-proposals", pid, proposal)
    return proposal


def summary(store: Store, actor_id: str | None = None) -> dict[str, Any]:
    episodes = [
        e
        for e in store.items("learning-episodes").values()
        if actor_id is None or e["actor_id"] == actor_id
    ]
    proposals = [
        p
        for p in store.items("learning-proposals").values()
        if actor_id is None or p["actor_id"] == actor_id
    ]
    return {
        "episodes": dict(Counter(e["status"] for e in episodes)),
        "proposals": dict(Counter(p["status"] for p in proposals)),
        "scope": "development learning; not benchmark readiness",
    }
