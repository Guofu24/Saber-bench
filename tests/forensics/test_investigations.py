from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid

import pytest
from click.testing import CliRunner

from saber.cli.main import cli
from saber.forensics import vault as vault_module
from saber.forensics.tools import MAX_STEPS, execute, overview
from saber.forensics.vault import Vault
from saber.world.models import Actor

BLUE = Actor(id="blue-dfir", team="blue", role="dfir")


def ingest(tmp_path, text=None, fmt="csv", **kwargs):
    source = tmp_path / "input.log"
    if text is None:
        text = 'Timestamp,Computer,ProcessGuid,Image,ParentProcessId,ParentImage,EventRecordID,EventID,ProcessId,CommandLine\r\n2026-11-03T10:00:00.123456+07:00,pc-a,guid-a,agent.exe,4,system.exe,9001,22,42,"hello, world"\r\n'
    source.write_bytes(text.encode())
    with Vault(tmp_path / "world") as vault:
        manifest = vault.import_file(source, fmt, "Synthetic test evidence", **kwargs)
    return source, manifest


def call(tmp_path, tool, args=None, actor=BLUE, **kwargs):
    return execute(tmp_path / "world", actor, tool, args or {}, **kwargs)


def start(tmp_path, manifest):
    result = call(
        tmp_path,
        "forensic_open",
        {"source_ids": [manifest["id"]], "question": "Check evidence and gaps"},
    )
    assert result["status"] == 200, result
    return result["forensics"]["id"]


def test_preserves_original_offsets_exact_columns_timezone(tmp_path):
    source, manifest = ingest(tmp_path)
    sid = start(tmp_path, manifest)
    result = call(tmp_path, "forensic_query", {"session_id": sid})["forensics"]
    row = result["evidence"][0]
    assert row["fields"]["image"] == "agent.exe"
    assert row["fields"]["parent_image"] == "system.exe"
    assert row["fields"]["event_id"] == "22"
    assert row["fields"]["process_guid"] == "guid-a"
    assert row["fields"]["ts"] == "2026-11-03T03:00:00.123456+00:00"
    assert row["fields"]["timestamp_raw"].endswith("+07:00")
    raw = source.read_bytes()
    assert (
        hashlib.sha256(raw[row["offset"] : row["offset"] + row["length"]]).hexdigest()
        == row["sha256"]
    )
    with Vault(tmp_path / "world") as vault:
        assert vault.original(manifest["id"]).read_bytes() == raw
        assert vault.verify(manifest["id"])["integrity_verified"]
    assert manifest["sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "fmt,text,expected",
    [
        (
            "apache",
            '192.0.2.8 - - [03/Nov/2026:10:00:00 +0700] "GET /portal HTTP/1.1" 200 23\n',
            "2026-11-03T03:00:00.000000+00:00",
        ),
        (
            "iis",
            "#Fields: date time c-ip cs-uri-stem sc-status\n2026-11-03 10:00:00 192.0.2.8 /portal 200\n",
            "2026-11-03T10:00:00.000000+00:00",
        ),
        ("text", "Nov 3 10:00:00 pc-a routine event\n", None),
        (
            "text",
            "2026-11-03T10:00:00.12-04:00 routine event\n",
            "2026-11-03T14:00:00.120000+00:00",
        ),
    ],
)
def test_formats_and_unknown_dates(tmp_path, fmt, text, expected):
    _, manifest = ingest(tmp_path, text, fmt)
    sid = start(tmp_path, manifest)
    row = call(tmp_path, "forensic_query", {"session_id": sid})["forensics"]["evidence"][0]
    assert row["fields"]["ts"] == expected
    assert "compromised" not in json.dumps(row)
    assert bool(manifest["warnings"].get("unknown_timestamp")) == (expected is None)


