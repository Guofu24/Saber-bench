"""Real HTTP/state effects, role boundaries and independent evaluation."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from saber.world.agents import action, llm_messages, parse_plan
from saber.world.environment import World
from saber.world.models import default_config
from saber.world.service import LabServer, ToolClient
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


def read_private(world, server):
    red = server.client("red-access")
    red.act(action("login"))
    name = f"work-{world.principals['client-1']}"
    result = red.act(action("read_document", document=name))
    return red, name, result


def open_case(server, event_id):
    return server.client("blue-monitor").act(action("open_case", evidence_ids=[event_id]))[
        "case_id"
    ]


def test_silent_access_collects_actual_data_without_informing_client(lab):
    world, server = lab
    client = server.client("client-1")
    before = client.observe()
    red, name, result = read_private(world, server)
    assert result["status"] == 200 and "SYNTHETIC PRIVATE" in result["text"]
    assert client.observe()["notifications"] == before["notifications"] == []
    collected = red.act(action("collect", document=name))
    assert collected["status"] == 201
    report = world.report()
    assert report["metrics"]["collected_bytes"] == len(result["text"].encode())
    assert report["metrics"]["unauthorized_reads"] == 1
    assert "collection" not in server.client("blue-dfir").observe()


def test_patch_actually_denies_later_reads(lab):
    world, server = lab
    red, name, _ = read_private(world, server)
    patched = server.client("blue-content").act(action("patch", control="document_acl"))
    assert patched["verified"] is True
    assert red.act(action("read_document", document=name))["status"] == 403
    client = server.client("client-1")
    client.act(action("login"))
    assert client.act(action("read_document", document=name))["status"] == 200


def test_truth_is_based_on_access_rights_even_for_a_client(lab):
    world, server = lab
    client = server.client("client-2")
    client.act(action("login"))
    result = client.act(action("read_document", document=f"work-{world.principals['client-1']}"))
    assert result["status"] == 200
    assert world.report()["metrics"]["unauthorized_reads"] == 1


def test_collection_requires_successfully_read_bytes(lab):
    world, server = lab
    red = server.client("red-access")
    red.act(action("login"))
    result = red.act(action("collect", document=f"work-{world.principals['client-1']}"))
    assert result["status"] == 409
    assert world.report()["metrics"]["collected_bytes"] == 0


def test_response_requires_evidence_and_postcondition_not_detection_score(lab):
    world, server = lab
    red, _, event = read_private(world, server)
    cid = open_case(server, event["event_id"])
    lead, ir = server.client("blue-lead"), server.client("blue-ir")
    assert lead.act(action("close_case", case_id=cid))["status"] == 409
    wrong = ir.act(action("contain", case_id=cid, principal=world.principals["client-1"]))
    assert wrong["status"] == 400
    result = ir.act(action("contain", case_id=cid, principal=world.principals["red-access"]))
    assert result["verified"] is True
    assert red.act(action("browse"))["status"] == 403
    assert lead.act(action("close_case", case_id=cid))["status"] == 200
    for _ in range(world.config.response_ttl_ticks):
        world.advance()
    assert red.act(action("browse"))["status"] == 200


def test_false_containment_has_real_user_impact(lab):
    world, server = lab
    client = server.client("client-1")
    event = client.act(action("browse"))
    cid = open_case(server, event["event_id"])
    ir = server.client("blue-ir")
    ir.act(action("contain", case_id=cid, principal=world.principals["client-1"]))
    assert client.act(action("call_app"))["status"] == 403
    assert world.report()["metrics"]["false_containments"] == 1
    assert world.report()["metrics"]["case_fp"] == 1
    ir.act(action("release", principal=world.principals["client-1"]))
    assert client.act(action("browse"))["status"] == 200


def test_outage_restoration_and_explicit_notifications(lab):
    world, server = lab
    client = server.client("client-1")
    event = server.client("red-impact").act(action("disrupt"))
    assert event["status"] == 202
    assert client.act(action("browse"))["status"] == 503
    assert client.observe()["notifications"] == []
    cid = open_case(server, event["event_id"])
    ir = server.client("blue-ir")
    assert ir.act(action("restore", case_id=cid))["verified"] is True
    assert client.act(action("browse"))["status"] == 200
    ir.act(
        action(
            "notify", principal=world.principals["client-1"], text="Please recheck your session."
        )
    )
    assert client.observe()["notifications"][0]["acknowledged"] is False
    client.act(action("acknowledge"))
    assert client.observe()["notifications"][0]["acknowledged"] is True


def test_job_is_persistent_and_quarantine_changes_state(lab):
    world, server = lab
    red = server.client("red-impact")
    red.act(action("login"))
    event = red.act(action("register_job", name="lab-sync"))
    assert world.store.get("jobs", "lab-sync")["enabled"] is True
    cid = open_case(server, event["event_id"])
    result = server.client("blue-ir").act(action("quarantine", case_id=cid, name="lab-sync"))
    assert result["verified"] is True
    assert world.store.get("jobs", "lab-sync")["enabled"] is False
    assert red.act(action("register_job", name="../../outside"))["status"] == 400
    undo = server.client("blue-ir").act(action("unquarantine", case_id=cid, name="lab-sync"))
    assert undo["verified"] is True
    assert world.store.get("jobs", "lab-sync")["enabled"] is True
    assert server.client("blue-lead").act(action("close_case", case_id=cid))["status"] == 409


def test_expired_response_cannot_close_case(lab):
    world, server = lab
    _, _, event = read_private(world, server)
    cid = open_case(server, event["event_id"])
    server.client("blue-ir").act(
        action("contain", case_id=cid, principal=world.principals["red-access"])
    )
    for _ in range(world.config.response_ttl_ticks):
        world.advance()
    assert server.client("blue-lead").act(action("close_case", case_id=cid))["status"] == 409


def test_case_metrics_are_deduplicated_and_based_on_real_event_time(lab):
    world, server = lab
    _, _, event = read_private(world, server)
    world.advance()
    world.advance()
    cid = open_case(server, event["event_id"])
    assert open_case(server, event["event_id"]) == cid
    report = world.report()
    assert report["metrics"]["detected_incidents"] == 1
    assert report["mean_detection_ticks"] == 2


def test_http_denies_truth_and_other_roles_and_other_world_tokens(lab, tmp_path):
    world, server = lab
    for aid, tool in [
        ("client-1", "disrupt"),
        ("red-recon", "contain"),
        ("blue-monitor", "collect"),
    ]:
        assert server.client(aid).act(action(tool))["status"] == 403
    bad = ToolClient(server.url, "invented-token")
    assert bad.observe() == {"error": "authentication required"}
    blue = server.client("blue-monitor")
    for endpoint in (
        "/sealed/truth",
        "/report",
        "/v1/observe?through_tick=99999",
        "/config",
        "/../world.sqlite3",
    ):
        assert blue._request(endpoint) == {"error": "unknown tool endpoint"}
    store2 = Store(tmp_path / "another")
    other = LabServer(World(store2, default_config(2)))
    other.start()
    try:
        assert ToolClient(other.url, blue._token).observe() == {"error": "authentication required"}
    finally:
        other.close()
        store2.close()
    text = json.dumps(llm_messages(world.actors["blue-monitor"], blue.observe()))
    for forbidden in (
        "unauthorized_reads",
        "case_tp",
        "SYNTHETIC PRIVATE DOCUMENT",
        "collected_bytes",
        "red-access",
    ):
        assert forbidden not in text


def test_team_handoffs_are_private_and_future_evidence_rejected(lab):
    world, server = lab
    server.client("red-recon").act(action("share", text="PRIVATE RED PLAN"))
    assert "PRIVATE RED PLAN" in json.dumps(server.client("red-access").observe())
    assert "PRIVATE RED PLAN" not in json.dumps(server.client("blue-monitor").observe())
    assert "PRIVATE RED PLAN" not in json.dumps(server.client("client-1").observe())
    assert (
        server.client("blue-monitor").act(action("open_case", evidence_ids=[999999]))["status"]
        == 400
    )


def test_plan_validation_drops_unauthorized_tools_and_shells(lab):
    world, _ = lab
    plan, _ = parse_plan(
        world.actors["client-1"],
        json.dumps(
            {
                "actions": [
                    {"tool": "disrupt", "args": {}},
                    {"tool": "shell", "args": {"cmd": "anything"}},
                    {"tool": "browse", "args": {}},
                    {"tool": "browse", "extra": "bad"},
                ]
            }
        ),
    )
    assert [a.tool for a in plan] == ["browse"]


def test_oversized_request_rejected_without_changing_state(lab):
    world, server = lab
    before = world.report()["metrics"]["requests"]
    client = server.client("client-1")
    req = urllib.request.Request(
        server.url + "/v1/act",
        data=b"x" * 17000,
        headers={"Authorization": f"Bearer {client._token}"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        client._opener.open(req)
    assert exc.value.code == 413
    assert world.report()["metrics"]["requests"] == before
