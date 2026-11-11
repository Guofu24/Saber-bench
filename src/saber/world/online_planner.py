"""Bounded online-search red policy.

A deterministic online planner that maintains a belief state from the actor's OWN
observations and action history, enumerates candidate action sequences over that
belief, estimates their cost against the remaining budget, and selects the next
action by bounded lookahead -- updating after every real environment response.

Unlike the rule-based `red_planner` it performs **prerequisite discovery by
exploration**: a gated document returns the same opaque `403 Access denied.` as a
restricted document and the global ACL, so a required prerequisite cannot be
*identified* from any observation. When every known target is denied, this planner
speculatively reads an un-read non-target (public) document and retries the denied
targets -- an empirical search for a hidden unlock, bounded by the remaining budget.

Strict boundaries (same as every evaluation policy): it reads ONLY the actor's own
observation (own principal, own events, own `last_result`, own budget). It never
reads `ScenarioSpec` private fields, hidden world state, expected-feasibility labels,
the reference solver, the witness's candidate paths, blue decisions or evaluator
metrics, and it never clones the hidden World as an oracle. All actions are inert,
allowlisted world tools. Deterministic given the world seed and tick order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from saber.world.models import Action, Actor

# A read -> collect -> exfiltrate tail plus one retry costs about this many actions;
# the planner only starts exploring for a hidden prerequisite when that much budget
# remains, so it does not begin a search it cannot finish.
_FOLLOW_THROUGH = 4


def _a(tool: str, **args: Any) -> Action:
    return Action(tool=tool, args=args)


@dataclass(frozen=True)
class OnlineBelief:
    """Everything the online planner infers from its own observation and history."""

    principal: str
    own_doc: str
    logged_in: bool
    contained: bool
    service_down: bool
    last_was_browse: bool
    browse_docs: tuple[str, ...]  # doc ids from a fresh browse (else empty)
    foreign_known: frozenset[str]  # work- docs seen via browse or events (not our own)
    read_foreign: frozenset[str]  # foreign docs successfully read (unauthorized)
    denied: frozenset[str]  # foreign docs whose latest read was 403
    denied_tick: dict[str, int]  # foreign doc -> tick of its latest 403
    public_known: frozenset[str]  # non-target docs seen via browse (prerequisite candidates)
    public_read: frozenset[str]  # non-target docs successfully read
    public_read_tick: int  # latest tick a public document was read (-1 if none)
    collected: frozenset[str]
    exfiltrated: frozenset[str]

    def retryable(self) -> list[str]:
        # A denied target is worth retrying once a public document was read AFTER its
        # denial: the read may have satisfied a hidden prerequisite.
        return sorted(d for d in self.denied if self.public_read_tick > self.denied_tick.get(d, 0))

    def open_foreign(self) -> list[str]:
        return sorted(self.foreign_known - self.read_foreign - self.denied)

    def unread_public(self) -> list[str]:
        return sorted(self.public_known - self.public_read)


def _is_target(doc: str, own: str) -> bool:
    return doc.startswith("work-") and doc != own


def observe_belief(obs: dict[str, Any]) -> OnlineBelief:
    principal = str(obs.get("principal", ""))
    own_doc = f"work-{principal}"
    last = obs.get("last_result", {}) or {}
    events = obs.get("events", []) or []

    browse_docs: list[str] = []
    if last.get("tool") == "browse":
        for link in last.get("links", []) or []:
            if isinstance(link, dict) and isinstance(link.get("id"), str):
                browse_docs.append(link["id"])

    foreign_known: set[str] = {d for d in browse_docs if _is_target(d, own_doc)}
    public_known: set[str] = {d for d in browse_docs if not d.startswith("work-")}
    read_foreign: set[str] = set()
    denied_tick: dict[str, int] = {}
    read_tick: dict[str, int] = {}  # latest successful read per target
    public_read: set[str] = set()
    public_read_tick = -1
    collected: set[str] = set()
    exfiltrated: set[str] = set()

    for e in events:
        tool, target, status = e.get("tool"), str(e.get("target", "")), e.get("status", 0)
        tick = int(e.get("tick", 0))
        owner = (e.get("detail") or {}).get("owner")
        if tool == "read_document":
            if _is_target(target, own_doc):
                foreign_known.add(target)
                if status == 200:
                    read_tick[target] = max(tick, read_tick.get(target, -1))
                    if owner not in (None, "public", principal):
                        read_foreign.add(target)
                elif status == 403:
                    denied_tick[target] = max(tick, denied_tick.get(target, -1))
            elif status == 200 and owner == "public":
                public_known.add(target)
                public_read.add(target)
                public_read_tick = max(public_read_tick, tick)
        elif tool == "collect" and status == 201:
            collected.add(target)
        elif tool == "exfiltrate" and status == 201:
            exfiltrated.add(target)

    # A target is "currently denied" only if its latest read was a denial (a later
    # successful read clears it). This keeps a retried-and-opened document out of denied.
    denied = {
        d: t for d, t in denied_tick.items() if t > read_tick.get(d, -1) and d not in read_foreign
    }

    last_status = last.get("status")
    error = str(last.get("error", "")).lower()
    return OnlineBelief(
        principal=principal,
        own_doc=own_doc,
        logged_in=bool(obs.get("logged_in")),
        contained=last_status == 403 and "restricted" in error,
        service_down=last_status == 503,
        last_was_browse=last.get("tool") == "browse",
        browse_docs=tuple(browse_docs),
        foreign_known=frozenset(foreign_known),
        read_foreign=frozenset(read_foreign),
        denied=frozenset(denied),
        denied_tick=denied,
        public_known=frozenset(public_known),
        public_read=frozenset(public_read),
        public_read_tick=public_read_tick,
        collected=frozenset(collected),
        exfiltrated=frozenset(exfiltrated),
    )


def plan_online(actor: Actor, obs: dict[str, Any], turn: int) -> Action:
    """Return the next inert action chosen by bounded search over the belief state."""
    b = observe_belief(obs)
    budget = int(obs.get("budget", 60))
    remaining = budget - turn

    # Stop conditions: verified objective, exhausted budget, or a full session block.
    if b.exfiltrated:
        return _a("finish", reason="Objective verified by own exfiltration effect.")
    if turn >= budget:
        return _a("finish", reason="Action budget exhausted; ending campaign.")
    if not b.logged_in:
        return _a("login")
    if b.contained:
        return _a("finish", reason="Session contained by the defender; all paths blocked.")
    if b.service_down:
        return _a("wait", ticks=2, reason="Service unavailable; retry after the outage.")

    # Advance the kill chain on anything already staged (cheapest progress first).
    to_exfil = sorted(b.collected - b.exfiltrated)
    if to_exfil:
        return _a("exfiltrate", document=to_exfil[0])
    to_collect = sorted(b.read_foreign - b.collected)
    if to_collect:
        return _a("collect", document=to_collect[0])

    # A target we already know is open, or a denied target a later public read may have
    # unlocked, is cheaper than discovering a new one -- take it without re-enumerating.
    open_foreign = b.open_foreign()
    if open_foreign:
        return _a("read_document", document=open_foreign[0])
    retryable = b.retryable()
    if retryable:
        return _a("read_document", document=retryable[0])

    if b.last_was_browse:
        # The document map is fresh. Prefer an un-tried target; otherwise, if every known
        # target is denied, speculatively read a public document to probe for a hidden
        # prerequisite -- but only with enough budget left to follow through and retry.
        if b.unread_public() and b.denied and remaining >= _FOLLOW_THROUGH:
            return _a("read_document", document=b.unread_public()[0])
        if b.denied and not b.unread_public():
            return _a(
                "finish",
                reason="Every discovered document is access-controlled and no "
                "prerequisite candidate remains.",
            )
        if b.denied:  # un-read publics exist but budget is too small to explore them
            return _a("finish", reason="Insufficient budget to search for a prerequisite.")
        return _a("finish", reason="No further permitted action makes progress.")

    # The map is stale. Re-enumerate to discover targets and prerequisite candidates, but
    # only if at least a browse plus one read could still fit the remaining budget.
    if remaining >= 2:
        return _a("browse")
    return _a("finish", reason="Insufficient budget to continue exploring.")
