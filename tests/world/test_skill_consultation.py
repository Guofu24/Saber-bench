import pytest

from saber.world import learning
from saber.world.agents import action, llm_messages
from saber.world.models import default_config
from saber.world.runtime import Runner
from saber.world.store import Store


@pytest.fixture
def runner(tmp_path):
    store = Store(tmp_path)
    run = Runner(store, default_config(1))
    try:
        yield run
    finally:
        run.close()
        store.close()


@pytest.mark.parametrize(
    "actor_id,skill,topic",
    [
        ("blue-dfir", "soc-dfir", "memory-malware"),
        ("blue-ir", "soc-ir", "soc-orchestrator--case-record"),
        ("client-1", "client-user", "role-workflows"),
        ("red-recon", "redteam-initial-access", "campaign-planning"),
        ("red-impact", "redteam-post-exploitation", "redteam-initial-access--campaign-planning"),
    ],
)
def test_world_http_consultation_selects_complete_guide_without_new_capabilities(
    runner, actor_id, skill, topic
):
    client = runner.clients[actor_id]
    pin = learning.prompt_version(runner.store, skill)
    text = pin["references"][topic]["text"]
    actor = runner.world.actors[actor_id]
    assert text not in llm_messages(actor, client.observe(), pinned=pin)[0]["content"]
    listed = client.act(action("consult_skill"))
    assert listed["guidance_only"] and topic in listed["reference_topics"]
    result = client.act(action("consult_skill", topic=topic))
    assert result["status"] == 200 and result["guidance_only"]
    assert result["skill_reference"]["sha256"] == pin["references"][topic]["sha256"]
    assert text in llm_messages(actor, client.observe(), pinned=pin)[0]["content"]
    assert "pid" not in result and "artifact_id" not in result
    assert client.act(action("consult_skill", topic="../../private"))["status"] == 404
    assert client.act(action("consult_skill", topic=topic, path="other"))["status"] == 400
    assert client.act(action("consult_skill", topic=""))["status"] == 200
    assert text not in llm_messages(actor, client.observe(), pinned=pin)[0]["content"]
    for name in ("client-1", "red-recon"):
        assert (
            runner.clients[name].act(action("consult_skill", topic="memory-malware"))["status"]
            == 404
        )


def test_reference_snapshot_survives_checkout_change_and_is_inherited_by_lessons(runner):
    old = learning.prompt_version(runner.store, "soc-dfir")
    learning.initialize(
        runner.world,
        {"soc-dfir": "new checkout"},
        reference_libraries={"soc-dfir": {}},
    )
    assert learning.prompt_version(runner.store, "soc-dfir") == old
    candidate = learning.candidate_version(
        old,
        {
            "lesson": {
                "applicability": "When an image cannot be parsed.",
                "guidance": "Record the parser error and request compatible symbols.",
                "limitations": "This does not establish the absence of compromise.",
            }
        },
    )
    assert candidate["references"] == old["references"]
    selected = {"topic": "memory-malware", "version": old["id"]}
    from saber.agents.skill_library import guidance_prompt

    assert "--- Selected skill guidance" not in guidance_prompt(candidate, selected)
    with runner.store.transaction():
        runner.store.put("skill-versions", old["id"], old | {"references": {}})
    with pytest.raises(ValueError, match="corrupt"):
        learning.prompt_version(runner.store, "soc-dfir")
