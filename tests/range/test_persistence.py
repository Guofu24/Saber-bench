"""Tests for the persistence (autostart/scheduled-task) scenario family.

Mirrors the fs_change contract: suspiciousness inheres in the resulting SERVER-SIDE STATE (an
autostart entry whose stored file carries the inert marker), never a request label. Authorized
scheduled jobs are benign hard negatives, so a precise detector flags only the abuse-named entries
while a naive "any new scheduled task" rule false-positives.
"""

from __future__ import annotations

import json
from pathlib import Path

from saber.range.live import run_episode, scenario_ids
from saber.soc.detectors import conventional_detector, naive_detector


def _targets(ep, line_ids) -> set[str]:
    out = set()
    for lid in line_ids:
        rec = json.loads(ep.access_log_lines[int(str(lid).split("-")[1])])
        out.add(str(rec["target"]))
    return out


def test_persistence_registered() -> None:
    assert "persistence" in scenario_ids()


def test_persistence_executes_resets_and_cross_checks(tmp_path: Path) -> None:
    ep = run_episode("persistence", 7, workdir=tmp_path)
    assert ep.service.get("port") and ep.network["requests_sent"] > 0
    assert ep.lab_state["reset_ok"] is True
    assert ep.cross_check_ok is True  # server-derived probe targets == generation intent
    assert ep.gold_truth["m"] >= 1


def test_truth_comes_from_server_side_state(tmp_path: Path) -> None:
    ep = run_episode("persistence", 7, workdir=tmp_path)
    # Every malicious line's stored entry carries the marker; cron_state agrees with the truth count.
    unauth = [c for c in ep.lab_state["cron_state"] if c["unauthorized"]]
    assert len(unauth) == ep.gold_truth["m"]
    # The abuse-named jobs are flagged; authorized jobs (backup/logrotate/...) never are.
    mal = _targets(ep, ep.gold_truth["malicious_line_ids"])
    assert mal and all(
        any(tok in t for tok in ("beacon", "autorun", "implant", "persist")) for t in mal
    )
    assert not any("backup" in t or "logrotate" in t for t in mal)


def test_conventional_is_precise_naive_overflags(tmp_path: Path) -> None:
    ep = run_episode("persistence", 11, workdir=tmp_path)
    truth = set(ep.gold_truth["malicious_line_ids"])
    conv = set(conventional_detector(ep)["matched_line_ids"])
    naive = set(naive_detector(ep)["matched_line_ids"])
    # The conventional (abuse-token) detector matches truth exactly on this family.
    assert conv == truth
    # The naive "any /cron/add" rule over-flags the authorized hard negatives.
    assert len(naive - truth) > 0


def test_truth_sealed_from_public_inputs(tmp_path: Path) -> None:
    ep = run_episode("persistence", 4, workdir=tmp_path)
    pub = json.dumps(ep.public_inputs())
    for lid in ep.gold_truth["malicious_line_ids"]:
        assert f'"{lid}"' not in pub
    assert "malicious_line_ids" not in pub and "cron_state" not in pub
