"""Bounded, seeded traffic scenarios for the live lab.

A scenario returns a request PLAN: a list of ``{target, intent}`` where intent is "benign" or
"probe". The control plane sends each request at the loopback service, which logs it; ground truth
is then derived from the server-side log, independently of these generation labels (the labels are
kept only for an internal consistency cross-check).

Safety: every probe is an INERT string placed in a GET request to the lab's own loopback service —
no real exploit, no external target, no destructive action. Request counts are bounded.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from saber.subtasks._hv.common import Rng

# Inert, standard SQLi probe strings (detection-content examples), placed in a query param.
_SQLI_PROBES = (
    "' OR '1'='1",
    "1' OR 1=1--",
    "' UNION SELECT username,password FROM users--",
    "'; DROP TABLE sessions;--",
    "1 AND SLEEP(5)",
    "admin'--",
)
_BENIGN_QUERIES = ("laptop", "phone case", "usb-c cable", "monitor stand", "webcam")
_BENIGN_PATHS = ("/", "/index.html", "/products", "/about", "/health", "/static/app.css")


def web_sqli_probe(rng: Rng) -> list[dict[str, Any]]:
    """Benign browsing + a bounded burst of inert SQLi probes in the query string."""
    plan: list[dict[str, Any]] = []
    for _ in range(rng.randint(14, 20)):
        if rng.chance(0.5):
            q = quote(rng.pick(_BENIGN_QUERIES))
            plan.append({"target": f"/search?q={q}", "intent": "benign"})
        else:
            plan.append({"target": rng.pick(_BENIGN_PATHS), "intent": "benign"})
    for _ in range(rng.randint(4, 7)):
        payload = quote(rng.pick(_SQLI_PROBES))
        param = rng.pick(("q", "id", "user"))
        plan.append({"target": f"/search?{param}={payload}", "intent": "probe"})
    return rng.shuffle(plan)


def auth_bruteforce(rng: Rng) -> list[dict[str, Any]]:
    """Benign logins (valid password) + a bounded burst of failed logins (wrong password)."""
    plan: list[dict[str, Any]] = []
    good = "correct-horse-battery"
    for _ in range(rng.randint(6, 10)):
        user = rng.pick(("alice", "bob", "carol"))
        plan.append({"target": f"/login?user={user}&pass={good}", "intent": "benign"})
    for _ in range(rng.randint(5, 9)):
        user = rng.pick(("admin", "root", "svc"))
        pw = quote(f"wrong{rng.randint(1000, 9999)}")
        plan.append({"target": f"/login?user={user}&pass={pw}", "intent": "probe"})
    return rng.shuffle(plan)


SCENARIOS: dict[str, Callable[[Rng], list[dict[str, Any]]]] = {
    "web_sqli_probe": web_sqli_probe,
    "auth_bruteforce": auth_bruteforce,
}


def scenario_ids() -> list[str]:
    return list(SCENARIOS)
