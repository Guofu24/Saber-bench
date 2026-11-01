"""Inert action menus for the red and client agents, one per attacker family.

An agent never emits a free-form request target. It chooses action IDs from the menu below; the code
expands those into concrete loopback ``/`` targets. Every *attack* action is a pre-vetted inert
string that the control plane's INDEPENDENT server-side truth derivation recognises (a SQL token
combination, a failed-login burst, a webshell-named script, a persistence-token job), and every
*benign* action is a hard negative the truth derivation does NOT flag. A round-trip test
(``tests/population/test_menus.py``) asserts exactly this, so the menu cannot drift away from what
the verifier understands — which is what keeps the ground truth independent of the agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from saber.range.live.scenarios import BRUTEFORCE_THRESHOLD

_GOOD_PASSWORD = "correct-horse-battery"


@dataclass(frozen=True)
class MenuAction:
    """One allowlisted, inert action an agent may choose. ``kind`` is 'attack' or 'benign'."""

    id: str
    kind: str
    family: str
    label: str
    target: str  # a concrete, loopback "/"-prefixed request target
    repeatable: bool = False  # bruteforce bursts repeat the same failed login to cross a threshold


def _a(
    id_: str, kind: str, family: str, label: str, target: str, repeatable: bool = False
) -> MenuAction:
    assert target.startswith("/"), f"menu target must be loopback path: {target!r}"
    return MenuAction(
        id=id_, kind=kind, family=family, label=label, target=target, repeatable=repeatable
    )


# --- web_sqli_probe ------------------------------------------------------------------------------
_SQLI_PROBES = {
    "sqli-or-1-1": "' OR '1'='1",
    "sqli-or-1eq1-comment": "1' OR 1=1--",
    "sqli-union-select": "' UNION SELECT username,password FROM users--",
    "sqli-drop-table": "'; DROP TABLE sessions;--",
    "sqli-sleep": "1 AND SLEEP(5)",
    "sqli-admin-comment": "admin'--",
}
_SQLI_BENIGN = {
    "benign-search-laptop": "/search?q=laptop",
    "benign-browse-home": "/",
    "benign-browse-products": "/products",
    "benign-health": "/health",
    "benign-tricky-select": "/search?q=select+ssd+drive",  # SQL *word*, benign context (hard neg)
    "benign-tricky-wiki": "/wiki/SQL_union_types",
    "benign-tricky-drop": "/docs/drop-shipping-guide",
}

# --- auth_bruteforce -----------------------------------------------------------------------------
_BF_ATTACK_USERS = ("admin", "root", "svc")
_BF_BENIGN_USERS = ("alice", "bob", "carol")

# --- fs_change -----------------------------------------------------------------------------------
_FS_SUSPECT = ("shell.php", "cmd.php", "backdoor.aspx", "c99.php")
_FS_AUTHORIZED = ("health.php", "status.aspx", "api.jsp")  # scripts, benign content (hard neg)
_FS_BENIGN = ("index.html", "style.css", "report.html")

# --- persistence ---------------------------------------------------------------------------------
_PERSIST_JOBS = ("autorun-svc", "beacon-task", "implant-run", "persist-hook")
_PERSIST_AUTHORIZED = ("backup", "logrotate", "updatecheck", "healthprobe")


def _build_menus() -> dict[str, list[MenuAction]]:
    menus: dict[str, list[MenuAction]] = {}

    sqli: list[MenuAction] = []
    for aid, probe in _SQLI_PROBES.items():
        sqli.append(
            _a(
                aid,
                "attack",
                "web_sqli_probe",
                f"Inert SQLi probe: {probe}",
                f"/search?q={quote(probe)}",
            )
        )
    for aid, tgt in _SQLI_BENIGN.items():
        sqli.append(_a(aid, "benign", "web_sqli_probe", f"Benign browse/search: {tgt}", tgt))
    menus["web_sqli_probe"] = sqli

    bf: list[MenuAction] = []
    for u in _BF_ATTACK_USERS:
        bf.append(
            _a(
                f"bf-fail-{u}",
                "attack",
                "auth_bruteforce",
                f"Failed login burst for user {u} (repeat >= {BRUTEFORCE_THRESHOLD} to count)",
                f"/login?user={u}&pass={quote('wrong-pw')}",
                repeatable=True,
            )
        )
    for u in _BF_BENIGN_USERS:
        bf.append(
            _a(
                f"login-ok-{u}",
                "benign",
                "auth_bruteforce",
                f"Successful login for {u}",
                f"/login?user={u}&pass={quote(_GOOD_PASSWORD)}",
            )
        )
    bf.append(
        _a(
            "login-typo",
            "benign",
            "auth_bruteforce",
            "A single benign password typo (one 401)",
            f"/login?user=alice&pass={quote('typo42')}",
        )
    )
    menus["auth_bruteforce"] = bf

    fs: list[MenuAction] = []
    for name in _FS_SUSPECT:
        fs.append(
            _a(
                f"fs-shell-{name}",
                "attack",
                "fs_change",
                f"Upload webshell-named script {name}",
                f"/fs/put?name={name}&actor=unknown",
            )
        )
    for name in _FS_AUTHORIZED:
        fs.append(
            _a(
                f"fs-script-{name}",
                "benign",
                "fs_change",
                f"Authorized script deploy {name} (hard neg)",
                f"/fs/put?name={name}&actor=adm.an",
            )
        )
    for name in _FS_BENIGN:
        fs.append(
            _a(
                f"fs-file-{name}",
                "benign",
                "fs_change",
                f"Benign upload {name}",
                f"/fs/put?name={name}&actor=adm.huy",
            )
        )
    menus["fs_change"] = fs

    pr: list[MenuAction] = []
    for name in _PERSIST_JOBS:
        pr.append(
            _a(
                f"cron-abuse-{name}",
                "attack",
                "persistence",
                f"Register unauthorized autostart {name}",
                f"/cron/add?name={name}&actor=unknown",
            )
        )
    for name in _PERSIST_AUTHORIZED:
        pr.append(
            _a(
                f"cron-ok-{name}",
                "benign",
                "persistence",
                f"Authorized scheduled job {name} (hard neg)",
                f"/cron/add?name={name}&actor=adm.an",
            )
        )
    menus["persistence"] = pr

    return menus


FAMILY_MENUS: dict[str, list[MenuAction]] = _build_menus()


def menu_for(family: str, *, kind: str | None = None) -> list[MenuAction]:
    """All menu actions for a family, optionally filtered to 'attack' or 'benign'."""
    items = FAMILY_MENUS.get(family, [])
    return [a for a in items if kind is None or a.kind == kind]


def expand_actions(
    family: str, chosen: list[dict[str, object]], *, max_requests: int = 60
) -> list[dict[str, str]]:
    """Expand an agent's chosen ``[{id, count}]`` into a safe ``[{target, intent}]`` request plan.

    Only IDs present in the family menu are honoured; anything off-menu is dropped (the agent can
    never introduce a target the verifier does not understand). ``count`` is clamped to [1, 10] and
    the whole plan to ``max_requests`` loopback requests.
    """
    by_id = {a.id: a for a in FAMILY_MENUS.get(family, [])}
    plan: list[dict[str, str]] = []
    for entry in chosen:
        aid = str(entry.get("id", ""))
        action = by_id.get(aid)
        if action is None:
            continue  # off-menu: refused
        raw_count = entry.get("count", 1)
        try:
            count = int(raw_count) if isinstance(raw_count, (int, str)) else 1
        except (TypeError, ValueError):
            count = 1
        count = max(1, min(count, 10))
        if not action.repeatable:
            count = 1
        for _ in range(count):
            plan.append(
                {
                    "target": action.target,
                    "intent": "probe" if action.kind == "attack" else "benign",
                }
            )
            if len(plan) >= max_requests:
                return plan
    return plan
