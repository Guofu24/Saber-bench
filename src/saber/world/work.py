"""Durable work ownership, private notes and explicit actor lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from saber.agents.specialties import BLUE_SKILLS
from saber.world.operations import Arguments, evidence, save_case

if TYPE_CHECKING:
    from saber.world.environment import World
    from saber.world.models import Action, Actor

HELP = {
    "wait": "Pause your actions for a bounded number of ticks, without scripted fallback. args: ticks (1..10000), reason.",
    "finish": "Finish your current actor mission; stop planning and actions until explicitly resumed. args: reason. Finish/block active tasks first.",
    "write_note": "Append to your private durable notebook. args: kind (observation/hypothesis/decision/next_step), text (max 2000), evidence_ids (optional). Not visible to other actors.",
    "read_notes": "Page your own notebook. args: after=0, limit=10 (max 20).",
    "create_task": "Lead offers a case task to a qualified teammate. args: case_id, assignee, specialty, objective, deadline_tick (optional). Same open objective is deduplicated.",
    "accept_task": "Acknowledge an offered task assigned to you; one active task at a time. args: task_id, expected_revision.",
    "complete_task": "Submit task result with attached case evidence. args: task_id, expected_revision, note, evidence_ids. A result is an analyst claim, not independent verification.",
    "block_task": "Report missing data/tool or other blocker. args: task_id, expected_revision, note.",
    "handoff_task": "Offer your active/blocked task to a qualified teammate. args: task_id, expected_revision, assignee, note, evidence_ids (optional). Receiver must accept.",
    "cancel_task": "Lead cancels outstanding work with a reason. args: task_id, expected_revision, note.",
    "list_tasks": "List task records, optionally by assignee/status. args: after=0, limit=20 (max 50), assignee/status optional.",
    "resume_actor": "Lead resumes a blue teammate and invalidates old plans. args: actor_id, reason. Cannot control clients/red.",
}
PERSONAL_TOOLS = frozenset({"wait", "finish", "write_note", "read_notes"})
WORKER_TOOLS = frozenset(
    {"accept_task", "complete_task", "block_task", "handoff_task", "list_tasks"}
)
LEAD_TOOLS = frozenset({"create_task", "cancel_task", "resume_actor"})


class Rest(Arguments):
    ticks: int = Field(default=1, ge=1, le=10000)
    reason: str = Field(min_length=1, max_length=500)


class Note(Arguments):
    kind: Literal["observation", "hypothesis", "decision", "next_step"]
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[int] = Field(default_factory=list, max_length=20)


class Page(Arguments):
    after: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=20)


class TasksPage(Arguments):
    after: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)
    assignee: str | None = None
    status: Literal["OFFERED", "ACTIVE", "BLOCKED", "DONE", "CANCELLED"] | None = None


class Offer(Arguments):
    case_id: str
    assignee: str
    specialty: str
    objective: str = Field(min_length=1, max_length=1000)
    deadline_tick: int | None = Field(default=None, ge=0)


class TaskRef(Arguments):
    task_id: str
    expected_revision: int = Field(ge=0)


class TaskChange(TaskRef):
    note: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[int] = Field(default_factory=list, max_length=50)
    assignee: str | None = None


class Resume(Arguments):
    actor_id: str
    reason: str = Field(min_length=1, max_length=500)


def control(world: World, actor_id: str) -> dict[str, Any]:
    return dict(world.store.get("actor-control", actor_id, {"status": "ACTIVE", "generation": 0}))


def set_control(world: World, actor_id: str, status: str, reason: str, until: int = 0) -> None:
    old = control(world, actor_id)
    world.store.put(
        "actor-control",
        actor_id,
        {
            "status": status,
            "reason": reason,
            "until_tick": until,
            "generation": old["generation"] + 1,
            "updated_tick": world.tick,
        },
    )
    world.store.put("plans", actor_id, [])
    memory = world.store.get("memory", actor_id, {})
    memory["next_plan"] = world.tick
    world.store.put("memory", actor_id, memory)


def qualified(world: World, assignee: str, specialty: str) -> None:
    from saber.world.models import specialties_for

    if assignee not in world.actors or specialty not in BLUE_SKILLS:
        raise ValueError("unknown teammate/specialty")
    if specialty not in specialties_for(world.actors[assignee]):
        raise ValueError("teammate does not have this specialty")


def execute(world: World, actor: Actor, action: Action) -> tuple[int, dict[str, Any], str]:
    tool, raw = action.tool, action.args
    if control(world, actor.id)["status"] == "DONE" and tool not in {"read_notes", "list_tasks"}:
        return 409, {"error": "Actor mission finished; explicit resume required."}, actor.id
    tasks = world.store.items("tasks")
    if tool in {"wait", "finish"}:
        rest = Rest.model_validate(raw)
        if tool == "finish" and any(
            t["assignee"] == actor.id and t["status"] == "ACTIVE" for t in tasks.values()
        ):
            return 409, {"error": "Complete, hand off or block active work first."}, actor.id
        set_control(
            world,
            actor.id,
            "WAITING" if tool == "wait" else "DONE",
            rest.reason,
            world.tick + rest.ticks,
        )
        return 200, {"control": control(world, actor.id)}, actor.id
    if tool == "write_note":
        note = Note.model_validate(raw)
        cited = evidence(world, note.evidence_ids, world.tick) if note.evidence_ids else []
        if actor.team != "blue" and any(
            e["principal"] != world.principals[actor.id] for e in cited
        ):
            raise ValueError("cannot cite another principal's private history")
        notes = world.store.get("notebook", actor.id, [])
        if len(notes) >= 200:
            return (
                409,
                {"error": "Notebook limit reached; preserve results in assigned case work."},
                actor.id,
            )
        notes.append(note.model_dump() | {"seq": len(notes) + 1, "tick": world.tick})
        world.store.put("notebook", actor.id, notes)
        return 201, {"sequence": len(notes)}, actor.id
    if tool == "read_notes":
        page = Page.model_validate(raw)
        notes = [n for n in world.store.get("notebook", actor.id, []) if n["seq"] > page.after]
        found = notes[: page.limit]
        return (
            200,
            {
                "notes": found,
                "has_more": len(notes) > page.limit,
                "next_after": found[-1]["seq"] if found else page.after,
            },
            actor.id,
        )
    if tool == "resume_actor":
        resume = Resume.model_validate(raw)
        target = world.actors.get(resume.actor_id)
        if target is None or target.team != "blue":
            raise ValueError("only a blue teammate can be resumed by lead")
        set_control(world, target.id, "ACTIVE", resume.reason)
        return 200, {"message": "Teammate resumed."}, target.id
    if tool == "list_tasks":
        listing = TasksPage.model_validate(raw)
        found = [
            t
            for t in tasks.values()
            if t["sequence"] > listing.after
            and (listing.assignee is None or t["assignee"] == listing.assignee)
            and (listing.status is None or t["status"] == listing.status)
        ]
        found.sort(key=lambda t: t["sequence"])
        page_tasks = found[: listing.limit]
        return (
            200,
            {
                "tasks": page_tasks,
                "has_more": len(found) > listing.limit,
                "next_after": page_tasks[-1]["sequence"] if page_tasks else listing.after,
            },
            "tasks",
        )
    if tool == "create_task":
        offer = Offer.model_validate(raw)
        case = world._case({"case_id": offer.case_id})
        qualified(world, offer.assignee, offer.specialty)
        if case["status"] == "CLOSED" or (
            offer.deadline_tick is not None and offer.deadline_tick < world.tick
        ):
            raise ValueError("closed case or past deadline")
        for task in tasks.values():
            if (task["case_id"], task["specialty"], task["objective"]) == (
                offer.case_id,
                offer.specialty,
                offer.objective,
            ) and task["status"] not in {"DONE", "CANCELLED"}:
                return 200, {"task": task, "message": "Existing task."}, task["id"]
        if sum(t["status"] in {"OFFERED", "ACTIVE", "BLOCKED"} for t in tasks.values()) >= 500:
            raise ValueError("open task limit reached")
        sequence = len(tasks) + 1
        task = offer.model_dump() | {
            "id": f"task-{sequence:06d}",
            "sequence": sequence,
            "status": "OFFERED",
            "revision": 0,
            "created_by": actor.id,
            "created_tick": world.tick,
            "history": [],
            "result": None,
        }
        world.store.put("tasks", task["id"], task)
        save_case(
            world, case, actor, f"Offered {task['id']} to {offer.assignee} ({offer.specialty})."
        )
        return 201, {"task": task}, task["id"]
    change = (TaskRef if tool == "accept_task" else TaskChange).model_validate(raw)
    task = tasks.get(change.task_id)
    if task is None or task["revision"] != change.expected_revision:
        raise ValueError("unknown task or stale revision")
    if tool != "cancel_task" and task["assignee"] != actor.id:
        return 403, {"error": "Task belongs to another actor."}, task["id"]
    if task["status"] in {"DONE", "CANCELLED"}:
        raise ValueError("task is already finished")
    old_owner = task["assignee"]
    case = world._case({"case_id": task["case_id"]})
    if case["status"] == "CLOSED":
        raise ValueError("case must be reopened")
    note_text = "Task accepted."
    if tool == "accept_task":
        if task["status"] != "OFFERED" or any(
            t["assignee"] == actor.id and t["status"] == "ACTIVE" for t in tasks.values()
        ):
            return 409, {"error": "Only one active task; accept an offered task."}, task["id"]
        task["status"] = "ACTIVE"
        set_control(world, actor.id, "ACTIVE", "Accepted task.")
    else:
        assert isinstance(change, TaskChange)
        note_text = change.note
        if not set(change.evidence_ids) <= set(case["evidence_ids"]):
            raise ValueError("task citations must be attached to case")
        if change.evidence_ids:
            evidence(world, change.evidence_ids, world.tick)
        if tool == "complete_task":
            if task["status"] != "ACTIVE" or not change.evidence_ids:
                raise ValueError("active task and cited result required")
            task["status"] = "DONE"
            task["result"] = {
                "note": change.note,
                "evidence_ids": change.evidence_ids,
                "by": actor.id,
                "tick": world.tick,
            }
        elif tool == "block_task":
            task["status"] = "BLOCKED"
        elif tool == "handoff_task":
            if (
                task["status"] not in {"ACTIVE", "BLOCKED"}
                or change.assignee is None
                or change.assignee == actor.id
            ):
                raise ValueError("active/blocked task and different assignee required")
            qualified(world, change.assignee, task["specialty"])
            task["assignee"] = change.assignee
            task["status"] = "OFFERED"
        elif tool == "cancel_task":
            task["status"] = "CANCELLED"
        else:
            raise ValueError("unknown work action")
        # A changed assignment/completion invalidates any in-flight plans for the old owner.
        old_control = control(world, old_owner)
        set_control(
            world,
            old_owner,
            old_control["status"],
            "Task state changed.",
            old_control.get("until_tick", 0),
        )
    task["revision"] += 1
    task["history"].append(
        {
            "by": actor.id,
            "tick": world.tick,
            "action": tool,
            "note": note_text,
            "assignee": task["assignee"],
            "revision": task["revision"],
        }
    )
    world.store.put("tasks", task["id"], task)
    save_case(world, case, actor, f"{tool} {task['id']}: {note_text}")
    return 200, {"task": task}, task["id"]
