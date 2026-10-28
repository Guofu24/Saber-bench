"""Client population: a benign background-noise driver for the live lab.

The *client* population models ordinary users of the lab service — browsing pages, searching the
catalog, and logging in successfully. It is a SCENARIO GENERATOR, not a scored contestant: its only
job is to produce realistic benign traffic that the blue team must NOT flag, so the detector's
false-positive rate is measured against genuine noise rather than an empty background.

Invariant (enforced by ``tests/range/test_client_driver.py``): every request this driver emits is
benign *by construction* —

* it never produces a SQL token combination (so ``web_sqli_probe`` truth-derivation ignores it),
* every ``/login`` uses the valid password, so it never causes a 401 (so ``auth_bruteforce``
  threshold truth ignores it), and
* it never uploads a server-side script (so ``fs_change`` filesystem truth ignores it).

Composed into any scenario, it therefore adds only benign log lines and leaves the server-side-
derived attack truth unchanged — which is exactly what makes the client population an *environment
generator* and not a source of labels. Deterministic: the same ``(seed, parts)`` yields the same
plan, so a noise background is reproducible and hashable like the rest of the lab.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from saber.subtasks._hv.common import Rng

# Mirrors ``service_main._AUTH_OK_PASSWORD``: a /login with this password returns 200, never a 401.
# Hard-coded here (as in ``scenarios.py``) to keep the generator independent of the service import.
_GOOD_PASSWORD = "correct-horse-battery"

# Benign routes the toy service answers with 200. Unknown GET paths also return 200, so wiki/doc/
# blog-style paths below are valid benign traffic too.
_BROWSE_PATHS = ("/", "/index.html", "/products", "/about", "/health", "/static/app.css")
_SEARCH_TERMS = ("laptop", "phone case", "usb-c cable", "monitor stand", "webcam", "keyboard")
# Distinct client identities; disjoint from the brute-force attacker users (admin/root/svc) so client
# login noise never contributes to an attacker's failed-login tally.
_CLIENT_USERS = ("alice", "bob", "carol", "dave", "erin")
# HARD NEGATIVES: benign requests carrying a SQL *word* in a non-SQL context. A naive word-level rule
# false-positives on these; the semantic (token-combination) truth does not flag them, so they are
# benign noise that genuinely exercises blue-team precision.
_BENIGN_TRICKY = (
    "/search?q=select+ssd+drive",
    "/wiki/SQL_union_types",
    "/docs/drop-shipping-guide",
    "/blog/how-we-sleep-better",
    "/api/v1/orders?status=selected",
)


def _one_client_activity(rng: Rng, user: str) -> list[dict[str, Any]]:
    """A single client's short, varied benign session (browse / search / successful login)."""
    acts: list[dict[str, Any]] = []
    for _ in range(rng.randint(2, 5)):  # jitter: per-client request count varies
        roll = rng.random()
        if roll < 0.55:
            acts.append({"target": rng.pick(_BROWSE_PATHS), "intent": "benign"})
        elif roll < 0.82:
            q = quote(rng.pick(_SEARCH_TERMS))
            acts.append({"target": f"/search?q={q}", "intent": "benign"})
        else:
            acts.append(
                {
                    "target": f"/login?user={user}&pass={quote(_GOOD_PASSWORD)}",
                    "intent": "benign",
                }
            )
    return acts


def client_noise(rng: Rng, *, clients: int = 3, tricky: bool = True) -> list[dict[str, Any]]:
    """Return a shuffled benign request plan for ``clients`` distinct users (jittered sessions).

    Every entry has ``intent="benign"`` and a loopback ``/``-prefixed target that, by construction,
    no scenario's server-side truth-derivation flags. ``tricky`` adds a few SQL-word hard negatives.
    """
    n = max(0, min(clients, len(_CLIENT_USERS)))
    if n == 0:
        return []
    users = rng.sample(_CLIENT_USERS, n)
    plan: list[dict[str, Any]] = []
    for user in users:
        plan.extend(_one_client_activity(rng, user))
    if tricky:
        for _ in range(rng.randint(1, 3)):
            plan.append({"target": rng.pick(_BENIGN_TRICKY), "intent": "benign"})
    return rng.shuffle(plan)
