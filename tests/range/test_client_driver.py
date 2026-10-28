"""Tests for the client population (benign background-noise driver).

The driver is an environment generator, not a scored contestant. These tests pin the two properties
that make that true and safe: (1) its traffic is benign *by construction* — no server-side truth-
derivation flags any of it — and (2) overlaid on a real attack scenario it only adds benign log
lines, leaving the server-side-derived attack truth (the set of malicious request targets)
unchanged. Determinism is checked so a noise background is reproducible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from saber.range.live import client_noise, run_episode
from saber.range.live.client_driver import _GOOD_PASSWORD
from saber.range.live.controlplane import _derive_truth, _is_sqli_target
from saber.subtasks._hv.common import Rng

_SCENARIOS = ("web_sqli_probe", "auth_bruteforce", "fs_change", "persistence")


def _noise(seed: int = 1, clients: int = 3) -> list[dict]:
    return client_noise(Rng("live-noise", "t", str(seed)), clients=clients)


def test_client_noise_is_deterministic() -> None:
    assert _noise(1) == _noise(1)  # same seed -> identical plan
    assert _noise(1) != _noise(2)  # different seed -> different plan (streams diverge)


def test_zero_clients_is_empty() -> None:
    assert client_noise(Rng("live-noise", "t", "1"), clients=0) == []


def test_client_noise_is_benign_by_construction() -> None:
    plan = _noise(7, clients=5)
    assert plan, "expected a non-empty benign plan"
    for req in plan:
        assert req["intent"] == "benign"
        target = req["target"]
        assert target.startswith("/"), f"non-loopback target would escape the lab: {target!r}"
        # never a SQL token combination (web_sqli_probe truth would otherwise flag it)
        assert not _is_sqli_target(target), f"noise must not trip SQLi truth: {target!r}"
        if target.startswith("/login"):
            # every login uses the valid password -> 200, never a 401 (auth threshold truth ignores)
            assert f"pass={_GOOD_PASSWORD}" in target
        # never a server-side-script upload (fs_change truth would otherwise flag it)
        assert "/fs/put" not in target


def test_noise_derives_no_malicious_web_lines() -> None:
    # Feed the noise plan to the web truth-derivation as if it were the server log: nothing flagged.
    lines = [{"target": r["target"], "status": 200} for r in _noise(3, clients=5)]
    assert _derive_truth("web_sqli_probe", lines) == set()


@pytest.mark.parametrize("scenario", _SCENARIOS)
def test_noise_does_not_change_attack_truth(scenario: str, tmp_path: Path) -> None:
    """A real run with benign noise must keep the SAME malicious targets, and only add lines."""
    base = run_episode(scenario, 11, workdir=tmp_path / "base")
    noisy = run_episode(scenario, 11, workdir=tmp_path / "noisy", noise_clients=3)

    # Both executions are genuine and reset cleanly, and both cross-check against generation intent.
    assert base.cross_check_ok is True and noisy.cross_check_ok is True
    assert noisy.lab_state["reset_ok"] is True

    # The attack content is unchanged: compare the malicious *targets* (line indices shift with the
    # interleaved benign noise, so ids are not comparable, but the set of flagged requests is).
    def mal_targets(ep) -> set[str]:
        idx = {int(lid.split("-")[1]) for lid in ep.gold_truth["malicious_line_ids"]}
        import json as _json

        recs = [_json.loads(ln) for ln in ep.access_log_lines]
        return {str(recs[i]["target"]) for i in idx}

    assert mal_targets(noisy) == mal_targets(base)

    # The noise added benign volume but not malicious volume.
    assert noisy.network["client_noise_requests"] > 0
    assert len(noisy.access_log_lines) > len(base.access_log_lines)
    assert noisy.gold_truth["m"] == base.gold_truth["m"]


def test_noise_count_zero_by_default(tmp_path: Path) -> None:
    ep = run_episode("web_sqli_probe", 2, workdir=tmp_path)
    assert ep.network["client_noise_requests"] == 0
