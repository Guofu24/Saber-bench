"""Operator-owned, bounded decision replay. Expected answers never enter model prompts.

Passing proves the submitted next-action checks only, not full incident resolution
or generalization. A replay suite cannot execute shell commands or mutate a lab.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saber.agents.skills import RUNTIME_SKILLS
from saber.agents.specialties import BLUE_SKILLS
from saber.baselines.prompt import extract_answer_json
from saber.world import learning
from saber.world.agents import llm_messages
from saber.world.models import Action, Actor, tools_for
from saber.world.store import Store


class ReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    split: Literal["repair", "regression"]
    observation: dict[str, Any]
    expected: list[Action] = Field(min_length=1, max_length=4)


class ReplaySuite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill: str
    description: str = Field(min_length=10, max_length=500)
    repetitions: int = Field(default=2, ge=2, le=3)
    cases: list[ReplayCase] = Field(min_length=3, max_length=12)

    @model_validator(mode="after")
    def valid_cases(self) -> ReplaySuite:
        if self.skill not in RUNTIME_SKILLS:
            raise ValueError("Unknown runtime skill")
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("Duplicate replay case ids")
        if len({learning.digest(c.observation) for c in self.cases}) != len(self.cases):
            raise ValueError("Replay observations must be distinct")
        if (
            not any(c.split == "repair" for c in self.cases)
            or sum(c.split == "regression" for c in self.cases) < 2
        ):
            raise ValueError("Require a repair case and at least two distinct regression cases")
        if any(len(json.dumps(c.observation)) > 16000 for c in self.cases):
            raise ValueError("Replay observation too large")
        return self


def install_suite(store: Store, raw: Any) -> str:
    suite = ReplaySuite.model_validate(raw)
    data = suite.model_dump(mode="json")
    sid = learning.digest(data)
    with store.transaction():
        store.put("learning-suites", sid, data)
        store.put("learning-suite-heads", suite.skill, sid)
    return sid


def replay_messages(actor: Actor, case: ReplayCase, pin: dict[str, Any]) -> list[dict[str, Any]]:
    # Replace any tool menu in the fixture with the actual actor capability.
    from saber.world.environment import TOOL_HELP

    obs = dict(case.observation)
    if actor.team == "blue":
        obs["active_specialty"] = next(
            r for r, skill in BLUE_SKILLS.items() if skill == pin["skill"]
        )
    obs["tools"] = {t: TOOL_HELP[t] for t in sorted(tools_for(actor))}
    messages = llm_messages(actor, obs, pinned=pin)
    messages[0]["content"] += " For this decision replay, return exactly ONE immediate next action."
    return messages


def matches_response(actor: Actor, case: ReplayCase, text: str) -> bool:
    # Do not use parse_plan's fallback/filtering: an invalid/disallowed extra action
    # must fail evaluation, not disappear and make a malicious plan look correct.
    try:
        obj, _ = extract_answer_json(text)
        if (
            not isinstance(obj, dict)
            or not isinstance(obj.get("actions"), list)
            or len(obj["actions"]) != 1
        ):
            return False
        chosen = Action.model_validate(obj["actions"][0])
        return chosen.tool in tools_for(actor) and any(
            chosen == expected for expected in case.expected
        )
    except (ValueError, TypeError):
        return False


def publish(store: Store, proposal_id: str, report: dict[str, Any]) -> str | None:
    """Called only by the evaluator, not available in an actor tool menu."""
    with store.transaction():
        proposal = store.get("learning-proposals", proposal_id)
        if proposal is None or proposal["status"] != "AWAITING_SUITE":
            raise ValueError("Proposal is not pending evaluation")
        if (
            report["proposal_id"] != proposal_id
            or report["base_version"] != proposal["base_version"]
        ):
            raise ValueError("Evaluation does not match proposal")
        suite_id = store.get("learning-suite-heads", proposal["skill"])
        if suite_id != report["suite_id"]:
            raise ValueError("Evaluation suite changed")
        base = learning.version(store, proposal["base_version"])
        candidate = learning.candidate_version(base, proposal)
        if candidate["id"] != report["candidate_version"]:
            raise ValueError("Candidate changed since evaluation")
        rows = report["checks"]
        suite = ReplaySuite.model_validate(store.get("learning-suites", suite_id))
        required = {(c.id, repeat) for c in suite.cases for repeat in range(suite.repetitions)}
        complete = (
            len(rows) == len(required) and {(r["case_id"], r["repeat"]) for r in rows} == required
        )
        repair_ids = {c.id for c in suite.cases if c.split == "repair"}
        passed = (
            complete
            and all(r["candidate_ok"] is True for r in rows)
            and any(r["case_id"] in repair_ids and r["base_ok"] is False for r in rows)
        )
        status = "PUBLISHED" if passed else "REJECTED"
        if store.get("skill-heads", proposal["skill"]) != base["id"]:
            status = "STALE"
        report = report | {"status": status, "passed": passed and status == "PUBLISHED"}
        rid = learning.digest(report)
        store.put("learning-evaluations", rid, report)
        proposal.update(status=status, evaluation_id=rid)
        if status == "PUBLISHED":
            store.put("skill-versions", candidate["id"], candidate)
            store.put("skill-heads", proposal["skill"], candidate["id"])
            proposal["published_version"] = candidate["id"]
            # An immutable release receipt is kept even if the head is rolled back.
            store.put(
                "skill-releases", candidate["id"], {"proposal": proposal_id, "evaluation": rid}
            )
        store.put("learning-proposals", proposal_id, proposal)
        return candidate["id"] if status == "PUBLISHED" else None


def rollback(store: Store, skill: str, target: str) -> None:
    with store.transaction():
        old = learning.version(store, target)
        if old["skill"] != skill:
            raise ValueError("Version belongs to another skill")
        if old["parent"] is not None and store.get("skill-releases", target) is None:
            raise ValueError("Target was never released")
        current = store.get("skill-heads", skill)
        store.put("skill-heads", skill, target)
        entry = {
            "skill": skill,
            "from": current,
            "to": target,
            "sequence": len(store.items("skill-rollbacks")) + 1,
        }
        store.put("skill-rollbacks", str(entry["sequence"]), entry)
