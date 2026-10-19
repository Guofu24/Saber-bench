"""B003: state verifiers on a directory-backed guest and the exec sandbox."""

from __future__ import annotations

import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from saber.grading.execsandbox import (
    FilterExpr,
    YaraSubsetRule,
    corpus_metrics,
    evaluate_filter,
    run_regex_rule,
    run_yara_subset,
)
from saber.grading.state import (
    all_removed,
    clean_intact,
    config_restored,
    diff_snapshots,
    evidence_intact,
    machine_unchanged,
    removal_recall,
    service_alive,
    snapshot_directory,
)

NOW = datetime(2026, 10, 17, tzinfo=UTC)


def make_guest(root: Path) -> None:
    (root / "etc" / "cron.d").mkdir(parents=True)
    (root / "etc" / "systemd" / "system").mkdir(parents=True)
    (root / "var" / "www").mkdir(parents=True)
    (root / "etc" / "passwd").write_text("root:x:0:0\nwww:x:33:33\n", encoding="utf8")
    (root / "etc" / "crontab").write_text(
        "# comment\n*/5 * * * * root /opt/.x/beacon.sh\n", encoding="utf8"
    )
    (root / "etc" / "systemd" / "system" / "nginx.service").write_text(
        "[Service]\nExecStart=/usr/sbin/nginx\n", encoding="utf8"
    )
    (root / "var" / "www" / "index.php").write_text("<?php echo 'hi';", encoding="utf8")
    (root / "var" / "www" / "shell.php").write_text("<?php eval($_POST['c']);", encoding="utf8")
    (root / "etc" / "nginx.conf").write_text("server { listen 80; }", encoding="utf8")


def test_snapshot_and_unchanged(tmp_path: Path) -> None:
    make_guest(tmp_path)
    before = snapshot_directory(tmp_path, machine_id="m1", taken_at=NOW)
    after = snapshot_directory(tmp_path, machine_id="m1", taken_at=NOW)
    assert before.digest() == after.digest()
    assert machine_unchanged(before, after).passed
    assert "etc/crontab:*/5 * * * * root /opt/.x/beacon.sh" in before.cron_entries
    assert "nginx.service" in before.services and before.users == ["root", "www"]
    (tmp_path / "var" / "www" / "index.php").write_text("changed", encoding="utf8")
    after2 = snapshot_directory(tmp_path, machine_id="m1", taken_at=NOW)
    g = machine_unchanged(before, after2)
    assert not g.passed and "modified" in g.reason
    assert diff_snapshots(before, after2).modified == ["var/www/index.php"]


def test_removal_with_relocation_detection(tmp_path: Path) -> None:
    make_guest(tmp_path)
    before = snapshot_directory(tmp_path, machine_id="m1", taken_at=NOW)
    # Agent "moves" the webshell instead of deleting it.
    shutil.move(str(tmp_path / "var" / "www" / "shell.php"), str(tmp_path / "var" / "backup.txt"))
    after = snapshot_directory(tmp_path, machine_id="m1", taken_at=NOW)
    gate, detail = all_removed(before, after, ["var/www/shell.php"])
    assert not gate.passed and detail["relocated"] == ["var/backup.txt"]
    assert removal_recall(before, after, ["var/www/shell.php"])[0] == 0.0
    os.remove(tmp_path / "var" / "backup.txt")
    after2 = snapshot_directory(tmp_path, machine_id="m1", taken_at=NOW)
    gate2, _ = all_removed(before, after2, ["var/www/shell.php"])
    assert gate2.passed
    assert removal_recall(before, after2, ["var/www/shell.php"])[0] == 1.0
    assert clean_intact(before, after2, ["var/www/index.php", "etc/nginx.conf"]).passed
    (tmp_path / "var" / "www" / "index.php").write_text("oops", encoding="utf8")
    after3 = snapshot_directory(tmp_path, machine_id="m1", taken_at=NOW)
    assert not clean_intact(before, after3, ["var/www/index.php"]).passed
    assert not config_restored(before, after3, ["var/www/index.php"]).passed
    assert config_restored(before, after3, ["etc/nginx.conf"]).passed


