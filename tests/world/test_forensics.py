import json

from saber.forensics.vault import Vault
from saber.world.agents import action, llm_messages
from saber.world.models import default_config
from saber.world.office_trace import trace
from saber.world.runtime import Runner
from saber.world.store import Store


def test_200_actor_office_keeps_events_when_forensic_previews_exceed_transport(tmp_path):
    from saber.world.environment import World
    from saber.world.models import Actor, WorldConfig
    from saber.world.office import snapshot
    from saber.world.runtime import atomic_json

    config = WorldConfig(
        actors=[Actor(id=f"blue-{i}", team="blue", role="dfir") for i in range(200)]
    )
    store = Store(tmp_path)
    try:
        world = World(store, config)
        with store.transaction():
            for actor in config.actors:
                eid = store.event(
                    0, world.principals[actor.id], "forensic_query", "session", 200, {}, {}
                )
                store.put(
                    "forensic-office",
                    actor.id,
                    [{"event_id": eid, "result": {"summary": "x" * 7800}}],
                )
        value = snapshot(
            store,
            config,
            world.report(),
            run_id="stress",
            profile="local",
            pending=set(),
            stopped=True,
            budget_exhausted=False,
        )
        atomic_json(tmp_path / "office.json", value)
        assert (tmp_path / "office.json").stat().st_size <= 250000
        assert len(value["actors"]) == len(value["trace"]["events"]) == 200
        assert any(e.get("forensics", {}).get("detail_omitted") for e in value["trace"]["events"])
        assert value["trace"]["events"][-1]["forensics"]["summary"] == "x" * 7800
        assert store.get("forensic-office", "blue-180")[0]["result"]["summary"] == "x" * 7800
    finally:
        store.close()


def test_world_http_investigation_visible_to_blue_and_office_only(tmp_path):
    source = tmp_path / "access.log"
    source.write_text('192.0.2.8 - - [03/Nov/2026:10:00:00 +0700] "GET /portal HTTP/1.1" 200 23\n')
    with Vault(tmp_path) as vault:
        imported = vault.import_file(source, "apache", "Local fixture")
    store = Store(tmp_path)
    runner = Runner(store, default_config(1))
    try:
        client = runner.clients["blue-dfir"]
        obs = client.observe()
        assert obs["forensics"]["source_count"] == 1
        assert "forensic_query" in obs["tools"]
        assert "forensics" not in runner.clients["client-1"].observe()
        assert runner.clients["red-recon"].act(action("forensic_sources"))["status"] == 403
        opened = client.act(
            action(
                "forensic_open",
                source_ids=[imported["id"]],
                question="Does HTTP 200 prove compromise?",
            )
        )
        sid = opened["forensics"]["id"]
        query = client.act(action("forensic_query", session_id=sid, text="/portal"))
        assert query["status"] == 200
        assert query["forensics"]["evidence"][0]["fields"]["status"] == "200"
        review = client.act(
            action(
                "response_review", session_id=sid, residual_risk="HTTP status alone is insufficient"
            )
        )
        assert "containment" in review["forensics"]["gaps"]
        done = client.act(
            action(
                "forensic_finish",
                session_id=sid,
                disposition="partial",
                summary="Need independent process and response evidence",
            )
        )
        assert done["forensics"]["state"] == "PARTIAL"
        exported = trace(store, runner.config, runner.world.tick)
        entry = next(e for e in exported["events"] if e["id"] == query["event_id"])
        assert entry["forensics"]["evidence"][0]["sha256"]
        assert entry["forensics"]["query"]["args"]["text"] == "/portal"
        assert "fields" in entry["forensics"]["evidence"][0]
        assert "forensic_query" in json.dumps(
            llm_messages(runner.world.actors["blue-dfir"], client.observe())
        )
        assert source.exists()
    finally:
        runner.close()
        store.close()
