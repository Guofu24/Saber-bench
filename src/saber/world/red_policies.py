"""Red policies for scenario evaluation.

All three emit only inert, allowlisted actions through the same validated world
interface, and all read only the actor's own observation -- never hidden state,
blue decisions or evaluator data. They exist to separate scenario feasibility from
red competence: given an identical feasible scenario, a capable policy reaches the
verified objective and a weak one does not.
"""

from __future__ import annotations

import hashlib
from typing import Any

from saber.world import red_planner
from saber.world.models import Action, Actor

_RANDOM_TOOLS = (
    "browse",
    "search",
    "login",
    "read_document",
    "collect",
    "exfiltrate",
    "register_job",
    "disrupt",
    "share",
)


def adaptive(actor: Actor, obs: dict[str, Any], turn: int) -> Action:
    """The deterministic rule-based adaptive planner (belief state + feedback)."""
    return red_planner.plan_action(actor, obs, turn)


def naive_greedy(actor: Actor, obs: dict[str, Any], turn: int) -> Action:
    """No belief or discovery: go through the motions against public data.

    For access it reads/collects/exfiltrates the public welcome document, which is
    authorized, so the server records no exfiltrated bytes and the security
    objective is never verified. For impact a single disruption already suffices.
    """
    if not obs.get("logged_in"):
        return Action(tool="login")
    if actor.role == "impact":
        return Action(tool="disrupt")
    if actor.role == "recon":
        return Action(tool="browse")
    events = obs.get("events", [])
    read = any(e["tool"] == "read_document" and e["target"] == "welcome" for e in events)
    collected = any(e["tool"] == "collect" and e["target"] == "welcome" for e in events)
    if not read:
        return Action(tool="read_document", args={"document": "welcome"})
    if not collected:
        return Action(tool="collect", args={"document": "welcome"})
    return Action(tool="exfiltrate", args={"document": "welcome"})


def _random_args(tool: str, obs: dict[str, Any]) -> dict[str, Any]:
    if tool in ("read_document", "collect", "exfiltrate"):
        return {"document": "welcome"}
    if tool == "search":
        return {"query": "work"}
    if tool == "register_job":
        return {"name": f"job-{obs.get('principal', 'x')}"}
    if tool == "share":
        return {"text": "status"}
    return {}


def random_valid(actor: Actor, obs: dict[str, Any], turn: int) -> Action:
    """Pick a permitted action deterministically by (actor, turn); rarely completes a chain."""
    digest = hashlib.sha256(f"{actor.id}:{turn}".encode()).hexdigest()
    tool = _RANDOM_TOOLS[int(digest, 16) % len(_RANDOM_TOOLS)]
    return Action(tool=tool, args=_random_args(tool, obs))


POLICIES = {"adaptive": adaptive, "naive": naive_greedy, "random": random_valid}
