"""The attacker allowlist must exactly cover the runnable families, each with an independent verifier.

This is the test that enforces the design's non-negotiable #2: a new attack family cannot reach the
lab without declaring, here, the server-side signal its label is derived from and a benign hard
negative — so ground truth can never silently depend on an agent's own claim.
"""

from __future__ import annotations

from saber.range.live.attack_registry import ALLOWLIST, allowlist_covers_scenarios
from saber.range.live.scenarios import SCENARIOS


def test_allowlist_exactly_covers_runnable_scenarios() -> None:
    assert allowlist_covers_scenarios()
    assert set(ALLOWLIST) == set(SCENARIOS)


def test_every_family_declares_an_independent_truth_basis() -> None:
    for family, spec in ALLOWLIST.items():
        assert spec.family == family
        # Truth is derived from a documented server-side signal (log / disk / store) or an inert
        # on-disk marker — never from an agent's claim.
        assert spec.truth_basis
        server_side = any(k in spec.truth_basis.lower() for k in ("server", "log", "disk", "store"))
        assert server_side or spec.inert_marker
        # A benign hard negative must exist so precision is genuinely tested.
        assert spec.hard_negative