def test_multiline_csv_and_long_original_are_preserved(tmp_path):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["UtcTime", "CommandLine"])
    writer.writerow(["2026-11-03T00:00:00", "first\nsecond," + "x" * 18000 + "TAIL"])
    source, manifest = ingest(tmp_path, buffer.getvalue())
    sid = start(tmp_path, manifest)
    row = call(tmp_path, "forensic_query", {"session_id": sid})["forensics"]["evidence"][0]
    assert row["fields"]["text_truncated"] is True
    assert manifest["warnings"]["search_text_truncated"] == 1
    with Vault(tmp_path / "world") as vault:
        assert vault.original(manifest["id"]).read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    "text",
    ["A,A\n1,2\n", "A,B\n1\n", "x" * 140000, 'A,B\n"unterminated'],
    ids=["duplicate", "missing", "oversize", "unclosed"],
)
def test_parse_failures_retain_source_and_report_partial(tmp_path, text):
    source, manifest = ingest(tmp_path, text)
    assert not manifest["indexed_complete"]
    assert manifest["warnings"]["parse_stopped"]
    assert source.exists()


def test_row_cap_and_fixed_offset(tmp_path, monkeypatch):
    monkeypatch.setattr(vault_module, "MAX_ROWS", 1)
    _, manifest = ingest(
        tmp_path, "Timestamp,Image\n2026-11-03T10:00:00,a\n2026-11-03T10:01:00,b\n", offset="+07:00"
    )
    assert manifest["records"] == 1
    assert not manifest["indexed_complete"]
    assert manifest["warnings"] == {"row_limit": 1}


def test_paging_literal_search_timeline_stats_and_process_scope(tmp_path):
    _, manifest = ingest(
        tmp_path,
        "Timestamp,Computer,ProcessGuid,ProcessId,Image\n2026-11-03T03:00:02Z,pc-a,guid-a,4,(a+)+$\n2026-11-03T03:00:01Z,pc-b,guid-b,4,good.exe\n",
    )
    sid = start(tmp_path, manifest)
    first = call(tmp_path, "forensic_query", {"session_id": sid, "mode": "timeline", "limit": 1})[
        "forensics"
    ]
    assert first["evidence"][0]["fields"]["host"] == "pc-b"
    second = call(
        tmp_path,
        "forensic_query",
        {"session_id": sid, "mode": "timeline", "limit": 1, "after": first["next_after"]},
    )["forensics"]
    assert second["evidence"][0]["fields"]["host"] == "pc-a"
    assert second["next_after"] is None
    literal = call(tmp_path, "forensic_query", {"session_id": sid, "text": "(a+)+$"})
    assert len(literal["forensics"]["evidence"]) == 1
    assert (
        call(tmp_path, "forensic_query", {"session_id": sid, "mode": "process", "pid": "4"})[
            "status"
        ]
        == 400
    )
    pivot = call(
        tmp_path,
        "forensic_query",
        {"session_id": sid, "mode": "process", "host": "pc-a", "process_guid": "guid-a"},
    )
    assert len(pivot["forensics"]["evidence"]) == 1
    groups = call(
        tmp_path, "forensic_query", {"session_id": sid, "mode": "stats", "group_by": "pid"}
    )
    assert groups["forensics"]["groups"] == [{"value": "4", "count": 2}]
    assert (
        call(tmp_path, "forensic_query", {"session_id": sid, "since": "2026-11-03T00:00:00"})[
            "status"
        ]
        == 400
    )


def test_roles_session_ownership_and_unseen_citations(tmp_path):
    _, manifest = ingest(tmp_path)
    sid = start(tmp_path, manifest)
    assert (
        call(tmp_path, "forensic_sources", actor=Actor(id="red", team="red", role="recon"))[
            "status"
        ]
        == 403
    )
    assert (
        call(
            tmp_path,
            "forensic_status",
            {"session_id": sid},
            actor=Actor(id="other", team="blue", role="dfir"),
        )["status"]
        == 400
    )
    finding = {
        "session_id": sid,
        "category": "observation",
        "text": "Unsubstantiated claim",
        "evidence_ids": [1],
    }
    assert call(tmp_path, "forensic_record", finding)["status"] == 400
    call(tmp_path, "forensic_query", {"session_id": sid})
    assert call(tmp_path, "forensic_record", finding)["status"] == 200


