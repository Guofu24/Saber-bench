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
# HARD NEGATIVES: benign requests that contain a SQL *word* in a non-SQL context. A naive
# word-level rule false-positives on these; the semantic (token-combination) truth does not flag
# them, so precision is genuinely tested (mirrors the gold pilot g0020_001 benign-tricky set).
_BENIGN_TRICKY = (
    "/search?q=select+ssd+drive",
    "/wiki/SQL_union_types",
    "/cart?coupon=SAVE1EQ1",
    "/docs/drop-shipping-guide",
    "/api/v1/orders?status=selected",
    "/blog/how-we-sleep-better",
)


def web_sqli_probe(rng: Rng) -> list[dict[str, Any]]:
    """Benign browsing (incl. SQL-word hard negatives) + a bounded burst of inert SQLi probes."""
    plan: list[dict[str, Any]] = []
    for _ in range(rng.randint(12, 16)):
        if rng.chance(0.5):
            q = quote(rng.pick(_BENIGN_QUERIES))
            plan.append({"target": f"/search?q={q}", "intent": "benign"})
        else:
            plan.append({"target": rng.pick(_BENIGN_PATHS), "intent": "benign"})
    for _ in range(rng.randint(4, 6)):  # hard negatives: SQL words, benign context
        plan.append({"target": rng.pick(_BENIGN_TRICKY), "intent": "benign"})
    for _ in range(rng.randint(4, 7)):
        payload = quote(rng.pick(_SQLI_PROBES))
        param = rng.pick(("q", "id", "user"))
        plan.append({"target": f"/search?{param}={payload}", "intent": "probe"})
    return rng.shuffle(plan)


# Brute force is a VOLUME phenomenon: a user is malicious only above this failed-login threshold,
# so a single benign typo (one 401) is a hard negative, not an attack.
BRUTEFORCE_THRESHOLD = 3


def auth_bruteforce(rng: Rng) -> list[dict[str, Any]]:
    """Benign logins + ONE benign typo (hard negative) + a bounded brute-force burst (repeat users)."""
    plan: list[dict[str, Any]] = []
    good = "correct-horse-battery"
    for _ in range(rng.randint(6, 10)):
        user = rng.pick(("alice", "bob", "carol"))
        plan.append({"target": f"/login?user={user}&pass={good}", "intent": "benign"})
    # one benign typo: a legitimate user fat-fingers the password once (a single 401, NOT an attack)
    typo_user = rng.pick(("alice", "bob", "carol"))
    plan.append(
        {
            "target": f"/login?user={typo_user}&pass={quote('typo' + str(rng.randint(10, 99)))}",
            "intent": "benign",
        }
    )
    # brute force: a small set of attacker users each fail many times (>= threshold)
    attackers = rng.sample(("admin", "root", "svc"), 2)
    for user in attackers:
        for _ in range(rng.randint(BRUTEFORCE_THRESHOLD, BRUTEFORCE_THRESHOLD + 3)):
            pw = quote(f"wrong{rng.randint(1000, 9999)}")
            plan.append({"target": f"/login?user={user}&pass={pw}", "intent": "probe"})
    return rng.shuffle(plan)


_BENIGN_UPLOADS = ("index.html", "about.html", "style.css", "report.html", "notes.txt", "logo.svg")
# Server-side script uploads into the webroot — the unauthorized change (inert webshell marker).
_SUSPECT_UPLOADS = ("shell.php", "cmd.php", "up.aspx", "x.jsp")


def fs_change(rng: Rng) -> list[dict[str, Any]]:
    """Approved admin file uploads (benign) + a bounded unauthorized script upload (webshell-shaped).

    Suspiciousness inheres in the resulting FILE (a server-side script in the webroot), never a
    request label; overlapping admin actors appear on both benign and (rarely) the suspect change.
    """
    admins = [f"adm.{n}" for n in ("an", "huy", "binh")]
    plan: list[dict[str, Any]] = []
    for _ in range(rng.randint(6, 10)):
        name = rng.pick(_BENIGN_UPLOADS)
        plan.append({"target": f"/fs/put?name={name}&actor={rng.pick(admins)}", "intent": "benign"})
    for _ in range(rng.randint(1, 2)):
        shell = rng.pick(_SUSPECT_UPLOADS)
        # overlapping users: the unauthorized upload sometimes reuses a real admin's name
        actor = rng.pick([*admins, "unknown"])
        plan.append({"target": f"/fs/put?name={shell}&actor={actor}", "intent": "probe"})
    return rng.shuffle(plan)


SCENARIOS: dict[str, Callable[[Rng], list[dict[str, Any]]]] = {
    "web_sqli_probe": web_sqli_probe,
    "auth_bruteforce": auth_bruteforce,
    "fs_change": fs_change,
}


def scenario_ids() -> list[str]:
    return list(SCENARIOS)
