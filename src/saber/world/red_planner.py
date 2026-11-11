"""Adaptive red planner: a belief state over observations drives a multi-step,
feedback-driven campaign using only inert allowlisted tools.

Deterministic given the world seed and tick order — no randomness — so episodes
replay exactly. The planner reads ONLY the actor's own observation (own principal,
own event history, own team channel); it never touches hidden world state, blue
decisions, the private evaluator, sealed truth or another team's plan. Objective
completion is judged from the actor's OWN server-confirmed events (an exfil 201,
a disrupt 202), never from the planner's intent: a plan is a hypothesis, the
recorded effect is the only proof.

This is a deterministic RULE-BASED adaptive planner: a fixed per-role decision
procedure that reacts to observed feedback (login, discovery, containment, outage,
control denial, budget). It is not learned, search-based or strategic planning, and
nothing here should be described as autonomous strategic reasoning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from saber.world.models import Action, Actor

# Bounded action budget per red actor; on exhaustion the actor finishes cleanly
# instead of hammering the service. Objectives normally complete in well under this.
RED_BUDGET = 60

OBJECTIVES = {
    "recon": "Enumerate reachable documents and hand the map to the access role.",
    "access": "Read, stage and exfiltrate one unauthorized document to the lab sink.",
    "impact": "Register one unauthorized automation job and cause a bounded outage.",
}


def _a(tool: str, **args: Any) -> Action:
    return Action(tool=tool, args=args)


@dataclass(frozen=True)
class RedBelief:
    """Everything the red actor can legitimately infer from its own observations."""

    principal: str
    own_doc: str
    logged_in: bool
    blocked: bool
    contained: bool
    last_tool: str
    service_down: bool
    known_docs: tuple[str, ...]
    read_foreign: frozenset[str]
    denied: frozenset[str]
    collected: frozenset[str]
    exfiltrated: frozenset[str]
    jobs_registered: int
    disrupted: bool
    shared_map: bool

    def foreign_candidates(self) -> list[str]:
        # Other users' work documents the actor has learned exist, newest-stable order.
        return sorted(d for d in self.known_docs if d.startswith("work-") and d != self.own_doc)


def _parse_links(text: str) -> list[str]:
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return []
    links = parsed.get("document_links") if isinstance(parsed, dict) else None
    return [x for x in links if isinstance(x, str)] if isinstance(links, list) else []


def observe_belief(actor: Actor, obs: dict[str, Any]) -> RedBelief:
    principal = str(obs.get("principal", ""))
    own_doc = f"work-{principal}"
    last = obs.get("last_result", {})
    events = obs.get("events", [])

    known: set[str] = set()
    read_foreign: set[str] = set()
    denied: set[str] = set()
    collected: set[str] = set()
    exfiltrated: set[str] = set()
    jobs = 0
    disrupted = False
    for link in last.get("links", []) or []:
        if isinstance(link, dict) and isinstance(link.get("id"), str):
            known.add(link["id"])
    for msg in obs.get("team_messages", []):
        known.update(_parse_links(str(msg.get("text", ""))))
    for e in events:
        tool, target, status = e.get("tool"), e.get("target", ""), e.get("status", 0)
        owner = (e.get("detail") or {}).get("owner")
        if tool == "read_document" and status == 200:
            known.add(target)
            if owner not in (None, "public", principal):
                read_foreign.add(target)
        elif tool == "read_document" and status == 403:
            # A control denied this specific document. Remember it so the actor tries a
            # different document rather than hammering the same denied one.
            known.add(target)
            denied.add(target)
        elif tool == "collect" and status == 201:
            collected.add(target)
        elif tool == "exfiltrate" and status == 201:
            exfiltrated.add(target)
        elif tool == "register_job" and status == 201:
            jobs += 1
        elif tool == "disrupt" and status == 202:
            disrupted = True

    shared_map = any(
        msg.get("sender") == actor.id and _parse_links(str(msg.get("text", "")))
        for msg in obs.get("team_messages", [])
    )
    return RedBelief(
        principal=principal,
        own_doc=own_doc,
        logged_in=bool(obs.get("logged_in")),
        # A 403 means a defender control denied this action. A session containment
        # ("restricted") blocks every path; a specific control (an enforced ACL) blocks
        # only the denied leg, so the role planner may still have an alternative.
        blocked=last.get("status") == 403,
        contained=last.get("status") == 403 and "restricted" in str(last.get("error", "")).lower(),
        last_tool=str(last.get("tool", "")),
        service_down=last.get("status") == 503,
        known_docs=tuple(sorted(known)),
        read_foreign=frozenset(read_foreign),
        denied=frozenset(denied),
        collected=frozenset(collected),
        exfiltrated=frozenset(exfiltrated),
        jobs_registered=jobs,
        disrupted=disrupted,
        shared_map=shared_map,
    )


def objective_complete(role: str, b: RedBelief) -> bool:
    if role == "recon":
        # Recon's deliverable is the shared document map; reading is the access role's job.
        return b.shared_map
    if role == "access":
        return bool(b.exfiltrated)
    if role == "impact":
        return b.jobs_registered >= 1 and b.disrupted
    return False


def plan_action(actor: Actor, obs: dict[str, Any], turn: int) -> Action:
    """Return the next inert action for a red actor, adapting to real feedback."""
    b = observe_belief(actor, obs)
    role = actor.role

    # Stop conditions: a verified objective or an exhausted budget ends the mission.
    budget = int(obs.get("budget", RED_BUDGET))
    if objective_complete(role, b):
        return _a("finish", reason=f"{role} objective verified by own effects.")
    if turn >= budget:
        return _a("finish", reason="Action budget exhausted; ending campaign.")

    if not b.logged_in:
        return _a("login")
    # A full session containment blocks every tool, so no path remains — stop. A
    # specific control denial is left to the role planner, which may try another leg.
    if b.contained:
        return _a("finish", reason="Session contained by the defender; all paths blocked.")
    # A bounded outage is transient; wait rather than retry blindly against 503.
    if b.service_down and role != "impact":
        return _a("wait", ticks=2, reason="Service unavailable; retry after the outage.")

    if role == "recon":
        return _recon(b)
    if role == "impact":
        return _impact(b)
    return _access(b, turn)


def _recon(b: RedBelief) -> Action:
    # Enumerate the document map, then hand it to the access role once (objective done).
    if b.known_docs and not b.shared_map:
        return _a("share", text=json.dumps({"document_links": sorted(b.known_docs)})[:1000])
    return _a("browse")


def _access(b: RedBelief, turn: int) -> Action:
    # Advance the kill chain on whatever is already staged first: exfiltrate > collect.
    to_exfil = sorted(b.collected - b.exfiltrated)
    if to_exfil:
        return _a("exfiltrate", document=to_exfil[0])
    to_collect = sorted(b.read_foreign - b.collected)
    if to_collect:
        return _a("collect", document=to_collect[0])
    # Read a foreign document that is neither read nor already denied. A per-document
    # control (a restricted asset) blocks only its own leg, so a different document is a
    # genuine alternative path -- unlike a full session containment, handled upstream.
    candidates = [
        d for d in b.foreign_candidates() if d not in b.read_foreign and d not in b.denied
    ]
    if candidates:
        return _a("read_document", document=candidates[0])
    foreign = b.foreign_candidates()
    if foreign and all(d in b.denied for d in foreign):
        # Every document currently in view is access-controlled. Re-enumerate once in
        # case an alternative exists that is not in the latest observation; only if a
        # fresh browse still surfaces no open document is the read path truly blocked.
        if b.last_tool != "browse":
            return _a("browse")
        return _a(
            "finish", reason="Every discovered document is access-controlled; no read path remains."
        )
    if b.blocked and not foreign:
        return _a("finish", reason="Authorization control blocks the read path; stopping.")
    # No foreign target learned yet (or only our own): enumerate to discover documents.
    return _a("browse")


def _impact(b: RedBelief) -> Action:
    # Persistence before disruption, so the job registers before the service drops.
    # If an enforced job ACL denies registration, disruption is a separate path that
    # is still worth attempting rather than ending the campaign prematurely.
    register_denied = b.blocked and b.last_tool == "register_job"
    disrupt_denied = b.blocked and b.last_tool == "disrupt"
    if b.jobs_registered == 0 and not register_denied:
        return _a("register_job", name=f"sync-{b.principal}")
    if not b.disrupted and not disrupt_denied:
        return _a("disrupt")
    return _a("finish", reason="Impact objectives met or remaining paths blocked; stopping.")
