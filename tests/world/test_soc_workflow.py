"""Exercise specialist coordination through HTTP, without a model or external service."""

from __future__ import annotations

from contextlib import closing

from click.testing import CliRunner

from saber.agents.specialties import BLUE_SKILLS
from saber.cli.main import cli
from saber.world.agents import action, baseline
from saber.world.models import WorldConfig
from saber.world.runtime import Runner, WorldLock
from saber.world.store import Store


def specialist_config(tmp_path):
    result = CliRunner().invoke(
        cli,
        [
            "world",
            "init",
            "--out",
            str(tmp_path),
            "--clients",
            "2",
            "--blue-specialists",
            "--tick-seconds",
            "0.01",
        ],
    )
    assert result.exit_code == 0, result.output
    config = WorldConfig.model_validate_json((tmp_path / "config.json").read_text())
    assert {a.role for a in config.actors if a.team == "blue"} == set(BLUE_SKILLS)
    return config


def test_http_specialists_coordinate_evidence_response_and_client_recovery(tmp_path):
    cfg = specialist_config(tmp_path)
    store = Store(tmp_path)
    runner = Runner(store, cfg)
    clients = runner.clients

    def act(actor, tool, /, **args):
        result = clients[actor].act(action(tool, **args))
        assert result["status"] < 400, (actor, tool, result)
        return result

    try:
        runner.world.advance()
        # Actor decisions use public observations and HTTP results only.
        document = clients["client-1"].observe()["own_document"]
        act("client-1", "login")
        benign = act("client-1", "read_document", document=document)["event_id"]
        act("red-access", "login")
        attack = act("red-access", "read_document", document=document)["event_id"]
        outage = act("red-impact", "disrupt")["event_id"]
        obs = clients["blue-monitor"].observe()
        page = act(
            "blue-monitor",
            "query_events",
            world_id=obs["world_id"],
            as_of_tick=obs["tick"],
            tool="read_document",
        )
        assert {benign, attack} <= {e["id"] for e in page["events"]}
        cid = act(
            "blue-monitor",
            "open_case",
            evidence_ids=[attack, outage],
            summary="Cross-owner document access followed by service unavailability.",
        )["case_id"]
        task = act(
            "blue-lead",
            "create_task",
            case_id=cid,
            assignee="blue-dfir",
            specialty="dfir",
            objective="Reconstruct the observed application activity.",
        )["task"]
        task = act("blue-dfir", "accept_task", task_id=task["id"], expected_revision=0)["task"]
        artifact = act("blue-dfir", "capture_artifact", case_id=cid, kind="events")["artifact"]
        analysis = act("blue-malware", "analyze_artifact", artifact_id=artifact["id"])["analysis"]
        assert analysis["verdict"] == "not_assessed"
        timeline = act("blue-dfir", "investigate", case_id=cid)["timeline"]
        assert {attack, outage} <= {e["event_id"] for e in timeline}
        current = act("blue-dfir", "get_case", case_id=cid)["case"]
        act(
            "blue-dfir",
            "record_finding",
            case_id=cid,
            expected_revision=current["revision"],
            classification="TP",
            severity="high",
            evidence_ids=[attack, outage],
            note="The service returned another user's document and then became unavailable.",
            next_step="IR should contain the observed principals and restore service.",
        )
        act(
            "blue-dfir",
            "write_note",
            kind="decision",
            text="Preserved application evidence.",
            evidence_ids=[attack, outage],
        )
        act(
            "blue-dfir",
            "complete_task",
            task_id=task["id"],
            expected_revision=task["revision"],
            note="Application timeline and immutable snapshot captured; no OS evidence provided.",
            evidence_ids=[attack, outage],
        )
        conditions = [
            {"field": "tool", "op": "eq", "value": "read_document"},
            {"field": "detail.owner", "op": "ne_field", "value": "principal"},
            {"field": "detail.owner", "op": "ne", "value": "public"},
        ]
        tested = act(
            "blue-content",
            "test_rule",
            rule_id="cross-owner",
            conditions=conditions,
            positive_ids=[attack],
            negative_ids=[benign],
        )["test"]
        assert tested["result"] == {"tp": 1, "fp": 0, "fn": 0, "tn": 1}
        act("blue-content", "publish_rule", test_id=tested["id"], expected_version=0)
        act("blue-content", "patch", control="document_acl")
        for event in current["evidence"]:
            assert act("blue-ir", "contain", case_id=cid, principal=event["principal"])["verified"]
        assert act("blue-ir", "restore", case_id=cid)["verified"]
        runner.world.advance()
        act("client-1", "read_document", document=document)
        act("client-2", "login")
        act("client-2", "call_app")
        recovered = act("blue-recovery", "verify_recovery", case_id=cid)["recovery"]
        assert recovered["service_available"] and recovered["client_work_observed"]
        assert recovered["mitigation_active"] and not recovered["restricted_clients"]
        assert act("blue-platform", "telemetry_health")["adapters"]["application"] == "available"
        act("blue-lead", "close_case", case_id=cid)
        assert act("blue-lead", "get_case", case_id=cid)["case"]["status"] == "CLOSED"
        # Independent assertions, not data supplied to an actor.
        assert store.get("tasks", task["id"])["status"] == "DONE"
        assert store.get("notebook", "blue-dfir")[0]["evidence_ids"] == [attack, outage]
    finally:
        runner.close()
        store.close()


def test_full_roster_scripted_smoke_and_operator_resume(tmp_path):
    cfg = specialist_config(tmp_path)
    with closing(Store(tmp_path)) as store:
        runner = Runner(store, cfg)
        try:
            for _ in range(12):
                runner.step()
            assert len(store.items("memory")) == len(cfg.actors) == 17
            for role in ("malware", "intel"):
                assert store.items("artifact-analysis")
                assert any(
                    e["tool"] in {"capture_artifact", "analyze_artifact"}
                    for e in store.events(
                        through_tick=runner.world.tick,
                        limit=1000,
                        principal=runner.world.principals[f"blue-{role}"],
                    )
                )
            actor = runner.world.actors["blue-platform"]
            assert baseline(actor, runner.clients[actor.id].observe(), 0).tool == "telemetry_health"
            actor = runner.world.actors["blue-recovery"]
            obs = runner.clients[actor.id].observe()
            if any(c["status"] != "CLOSED" for c in obs["cases"]):
                assert baseline(actor, obs, 0).tool == "verify_recovery"
            assert (
                runner.clients["red-impact"].act(action("finish", reason="Exercise complete."))[
                    "status"
                ]
                == 200
            )
        finally:
            runner.close()
    invoke = CliRunner()
    args = ["world", "actor-resume", "--out", str(tmp_path), "--actor", "red-impact"]
    with WorldLock(tmp_path):
        assert invoke.invoke(cli, args).exit_code != 0
    result = invoke.invoke(cli, args)
    assert result.exit_code == 0, result.output
    with closing(Store(tmp_path)) as store:
        assert store.get("actor-control", "red-impact")["status"] == "ACTIVE"
        assert store.get("plans", "red-impact") == []
        assert store.get("meta", "tick") == 12
