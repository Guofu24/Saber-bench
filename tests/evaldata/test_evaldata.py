"""Tests for Phase E1 evaluation-data ingestion, provenance, and contamination control."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saber.evaldata import (
    CANDIDATE_SOURCES,
    DataSource,
    LabelTier,
    LineageGuardError,
    assert_no_lineage_crosses_split,
    candidate_by_kind,
    import_dataset,
    lineage_key,
)


def _src(kind: str) -> DataSource:
    return DataSource(
        name="test", kind=kind, url="https://example.invalid", license="test", usage_permitted=True
    )


def test_import_event_log_json_array(tmp_path: Path) -> None:
    p = tmp_path / "events.json"
    p.write_text(
        json.dumps(
            [
                {"UtcTime": "2026-01-01 00:00:00", "Hostname": "ws-1", "EventID": 1, "Image": "x"},
                {"UtcTime": "2026-01-01 00:01:00", "Hostname": "ws-1", "EventID": 3},
            ]
        ),
        encoding="utf-8",
    )
    res = import_dataset(p, source=_src("event_log"), label_tier=LabelTier.SOURCE_PROVIDED)
    assert res.ok
    assert res.provenance.record_count == 2
    assert res.records[0]["host"] == "ws-1" and res.records[0]["event_id"] == 1
    assert len(res.provenance.sha256) == 64 and res.provenance.size_bytes > 0


def test_import_event_log_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text(
        '{"timestamp": "t", "host": "h", "id": 7}\n{"timestamp": "t2", "host": "h"}\n',
        encoding="utf-8",
    )
    res = import_dataset(p, source=_src("event_log"), label_tier=LabelTier.SOURCE_PROVIDED)
    assert res.provenance.record_count == 2 and res.ok


def test_event_log_missing_timestamp_flagged(tmp_path: Path) -> None:
    p = tmp_path / "e.json"
    p.write_text(json.dumps([{"Hostname": "h"}]), encoding="utf-8")
    res = import_dataset(p, source=_src("event_log"), label_tier=LabelTier.SOURCE_PROVIDED)
    assert not res.ok
    assert any("timestamp" in i for i in res.issues)


def test_import_zeek_conn_log(tmp_path: Path) -> None:
    p = tmp_path / "conn.log"
    p.write_text(
        "#separator \\x09\n"
        "#fields\tts\tid.orig_h\tid.resp_h\tproto\n"
        "1.0\t10.0.0.1\t93.184.216.34\ttcp\n"
        "2.0\t10.0.0.2\t8.8.8.8\tudp\n",
        encoding="utf-8",
    )
    res = import_dataset(p, source=_src("network_capture"), label_tier=LabelTier.SOURCE_PROVIDED)
    assert res.ok and res.provenance.record_count == 2
    assert res.records[0]["dst"] == "93.184.216.34" and res.records[0]["proto"] == "tcp"


def test_pcap_reports_missing_dependency(tmp_path: Path) -> None:
    p = tmp_path / "capture.pcap"
    p.write_bytes(b"\xd4\xc3\xb2\xa1rawpcapbytes")
    res = import_dataset(p, source=_src("network_capture"), label_tier=LabelTier.SOURCE_PROVIDED)
    assert not res.ok
    assert any("dpkt" in i or "scapy" in i for i in res.issues)  # dependency blocker, not silent


def test_import_host_artifact_csv(tmp_path: Path) -> None:
    p = tmp_path / "autoruns.csv"
    p.write_text(
        "type,location,signer,points_to\n"
        "run_key,HKCU\\...\\Run\\x,,C:\\Users\\x\\AppData\\Roaming\\svc.exe\n",
        encoding="utf-8",
    )
    res = import_dataset(p, source=_src("host_artifact"), label_tier=LabelTier.SOURCE_PROVIDED)
    assert res.ok and res.records[0]["type"] == "run_key"
    assert res.records[0]["signer"] in (None, "")


def test_import_sigma_rule(tmp_path: Path) -> None:
    p = tmp_path / "rule.yml"
    p.write_text(
        "title: Suspicious PowerShell\n"
        "id: 11111111-1111-1111-1111-111111111111\n"
        "logsource:\n  product: windows\n  category: process_creation\n"
        "detection:\n  sel:\n    Image|endswith: \\powershell.exe\n  condition: sel\n"
        "level: high\n"
        "tags:\n  - attack.execution\n  - attack.t1059.001\n",
        encoding="utf-8",
    )
    res = import_dataset(p, source=_src("detection_test"), label_tier=LabelTier.SOURCE_PROVIDED)
    assert res.ok and res.records[0]["corpus"] == "sigma"
    assert "T1059.001" in res.records[0]["techniques"]


def test_import_atomic_test(tmp_path: Path) -> None:
    p = tmp_path / "T1059.yaml"
    p.write_text(
        "attack_technique: T1059.001\n"
        "display_name: PowerShell\n"
        "atomic_tests:\n"
        "  - name: Download Cradle\n"
        "    executor:\n      name: powershell\n",
        encoding="utf-8",
    )
    res = import_dataset(p, source=_src("detection_test"), label_tier=LabelTier.SOURCE_PROVIDED)
    assert res.ok and res.records[0]["corpus"] == "atomic_red_team"
    assert res.records[0]["techniques"] == ["T1059.001"]


def test_lineage_key_is_task_id_independent() -> None:
    a = {"task_id": "T1112.002", "techniques": ["T1059"], "iocs": ["evil.example"]}
    b = {"task_id": "T2013.001", "techniques": ["T1059"], "iocs": ["evil.example"]}
    c = {"task_id": "T1112.002", "techniques": ["T1486"], "iocs": ["evil.example"]}
    assert lineage_key(a) == lineage_key(b)  # same attack, different task IDs -> same lineage
    assert lineage_key(a) != lineage_key(c)  # different technique -> different lineage


def test_assert_no_lineage_crosses_split() -> None:
    ok = [("k1", "train"), ("k1", "train"), ("k2", "dev")]
    resolved = assert_no_lineage_crosses_split(ok)
    assert resolved == {"k1": "train", "k2": "dev"}
    with pytest.raises(LineageGuardError, match="crosses splits"):
        assert_no_lineage_crosses_split([("k1", "train"), ("k1", "test")])


def test_catalog_sources_are_licensed_and_permitted() -> None:
    assert CANDIDATE_SOURCES
    assert all(s.usage_permitted and s.license for s in CANDIDATE_SOURCES)
    assert candidate_by_kind("detection_test")  # at least Sigma + Atomic
    kinds = {s.kind for s in CANDIDATE_SOURCES}
    assert {"detection_test", "event_log", "network_capture"} <= kinds


def test_label_tiers_distinct() -> None:
    assert LabelTier.SOURCE_PROVIDED != LabelTier.INDEPENDENTLY_VERIFIED
    assert LabelTier("synthetic") == LabelTier.SYNTHETIC