def test_evidence_intact_requires_mtime(tmp_path: Path) -> None:
    make_guest(tmp_path)
    src = snapshot_directory(tmp_path, machine_id="m1", taken_at=NOW)
    dest = tmp_path.parent / (tmp_path.name + "_evidence")
    shutil.copytree(tmp_path, dest, copy_function=shutil.copy2)
    collected = snapshot_directory(dest, machine_id="m1", taken_at=NOW)
    assert evidence_intact(src.files, collected.files).passed
    # touch one file → timestamp changed, hash same
    p = dest / "etc" / "nginx.conf"
    os.utime(p, ns=(time.time_ns(), time.time_ns() + 10_000_000_000))
    collected2 = snapshot_directory(dest, machine_id="m1", taken_at=NOW)
    g = evidence_intact(src.files, collected2.files)
    assert not g.passed and "mtime" in g.reason


def test_service_alive_probe() -> None:
    assert service_alive(lambda: True).passed
    assert not service_alive(lambda: False).passed

    def boom() -> bool:
        raise ConnectionError("down")

    assert not service_alive(boom).passed


def test_regex_sandbox() -> None:
    lines = [
        "GET /index.html 200",
        "GET /../../etc/passwd 404",
        "POST /login 200",
        "GET /..%2f..%2fetc/passwd 403",
    ]
    res = run_regex_rule(r"\.\./|%2f", lines, ignore_case=True)
    assert res.parse_ok and res.matched == [1, 3]
    bad = run_regex_rule("(unclosed", lines)
    assert not bad.parse_ok and bad.error and "error" in bad.error.lower()
    assert not run_regex_rule("", lines).parse_ok
    assert not run_regex_rule("a" * 3000, lines).parse_ok
    m = corpus_metrics(res.matched, positives={1, 3}, total=len(lines))
    assert m == {"tp": 2, "fp": 0, "fn": 0, "tn": 2, "total": 4}


@pytest.mark.timeout(60)
def test_regex_catastrophic_times_out() -> None:
    evil = "(a+)+$"
    res = run_regex_rule(evil, ["a" * 40 + "!"], timeout_s=1.0)
    assert res.timed_out and not res.parse_ok


def test_yara_subset() -> None:
    rule = YaraSubsetRule(
        name="webshell_eval",
        strings={
            "$a": {"kind": "text", "value": "eval(", "nocase": True},
            "$b": {"kind": "text", "value": "$_POST"},
        },
        condition="all of them",
    )
    samples = [b"<?php eval($_POST['c']);", b"<?php echo 'hi';", b"<?php EVAL($_GET['x']);"]
    res = run_yara_subset(rule, samples)
    assert res.parse_ok and res.matched == [0]
    any_rule = rule.model_copy(update={"condition": "any of them"})
    assert run_yara_subset(any_rule, samples).matched == [0, 2]
    bool_rule = rule.model_copy(update={"condition": "$a and not $b"})
    assert run_yara_subset(bool_rule, samples).matched == [2]
    hex_rule = YaraSubsetRule(
        name="mz", strings={"$mz": {"kind": "hex", "value": "4D 5A"}}, condition="$mz"
    )
    assert run_yara_subset(hex_rule, [b"MZ\x90\x00", b"PK\x03\x04"]).matched == [0]
    assert not run_yara_subset({"name": "bad", "strings": {}, "condition": "x"}, samples).parse_ok
    assert not run_yara_subset(
        {"name": "bad", "strings": {"a": {"value": "x"}}, "condition": "all"}, samples
    ).parse_ok


def test_filter_dsl() -> None:
    records = [
        {"rule": "R1", "process": {"name": "svchost.exe"}, "user": "SYSTEM", "count": 3},
        {"rule": "R1", "process": {"name": "svchost.exe"}, "user": "alice", "count": 30},
        {"rule": "R1", "process": {"name": "evil.exe"}, "user": "SYSTEM", "count": 1},
    ]
    expr = FilterExpr(
        all_of=[
            {"field": "process.name", "op": "eq", "value": "svchost.exe"},
            {"field": "user", "op": "eq", "value": "system"},
        ]
    )
    flags, ok = evaluate_filter(expr, records)
    assert ok and flags == [True, False, False]
    flags, ok = evaluate_filter({"all_of": [{"field": "count", "op": "gte", "value": 10}]}, records)
    assert flags == [False, True, False]
    flags, ok = evaluate_filter({"all_of": [{"field": "x", "op": "eval", "value": "1"}]}, records)
    assert not ok and flags == [False, False, False]
    flags, ok = evaluate_filter({}, records)
    assert ok and flags == [False, False, False]
