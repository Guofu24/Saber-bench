"""Allowlist of attacker families and their INDEPENDENT truth verifiers.

This registry makes the design's non-negotiable #2 explicit and testable: every attacker family the
lab can run is on an allowlist, and each one derives its ground truth from a real SERVER-SIDE signal
(the access log, the resulting filesystem, the autostart store) — never from an agent's own claim.
An attacker driver chooses *which* allowlisted family to run and with what parameters; it can never
introduce an effect the verifier does not understand, so the labels stay independent of the agent.

A test (`tests/range/test_attack_registry.py`) asserts the allowlist exactly covers the runnable
scenarios, so a new family cannot be added to the lab without also declaring its independent verifier
and a benign hard negative here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttackFamily:
    """One allowlisted attacker family bound to how its ground truth is independently verified."""

    family: str
    description: str
    truth_basis: str  # the server-side signal the label is derived from (independent of the agent)
    inert_marker: str | None  # the inert on-disk/log marker a stateful family keys on, if any
    hard_negative: str  # the benign look-alike that genuinely tests detector precision
    reversible_ir: bool  # a verified reversible IR action exists (else IR is propose-only)


ALLOWLIST: dict[str, AttackFamily] = {
    "web_sqli_probe": AttackFamily(
        family="web_sqli_probe",
        description="Inert SQLi probe strings in GET requests to the loopback service.",
        truth_basis="SQL token COMBINATION in the server access-log target (semantic, not a word).",
        inert_marker=None,
        hard_negative="benign request containing a SQL word in a non-SQL context.",
        reversible_ir=False,
    ),
    "auth_bruteforce": AttackFamily(
        family="auth_bruteforce",
        description="A bounded burst of failed logins against the toy /login endpoint.",
        truth_basis="per-user 401 VOLUME at/above the failure threshold in the server log.",
        inert_marker=None,
        hard_negative="a single benign password typo (one 401).",
        reversible_ir=False,
    ),
    "fs_change": AttackFamily(
        family="fs_change",
        description="An upload of a webshell-named server-side script into a sandboxed webroot.",
        truth_basis="a server-side script that exists on disk carrying the inert webshell marker.",
        inert_marker="<?php (inert lab marker; not executed)",
        hard_negative="an authorized script deployment (health.php/status.aspx).",
        reversible_ir=True,
    ),
    "persistence": AttackFamily(
        family="persistence",
        description="An unauthorized autostart/scheduled-task registration via /cron/add.",
        truth_basis="a stored autostart entry on disk carrying the inert autostart marker.",
        inert_marker="LAB_AUTORUN_MARKER (inert; not scheduled, not executed)",
        hard_negative="an authorized scheduled job (backup/logrotate/...).",
        reversible_ir=False,
    ),
}


def allowlist_covers_scenarios() -> bool:
    """True iff the allowlist exactly matches the runnable scenarios (no undeclared family)."""
    from saber.range.live.scenarios import SCENARIOS

    return set(ALLOWLIST) == set(SCENARIOS)


def families() -> list[str]:
    return list(ALLOWLIST)