def test_restart_idempotence_and_review_does_not_verify_claims(tmp_path):
    _, manifest = ingest(tmp_path)
    args = {"source_ids": [manifest["id"]], "question": "Assess response evidence"}
    first = call(tmp_path, "forensic_open", args, request_id="job-1")
    assert call(tmp_path, "forensic_open", args, request_id="job-1") == first
    sid = first["forensics"]["id"]
    assert overview(tmp_path / "world", BLUE.id)["sessions"][0]["id"] == sid
    assert (
        call(
            tmp_path,
            "forensic_finish",
            {"session_id": sid, "disposition": "reviewed", "summary": "Model says done"},
        )["status"]
        == 400
    )
    queried = call(tmp_path, "forensic_query", {"session_id": sid})
    eid = queried["forensics"]["evidence"][0]["id"]
    for category in ("scope", "containment", "eradication", "recovery"):
        assert (
            call(
                tmp_path,
                "forensic_record",
                {
                    "session_id": sid,
                    "category": category,
                    "text": "Analyst claim; needs corroboration",
                    "evidence_ids": [eid],
                },
            )["status"]
            == 200
        )
    review = call(
        tmp_path,
        "response_review",
        {"session_id": sid, "residual_risk": "Semantic claims not independently verified"},
    )["forensics"]
    assert review["gaps"] == []
    assert review["response_verified"] is False
    done = call(
        tmp_path,
        "forensic_finish",
        {
            "session_id": sid,
            "disposition": "reviewed",
            "summary": "Documentation reviewed, not mitigation proof",
        },
    )
    assert done["forensics"]["state"] == "REVIEWED"
    assert done["forensics"]["response_verified"] is False
    assert call(tmp_path, "forensic_query", {"session_id": sid})["status"] == 400
    status = call(tmp_path, "forensic_status", {"session_id": sid})["forensics"]
    assert all(not f["semantic_verified"] for f in status["findings"])


def test_corruption_rejected_and_display_masks_ephemeral_marker(tmp_path):
    marker = uuid.uuid4().hex
    _, manifest = ingest(
        tmp_path, "2026-11-03T00:00:00Z Authorization: Bearer " + marker + "\n", "text"
    )
    sid = start(tmp_path, manifest)
    result = call(tmp_path, "forensic_query", {"session_id": sid})
    assert marker not in json.dumps(result)
    with Vault(tmp_path / "world") as vault:
        vault.original(manifest["id"]).write_bytes(b"altered")
        assert not vault.verify(manifest["id"])["integrity_verified"]
    assert call(tmp_path, "forensic_query", {"session_id": sid})["status"] == 400


def test_step_limit_stays_partial_and_cli_works(tmp_path):
    source, manifest = ingest(tmp_path)
    sid = start(tmp_path, manifest)
    with Vault(tmp_path / "world") as vault, vault.db:
        row = json.loads(
            vault.db.execute("SELECT data FROM sessions WHERE id=?", (sid,)).fetchone()[0]
        )
        row["steps"] = [{"tool": "forensic_query"}] * MAX_STEPS
        vault.db.execute("UPDATE sessions SET data=? WHERE id=?", (json.dumps(row), sid))
    assert call(tmp_path, "forensic_query", {"session_id": sid})["status"] == 400
    result = call(
        tmp_path,
        "forensic_finish",
        {"session_id": sid, "disposition": "partial", "summary": "Budget exhausted"},
    )
    assert result["forensics"]["state"] == "PARTIAL"
    runner = CliRunner()
    for args in (
        ["sources"],
        ["verify", "--source", manifest["id"]],
        ["sessions"],
        ["inspect", "--session", sid],
    ):
        response = runner.invoke(
            cli, ["world", "forensics", *args, "--out", str(tmp_path / "world")]
        )
        assert response.exit_code == 0, response.output
    response = runner.invoke(
        cli,
        [
            "lab",
            "forensics",
            "import",
            "--out",
            str(tmp_path / "range"),
            "--file",
            str(source),
            "--format",
            "csv",
            "--label",
            "fixture",
        ],
    )
    assert response.exit_code == 0, response.output
