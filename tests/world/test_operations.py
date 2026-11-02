"""HTTP evidence access, durable case findings and scope/cutoff enforcement."""

from __future__ import annotations

import json

import pytest

from saber.world.agents import action
from saber.world.environment import World
from saber.world.models import default_config
from saber.world.service import LabServer
from saber.world.store import Store


@pytest.fixture
def lab(tmp_path):
    store = Store(tmp_path)
    world = World(store, default_config(2))
    server = LabServer(world)
    server.start()
    world.advance()
    try:
        yield world, server
    finally:
        server.close()
        store.close()


def test_query_pages_past_observation_window_with_cutoff_and_no_private_truth(lab):
    world, server = lab
    client, blue = server.client("client-1"), server.client("blue-hunter")
    expected = [client.act(action("browse"))["event_id"] for _ in range(63)]
    cutoff = world.tick
    world.advance()
    client.act(action("browse"))
    found, after = [], 0
    while True:
        page = blue.act(
            action(
                "query_events",
                world_id=world.store.get("meta", "world_id"),
                as_of_tick=cutoff,
                tool="browse",
                limit=17,
                after_id=after,
            )
        )
        assert page["status"] == 200
        found.extend(e["id"] for e in page["events"])
        assert "unauthorized_access" not in json.dumps(page)
        after = page["next_after_id"]
        if not page["has_more"]:
            break
    assert found == expected
    for bad in (
        {"as_of_tick": world.tick + 1},
        {"world_id": "another"},
        {"limit": 1000},
        {"after_id": True},
        {"sql": "SELECT * FROM effects"},
    ):
        args = {"world_id": world.store.get("meta", "world_id"), "as_of_tick": cutoff} | bad
        assert blue.act(action("query_events", **args))["status"] == 400
    assert server.client("red-recon").act(action("query_events"))["status"] == 403


def test_case_snapshots_survive_retention_and_reject_missing_future_ids(lab):
    world, server = lab
    blue = server.client("blue-monitor")
    event = server.client("client-1").act(action("browse"))["event_id"]
    case_id = blue.act(action("open_case", evidence_ids=[event]))["case_id"]
    for _ in range(10):
        server.client("client-1").act(action("browse"))
    world.store.archive(3, 1_000_000)
    args = {"world_id": world.store.get("meta", "world_id"), "as_of_tick": world.tick}
    result = blue.act(action("get_evidence", evidence_ids=[event], **args))
    assert result["evidence"][0]["id"] == event
    assert "effect" not in json.dumps(result)
    page = blue.act(action("query_events", **args))
    assert page["retention"]["truncated_before"] is True
    assert page["retention"]["archives_searchable"] is False
    assert blue.act(action("get_evidence", evidence_ids=[999999], **args))["status"] == 400
    args["as_of_tick"] = 0
    assert blue.act(action("get_evidence", evidence_ids=[event], **args))["status"] == 400
    assert blue.act(action("get_case", case_id=case_id))["case"]["revision"] == 0


def test_case_revision_evidence_findings_fp_close_and_reopen(lab):
    world, server = lab
    blue, lead = server.client("blue-monitor"), server.client("blue-lead")
    client = server.client("client-1")
    first = client.act(action("browse"))["event_id"]
    second = client.act(action("search", query="hello"))["event_id"]
    cid = blue.act(action("open_case", evidence_ids=[first]))["case_id"]
    assert (
        blue.act(
            action(
                "record_finding",
                case_id=cid,
                expected_revision=0,
                note="benign",
                classification="FP",
                evidence_ids=[second],
            )
        )["status"]
        == 400
    )
    result = blue.act(
        action(
            "append_evidence",
            case_id=cid,
            expected_revision=0,
            evidence_ids=[second],
            note="Follow-up query from same session.",
        )
    )
    assert result["revision"] == 1
    assert (
        blue.act(action("record_finding", case_id=cid, expected_revision=0, note="stale"))["status"]
        == 400
    )
    result = blue.act(
        action(
            "record_finding",
            case_id=cid,
            expected_revision=1,
            classification="FP",
            evidence_ids=[first, second],
            note="Ordinary portal usage.",
        )
    )
    assert result["revision"] == 2
    assert (
        lead.act(
            action("close_case", case_id=cid, disposition="false_positive", expected_revision=1)
        )["status"]
        == 409
    )
    assert (
        lead.act(
            action("close_case", case_id=cid, disposition="false_positive", expected_revision=2)
        )["status"]
        == 200
    )
    assert (
        blue.act(
            action(
                "append_evidence",
                case_id=cid,
                expected_revision=3,
                evidence_ids=[second],
                note="cannot edit closed",
            )
        )["status"]
        == 400
    )
    assert (
        blue.act(action("reopen_case", case_id=cid, expected_revision=3, note="review"))["status"]
        == 403
    )
    assert (
        lead.act(action("reopen_case", case_id=cid, expected_revision=3, note="New question."))[
            "status"
        ]
        == 200
    )
    case = blue.act(action("get_case", case_id=cid))["case"]
    assert case["status"] == "OPEN" and case["classification"] == "UNDETERMINED"
    assert len(case["worklog"]) == 4 and len(case["findings"]) == 1
    assert world.report()["metrics"]["case_fp"] == 1  # Analyst claims do not overwrite truth.


def test_added_attack_evidence_updates_private_scoring_without_exposing_labels(lab):
    world, server = lab
    blue = server.client("blue-monitor")
    first = server.client("client-1").act(action("browse"))["event_id"]
    cid = blue.act(action("open_case", evidence_ids=[first]))["case_id"]
    red = server.client("red-access")
    red.act(action("login"))
    second = red.act(action("read_document", document=f"work-{world.principals['client-1']}"))[
        "event_id"
    ]
    added = blue.act(
        action(
            "append_evidence",
            case_id=cid,
            expected_revision=0,
            evidence_ids=[second],
            note="Observed another principal reading private data.",
        )
    )
    assert added["status"] == 200
    assert world.report()["metrics"]["case_tp"] == 1
    assert world.report()["metrics"]["case_fp"] == 0
    contained = server.client("blue-ir").act(
        action("contain", case_id=cid, principal=world.principals["red-access"])
    )
    assert contained["verified"] is True
    assert world.report()["metrics"]["false_containments"] == 0
    assert "offenders" not in json.dumps(blue.act(action("get_case", case_id=cid)))


def test_new_evidence_invalidates_old_fp_verdict_before_closure(lab):
    _, server = lab
    blue, lead = server.client("blue-monitor"), server.client("blue-lead")
    client = server.client("client-1")
    first = client.act(action("browse"))["event_id"]
    cid = blue.act(action("open_case", evidence_ids=[first]))["case_id"]
    blue.act(
        action(
            "record_finding",
            case_id=cid,
            expected_revision=0,
            classification="FP",
            evidence_ids=[first],
            note="Ordinary browsing.",
        )
    )
    second = client.act(action("search", query="work"))["event_id"]
    blue.act(
        action(
            "append_evidence",
            case_id=cid,
            expected_revision=1,
            evidence_ids=[second],
            note="Additional activity needs assessment.",
        )
    )
    case = blue.act(action("get_case", case_id=cid))["case"]
    assert case["classification"] == "UNDETERMINED"
    assert case["findings"][0]["classification"] == "FP"  # Audit history is preserved.
    assert (
        lead.act(
            action("close_case", case_id=cid, disposition="false_positive", expected_revision=2)
        )["status"]
        == 409
    )
