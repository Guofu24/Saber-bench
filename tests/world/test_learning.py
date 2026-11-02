from __future__ import annotations

import json

import pytest

from saber.world import learning
from saber.world.agents import action, llm_messages
from saber.world.models import Actor, default_config
from saber.world.runtime import Runner
from saber.world.store import Store


@pytest.fixture
def lab(tmp_path):
    cfg = default_config(1).model_copy(update={"learning_interval_ticks": 2})
    store = Store(tmp_path)
    runner = Runner(store, cfg)
    try:
        yield runner
    finally:
        runner.close()
        store.close()


def episode(runner):
    client = runner.clients["client-1"]
    failed = client.act(action("call_app"))
    assert failed["status"] == 401
    client.act(action("finish", reason="Review unsuccessful work."))
    return next(
        e for e in runner.store.items("learning-episodes").values() if e["actor_id"] == "client-1"
    )


def lesson(e):
    return {
        "failure_kind": "tool_contract",
        "applicability": "Before calling an application requiring a session.",
        "guidance": "Inspect your session and sign in if the application requires authentication.",
        "evidence_ids": [e["records"][0]["event_id"]],
        "limitations": "Authentication success does not prove application availability.",
    }


def test_private_experience_is_actual_scoped_and_not_shared(lab):
    e = episode(lab)
    assert e["summary"]["http_errors"] == 1
    assert e["version"] and e["reason"] == "finish"
    assert not {"effects", "plan", "raw_key"} & e.keys()
    with lab.store.transaction():
        p = learning.propose(lab.world, lab.world.actors["client-1"], e["id"], lesson(e))
    assert p["status"] == "AWAITING_SUITE"
    assert learning.prompt_version(lab.store, "client-user")["lessons"] == []
    assert "Authentication success" not in json.dumps(lab.clients["blue-monitor"].observe())
    with pytest.raises(ValueError, match="owned"):
        learning.propose(lab.world, lab.world.actors["blue-monitor"], e["id"], lesson(e))
    with pytest.raises(ValueError, match="Citations"):
        learning.propose(
            lab.world, lab.world.actors["client-1"], e["id"], lesson(e) | {"evidence_ids": [999999]}
        )


def test_skill_versions_survive_restart_and_do_not_change_mid_case(lab):
    e = episode(lab)
    with lab.store.transaction():
        proposal = learning.propose(lab.world, lab.world.actors["client-1"], e["id"], lesson(e))
    old = learning.prompt_version(lab.store, "client-user")
    candidate = learning.candidate_version(old, proposal)
    case_id = lab.clients["blue-monitor"].act(
        action("open_case", evidence_ids=lesson(e)["evidence_ids"])
    )["case_id"]
    with lab.store.transaction():
        lab.store.put("skill-versions", candidate["id"], candidate)
        lab.store.put("skill-heads", "client-user", candidate["id"])
    for _ in range(3):
        lab.world.advance()
    with lab.store.transaction():
        assert not learning.activate(lab.world)
    assert learning.prompt_version(lab.store, "client-user")["id"] == old["id"]
    learning.initialize(lab.world, {"client-user": "Changed checkout text."})
    assert learning.prompt_version(lab.store, "client-user")["base"] == old["base"]
    assert lab.store.get("cases", case_id)["status"] == "OPEN"
    text = json.dumps(
        llm_messages(Actor(id="u", team="client", role="person"), {}, pinned=candidate)
    )
    assert "Before calling an application" in text
    with lab.store.transaction():
        changed = dict(candidate) | {"base": "corrupt"}
        lab.store.put("skill-versions", candidate["id"], changed)
    with pytest.raises(ValueError, match="corrupt"):
        learning.version(lab.store, candidate["id"])
