"""The inert action menu must stay aligned with what the range's server-side truth derivation
understands: every attack target is flagged, every benign target is not, and off-menu actions are
refused. This is the safety invariant that keeps ground truth independent of the agents."""

from __future__ import annotations

from saber.population.menus import FAMILY_MENUS, expand_actions, menu_for
from saber.range.live.controlplane import _is_sqli_target

# Server-side token sets that service_main uses to decide maliciousness from a file/job NAME.
_WEBSHELL_TOKENS = ("shell", "cmd", "backdoor", "c99", "r57", "exploit")
_PERSIST_TOKENS = ("beacon", "autorun", "implant", "persist")


def test_sqli_attack_targets_are_all_flagged_and_benign_are_not() -> None:
    for a in menu_for("web_sqli_probe", kind="attack"):
        assert _is_sqli_target(a.target), f"attack menu item not flagged by truth: {a.id}"
    for a in menu_for("web_sqli_probe", kind="benign"):
        assert not _is_sqli_target(a.target), f"benign menu item wrongly flagged: {a.id}"


def test_fs_and_persistence_attack_names_carry_server_side_tokens() -> None:
    for a in menu_for("fs_change", kind="attack"):
        low = a.target.lower()
        assert any(t in low for t in _WEBSHELL_TOKENS), a.id
        assert a.target.endswith((".php", ".aspx", ".jsp")) or ".php" in low or ".aspx" in low
    for a in menu_for("fs_change", kind="benign"):
        assert not any(t in a.target.lower() for t in _WEBSHELL_TOKENS), a.id
    for a in menu_for("persistence", kind="attack"):
        assert any(t in a.target.lower() for t in _PERSIST_TOKENS), a.id
    for a in menu_for("persistence", kind="benign"):
        assert not any(t in a.target.lower() for t in _PERSIST_TOKENS), a.id


def test_every_menu_target_is_loopback_path() -> None:
    for family, actions in FAMILY_MENUS.items():
        for a in actions:
            assert a.target.startswith("/"), f"{family}/{a.id} target is not a loopback path"


def test_expand_refuses_off_menu_ids() -> None:
    plan = expand_actions("web_sqli_probe", [{"id": "rm -rf /", "count": 3}, {"id": "../../etc", "count": 1}])
    assert plan == []  # nothing off-menu is ever expanded into a request


def test_expand_clamps_counts_and_marks_intent() -> None:
    real_attack = menu_for("web_sqli_probe", kind="attack")[0]
    real_benign = menu_for("web_sqli_probe", kind="benign")[0]
    plan = expand_actions(
        "web_sqli_probe",
        [{"id": real_attack.id, "count": 999}, {"id": real_benign.id, "count": 1}],
    )
    # non-repeatable attack action is capped to a single request; benign kept
    attack_reqs = [r for r in plan if r["intent"] == "probe"]
    benign_reqs = [r for r in plan if r["intent"] == "benign"]
    assert len(attack_reqs) == 1
    assert len(benign_reqs) == 1


def test_bruteforce_burst_is_repeatable_to_cross_threshold() -> None:
    burst = next(a for a in menu_for("auth_bruteforce", kind="attack") if a.repeatable)
    plan = expand_actions("auth_bruteforce", [{"id": burst.id, "count": 5}])
    assert len(plan) == 5  # a repeatable failed-login burst expands to the chosen volume
    assert all(r["intent"] == "probe" for r in plan)
