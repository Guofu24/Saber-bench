from __future__ import annotations

import hashlib
import json

import pytest

from saber.world.agents import action
from saber.world.environment import World
from saber.world.models import Actor, default_config
from saber.world.service import LabServer
from saber.world.store import Store


@pytest.fixture
def lab(tmp_path):
    cfg = default_config(2)
    cfg = cfg.model_copy(
        update={
            "actors": cfg.actors
            + [
                Actor(id="blue-malware", team="blue", role="malware"),
                Actor(id="blue-recovery", team="blue", role="recovery"),
            ]
        }
    )
    store = Store(tmp_path)
    world = World(store, cfg)
    server = LabServer(world)
    server.start()
    world.advance()
    try:
        yield world, server
    finally:
        server.close()
        store.close()


def setup_case(world, server):
    client = server.client("client-1")
    red = server.client("red-access")
    client.act(action("login"))
    red.act(action("login"))
    document = f"work-{world.principals['client-1']}"
    benign = client.act(action("read_document", document=document))["event_id"]
    attack = red.act(action("read_document", document=document))["event_id"]
    cid = server.client("blue-monitor").act(action("open_case", evidence_ids=[attack]))["case_id"]
    return cid, document, benign, attack


def test_artifact_is_immutable_hashed_case_bound_and_native_analysis_never_faked(lab):
    world, server = lab
    cid, doc, _, _ = setup_case(world, server)
    dfir = server.client("blue-dfir")
    assert (
        dfir.act(
            action("capture_artifact", case_id=cid, kind="document", target="../../keys_pool.txt")
        )["status"]
        == 400
    )
    capture = dfir.act(action("capture_artifact", case_id=cid, kind="document", target=doc))[
        "artifact"
    ]
    aid = capture["id"]
    assert capture["scope"] == "application_snapshot"
    assert (
        dfir.act(action("capture_artifact", case_id=cid, kind="document", target=doc))["artifact"][
            "id"
        ]
        == aid
    )
    server.client("client-1").act(action("write_document", text="New content after acquisition."))
    chunks, offset = [], 0
    while True:
        page = dfir.act(action("read_artifact", artifact_id=aid, offset=offset, limit=30))
        chunks.append(page["text"])
        offset = page["next_offset"]
        if not page["has_more"]:
            break
    text = "".join(chunks)
    assert hashlib.sha256(text.encode()).hexdigest() == capture["sha256"]
    assert "New content after acquisition" not in text
    malware = server.client("blue-malware")
    result = malware.act(action("analyze_artifact", artifact_id=aid))["analysis"]
    assert result["verdict"] == "not_assessed" and result["sha256"] == capture["sha256"]
    native = malware.act(action("analyze_artifact", artifact_id=aid, engine="ghidra"))
    assert native["status"] == 409 and "analysis" not in native
    assert (
        server.client("red-access").act(action("read_artifact", artifact_id=aid))["status"] == 403
    )
    with world.store.transaction():
        item = world.store.get("artifacts", aid)
        item["text"] = "corrupt"
        world.store.put("artifacts", aid, item)
    assert dfir.act(action("read_artifact", artifact_id=aid))["status"] == 400


def test_rule_test_publish_live_match_and_rollback_use_actual_event_fields(lab):
    world, server = lab
    _, doc, benign, attack = setup_case(world, server)
    content = server.client("blue-content")
    conditions = [
        {"field": "tool", "op": "eq", "value": "read_document"},
        {"field": "status", "op": "eq", "value": 200},
        {"field": "detail.owner", "op": "ne_field", "value": "principal"},
        {"field": "detail.owner", "op": "ne", "value": "public"},
    ]
    corpus = dict(rule_id="cross-owner", positive_ids=[attack], negative_ids=[benign])
    bad = content.act(action("test_rule", conditions=conditions[:2], **corpus))["test"]
    assert bad["result"]["fp"] == 1
    assert (
        content.act(action("publish_rule", test_id=bad["id"], expected_version=0))["status"] == 409
    )
    good = content.act(action("test_rule", conditions=conditions, **corpus))["test"]
    assert good["result"] == {"tp": 1, "fp": 0, "fn": 0, "tn": 1}
    assert good["label_source"] == "caller_supplied_not_gold"
    published = content.act(action("publish_rule", test_id=good["id"], expected_version=0))["rule"]
    assert published["version"] == 1
    next_event = server.client("red-access").act(action("read_document", document=doc))["event_id"]
    assert any(
        f"Rule cross-owner matched event {next_event}" in m["text"]
        for m in content.observe()["team_messages"]
    )
    content.act(action("publish_rule", test_id=good["id"], expected_version=1))
    restored = content.act(
        action("rollback_rule", rule_id="cross-owner", version=1, expected_version=2)
    )["rule"]
    assert restored["version"] == 3 and restored["restored_from"] == 1
    assert (
        content.act(action("rollback_rule", rule_id="cross-owner", version=1, expected_version=2))[
            "status"
        ]
        == 400
    )
    assert (
        server.client("blue-dfir").act(
            action("publish_rule", test_id=good["id"], expected_version=3)
        )["status"]
        == 403
    )


def test_recovery_requires_work_from_each_affected_client_and_reports_unmeasured_integrity(lab):
    world, server = lab
    outage = server.client("red-impact").act(action("disrupt"))["event_id"]
    cid = server.client("blue-monitor").act(action("open_case", evidence_ids=[outage]))["case_id"]
    ir = server.client("blue-ir")
    check = server.client("blue-recovery")
    assert (
        check.act(action("verify_recovery", case_id=cid))["recovery"]["service_available"] is False
    )
    assert ir.act(action("restore", case_id=cid))["verified"] is True
    before = check.act(action("verify_recovery", case_id=cid))["recovery"]
    assert before["service_available"] is True and before["client_work_observed"] is False
    world.advance()
    server.client("client-1").act(action("login"))
    server.client("client-1").act(action("call_app"))
    assert (
        check.act(action("verify_recovery", case_id=cid))["recovery"]["client_work_observed"]
        is False
    )
    server.client("client-2").act(action("login"))
    server.client("client-2").act(action("call_app"))
    after = check.act(action("verify_recovery", case_id=cid))["recovery"]
    assert after["client_work_observed"] and after["mitigation_active"]
    assert after["integrity"] == "not_measured" and after["restricted_clients"] == []
    assert len(after["evidence_ids"]) == 2


def test_health_reports_observation_limits_without_exposing_evaluator(lab):
    _, server = lab
    health = server.client("blue-monitor").act(action("telemetry_health"))
    assert health["adapters"]["application"] == "available"
    assert health["adapters"]["volatility"] == "not_configured"
    assert "effects" not in json.dumps(health)
    assert (
        server.client("blue-monitor").act(action("telemetry_health", path="C:/"))["status"] == 400
    )
