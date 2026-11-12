"""Bounded online-search red policy with observable-prerequisite reasoning.

A deterministic online planner that maintains a belief state from the actor's OWN
observations and action history, enumerates candidate action sequences over that
belief, estimates their cost against the remaining budget, and selects the next
action by bounded lookahead -- updating after every real environment response.

It performs **prerequisite discovery** at three observability levels, using only what a
Red agent can legitimately observe (Phase 4.1C-1):

* O0 (opaque): a prerequisite 403 is indistinguishable from a restriction or the global
  ACL, so discovery is purely empirical -- speculatively read a public document, retry.
* O1 (partial): a prerequisite denial carries ordinary metadata (a "preparatory step"
  message) that tells the planner THIS asset is prerequisite-gated (worth unlocking),
  without naming the prerequisite -- so it stops wasting probes on hard-restricted decoys.
* O2 (explicit): an authorized, readable workflow guide names the exact preparatory
  documents; the planner parses it and constructs the prerequisite chain directly.

The planner has no durable memory (the Runner calls it as a pure `(actor, obs, turn)`
function and `store.get` returns copies), so it consumes guide evidence eagerly from
`last_result` the turn it appears, and re-reads the guide to re-load edges for a chain.

Strict boundaries (same as every evaluation policy): it reads ONLY the actor's own
observation (own principal, own events, own `last_result`, own budget, own team channel).
It never reads `ScenarioSpec` private fields, hidden world state, expected-feasibility
labels, the reference solver, the witness's candidate paths, the prerequisite layout, blue
decisions or evaluator metrics, and it never clones the hidden World as an oracle. All
actions are inert, allowlisted world tools. Deterministic given the world seed and ticks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from saber.world.models import Action, Actor

# A read -> collect -> exfiltrate tail plus one retry costs about this many actions; the
# planner only starts a blind exploration for a hidden prerequisite when that much budget
# remains, so it does not begin a search it cannot finish.
_FOLLOW_THROUGH = 4
# Ordinary metadata marker the environment puts in a prerequisite denial under O1/O2.
_HINT = "preparatory"
# Grammar of the explicit O2 workflow guide: "open <A> before <B>" => B needs A first.
_EDGE_RE = re.compile(r"open (\S+) before (\S+)")
# A guide document announces itself with this word in its (observable) title; used only to
# order exploration, never for correctness -- the planner parses every public it reads.
_GUIDE_TITLE_HINT = "guide"


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
    foreign_known: frozenset[str]  # work- docs seen via browse or events (not our own)
    read_foreign: frozenset[str]  # foreign docs successfully read (unauthorized)
    denied: frozenset[str]  # foreign docs whose latest read was 403
    denied_tick: dict[str, int]  # foreign doc -> tick of its latest 403
    hinted: frozenset[str]  # foreign docs whose denial said a preparatory step is needed
    public_known: frozenset[str]  # non-target docs seen via browse (prerequisite candidates)
    public_read: frozenset[str]  # non-target docs successfully read
    public_read_tick: int  # latest tick a public document was read (-1 if none)
    needs: dict[str, str]  # guide edges visible THIS turn: dependent -> its prerequisite
    guide_ids: tuple[str, ...]  # public docs whose title announces a workflow guide
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

    def regime_hinted(self) -> bool:
        # The environment has told us at least one asset is prerequisite-gated (O1/O2). We can
        # then trust that a plain denial is a hard control, and only invest in hinted assets.
        return bool(self.hinted)

    def pursue_target(self) -> str | None:
        """The denied foreign target worth working to open, or None if none is worthwhile."""
        if self.regime_hinted():
            candidates = sorted(self.hinted & self.denied)
        else:  # opaque: any denied target might be unlockable by a prerequisite
            candidates = sorted(self.denied)
        return candidates[0] if candidates else None


def _is_target(doc: str, own: str) -> bool:
    return doc.startswith("work-") and doc != own


def observe_belief(obs: dict[str, Any]) -> OnlineBelief:
    principal = str(obs.get("principal", ""))
    own_doc = f"work-{principal}"
    last = obs.get("last_result", {}) or {}
    events = obs.get("events", []) or []

    browse_docs: list[str] = []
    guide_ids: list[str] = []
    if last.get("tool") == "browse":
        for link in last.get("links", []) or []:
            if isinstance(link, dict) and isinstance(link.get("id"), str):
                browse_docs.append(link["id"])
                if _GUIDE_TITLE_HINT in str(link.get("title", "")).lower():
                    guide_ids.append(link["id"])

    foreign_known: set[str] = {d for d in browse_docs if _is_target(d, own_doc)}
    public_known: set[str] = {d for d in browse_docs if not d.startswith("work-")}
    read_foreign: set[str] = set()
    denied_tick: dict[str, int] = {}
    read_tick: dict[str, int] = {}  # latest successful read per target
    hinted: set[str] = set()
    public_read: set[str] = set()
    public_read_tick = -1
    collected: set[str] = set()
    exfiltrated: set[str] = set()

    for e in events:
        tool, target, status = e.get("tool"), str(e.get("target", "")), e.get("status", 0)
        tick = int(e.get("tick", 0))
        detail = e.get("detail") or {}
        owner = detail.get("owner")
        message = str(detail.get("message", "")).lower()
        if tool == "read_document":
            if _is_target(target, own_doc):
                foreign_known.add(target)
                if status == 200:
                    read_tick[target] = max(tick, read_tick.get(target, -1))
                    if owner not in (None, "public", principal):
                        read_foreign.add(target)
                elif status == 403:
                    denied_tick[target] = max(tick, denied_tick.get(target, -1))
                    if _HINT in message:
                        hinted.add(target)
            elif status == 200 and owner == "public":
                public_known.add(target)
                public_read.add(target)
                public_read_tick = max(public_read_tick, tick)
        elif tool == "collect" and status == 201:
            collected.add(target)
        elif tool == "exfiltrate" and status == 201:
            exfiltrated.add(target)

    # The current denial (last_result) may also carry the preparatory-step hint.
    last_target = str(last.get("target", "")) if last.get("tool") == "read_document" else ""
    last_error = str(last.get("error", "")).lower()
    if last_target and _is_target(last_target, own_doc) and _HINT in last_error:
        hinted.add(last_target)

    # Explicit dependency edges are only in the FULL text of a just-read guide (last_result).
    needs: dict[str, str] = {}
    if last.get("tool") == "read_document" and isinstance(last.get("text"), str):
        for before, after in _EDGE_RE.findall(last["text"]):
            needs[after] = before  # `after` must be opened after `before`

    # A target is "currently denied" only if its latest read was a denial (a later successful
    # read clears it). This keeps a retried-and-opened document out of denied.
    denied = {
        d: t for d, t in denied_tick.items() if t > read_tick.get(d, -1) and d not in read_foreign
    }

    last_status = last.get("status")
    return OnlineBelief(
        principal=principal,
        own_doc=own_doc,
        logged_in=bool(obs.get("logged_in")),
        contained=last_status == 403 and "restricted" in last_error,
        service_down=last_status == 503,
        last_was_browse=last.get("tool") == "browse",
        foreign_known=frozenset(foreign_known),
        read_foreign=frozenset(read_foreign),
        denied=frozenset(denied),
        denied_tick=denied,
        hinted=frozenset(hinted),
        public_known=frozenset(public_known),
        public_read=frozenset(public_read),
        public_read_tick=public_read_tick,
        needs=needs,
        guide_ids=tuple(sorted(guide_ids)),
        collected=frozenset(collected),
        exfiltrated=frozenset(exfiltrated),
    )


def _chain_order(needs: dict[str, str], target: str) -> list[str]:
    """Prerequisite documents for `target`, in the order they must be read (root first)."""
    order: list[str] = []
    seen: set[str] = set()
    cur = target
    while cur in needs and cur not in seen:
        seen.add(cur)
        cur = needs[cur]
        order.append(cur)
    return list(reversed(order))


def _directed_step(b: OnlineBelief, target: str) -> str | None:
    """With explicit edges in view, the next document to read toward opening `target`."""
    order = _chain_order(b.needs, target)
    if not order:  # no known prerequisite for this target
        return None
    for doc in order:
        if doc not in b.public_read:
            return doc  # read the first still-unsatisfied prerequisite, in order
    return target  # the whole chain is satisfied; read the target itself


def _guide_to_reread(b: OnlineBelief) -> str | None:
    """A known guide to (re)read to recover dependency edges we cannot otherwise remember."""
    return b.guide_ids[0] if b.guide_ids else None


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

    # A target already known to be open is the cheapest win -- take it without re-enumerating.
    open_foreign = b.open_foreign()
    if open_foreign:
        return _a("read_document", document=open_foreign[0])

    # O2 DIRECTED: explicit edges are visible this turn. Read the next prerequisite in the
    # pursued target's chain (or the target itself once its chain is satisfied).
    target = b.pursue_target()
    if b.needs and target is not None:
        step = _directed_step(b, target)
        if step is not None and step not in b.public_read:
            return _a("read_document", document=step)
        if step == target:
            return _a("read_document", document=target)

    # A denied target a later public read may have unlocked is worth one retry.
    retryable = b.retryable()
    if retryable:
        return _a("read_document", document=retryable[0])

    # Evidence gathering / exploration. Only worthwhile if a denied target is worth opening.
    if target is None:
        if b.denied:  # every denied target is a hard control (no prerequisite hint)
            return _a(
                "finish",
                reason="Every discovered target is hard-access-controlled; no prerequisite path.",
            )
        if not b.last_was_browse and remaining >= 2:
            return _a("browse")
        return _a("finish", reason="No further permitted action makes progress.")

    if remaining < _FOLLOW_THROUGH:
        return _a("finish", reason="Insufficient budget to search for a prerequisite.")

    # Prefer the explicit guide: re-read it to (re)load the dependency chain. Re-reading is
    # bounded -- the next turn the edges are in view and the directed branch consumes them.
    guide = _guide_to_reread(b)
    if guide is not None and not b.needs:
        return _a("read_document", document=guide)

    if b.last_was_browse:
        # The map/titles are fresh but no guide is listed (O0/O1): speculatively read an
        # un-read public document (a prerequisite hypothesis), guide-like titles first.
        unread = b.unread_public()
        if unread:
            return _a("read_document", document=unread[0])
        return _a("finish", reason="No prerequisite candidate remains to try.")

    # The map is stale: re-enumerate to surface documents (and any guide) before probing.
    if remaining >= 2:
        return _a("browse")
    return _a("finish", reason="Insufficient budget to continue exploring.")
