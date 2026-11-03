import json

import pytest
from click.testing import CliRunner

from saber.agents.provider import LLMResponse
from saber.cli.main import cli
from saber.lab.capabilities import configured_tools
from saber.lab.controller import Controller
from saber.lab.learning import RangeLearner, messages
from saber.lab.models import preset_spec
from saber.world import learning
from saber.world.learning_eval import install_suite, rollback


class ReflectAndReplay:
    def __init__(self):
        self.calls = []

    def generate_for(self, team, prompt, *, max_tokens):
        self.calls.append((team, prompt))
        if prompt[0]["content"].startswith("Review"):
            episode = json.loads(prompt[1]["content"])["episode"]
            value = {
                "lesson": {
                    "failure_kind": "tool_contract",
                    "applicability": "When authentication is missing or expired",
                    "guidance": "Use the login tool before retrying an authenticated document read.",
                    "limitations": "A denied request does not by itself prove compromise.",
                    "evidence_ids": [episode["records"][0]["event_id"]],
                }
            }
        else:
            obs = json.loads(prompt[1]["content"])["observation"]
            learned = "Advisory lessons" in prompt[0]["content"]
            value = {"tool": "login" if obs["needs_login"] and learned else "browse", "args": {}}
        return LLMResponse(
            text=json.dumps(value), model_id="fixture-model", input_tokens=10, output_tokens=10
        )


def test_range_capture_reflection_replay_publication_pinning_and_rollback(
    lab, tmp_path, monkeypatch
):
    spec, creds, *_ = lab
    root = tmp_path / "learning-control"
    provider = ReflectAndReplay()
    controller = Controller(spec, root, creds["controller"], {}, "http://unused", provider)
    actor = next(a for a in spec.actors if a.team == "client")
    skill = learning.actor_skill(controller.learning_world, actor)
    base = learning.prompt_version(controller.store, skill)
    assert base and not base["lessons"]
    with controller.store.transaction():
        eid = controller.store.event(1, "fixture", "read_document", "app", 401, {}, {})
        controller.store.put("meta", "tick", 1)
        learning.capture(
            controller.learning_world,
            actor,
            {"event_id": eid, "tool": "read_document", "status": 401},
            "app",
            skill,
        )
        episode = learning.seal(controller.learning_world, actor, "finish")
    learner = RangeLearner(controller)
    try:
        assert learner.process_one()
        proposal = next(iter(controller.store.items("learning-proposals").values()))
        assert proposal["episode_id"] == episode and proposal["status"] == "AWAITING_SUITE"
        suite = {
            "skill": skill,
            "description": "Trusted synthetic next-action checks for range login",
            "cases": [
                {
                    "id": "repair",
                    "split": "repair",
                    "observation": {"needs_login": True},
                    "expected": [{"tool": "login", "args": {}}],
                },
                {
                    "id": "browse_one",
                    "split": "regression",
                    "observation": {"needs_login": False, "turn": 1},
                    "expected": [{"tool": "browse", "args": {}}],
                },
                {
                    "id": "browse_two",
                    "split": "regression",
                    "observation": {"needs_login": False, "turn": 2},
                    "expected": [{"tool": "browse", "args": {}}],
                },
            ],
        }
        install_suite(controller.store, suite)
        assert learner.process_one()
        published = controller.store.get("skill-heads", skill)
        assert published != base["id"]
        assert learning.prompt_version(controller.store, skill)["id"] == base["id"]
        assert len(provider.calls) == 13  # Reflection plus base/candidate, 3 cases, 2 repeats.
        restarted = Controller(spec, root, creds["controller"], {}, "http://unused")
        assert learning.prompt_version(restarted.store, skill)["id"] == base["id"]
        restarted.close()
        assert all(team == "client" for team, _ in provider.calls)
        assert all('"expected"' not in prompt[1]["content"] for _, prompt in provider.calls)
        from saber.lab import controller as module

        monkeypatch.setattr(
            module, "request", lambda *a, **kw: (200, {"cases": [{"status": "OPEN"}]})
        )
        with controller.store.transaction():
            controller.store.put("meta", "tick", 31)
        controller.provider = None
        controller.learning_boundary()
        assert learning.prompt_version(controller.store, skill)["id"] == base["id"]
        monkeypatch.setattr(module, "request", lambda *a, **kw: (200, {"cases": []}))
        controller.learning_boundary()
        assert learning.prompt_version(controller.store, skill)["id"] == published
        assert (
            "Advisory lessons"
            in messages(actor, {}, learning.version(controller.store, published), [])[0]["content"]
        )
        rollback(controller.store, skill, base["id"])
    finally:
        learner.close()
        controller.close()
    result = CliRunner().invoke(
        cli, ["lab", "learning", "versions", "--out", str(root), "--skill", skill]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["released"] == base["id"]


@pytest.mark.parametrize(
    "role,tool", [("dfir", "analyze_sample"), ("ir", "run_playbook"), ("ir", "contain_domain_user")]
)
def test_learning_rejects_unavailable_tools_even_when_replay_expects_them(
    lab, tmp_path, role, tool
):
    spec, creds, *_ = lab
    spec.analysis.enabled = False
    spec.soar.enabled = False
    actor = next(a for a in spec.actors if a.role == role)
    assert tool not in configured_tools(actor, spec)
    assert tool in configured_tools(actor, preset_spec("windows-ad"))

    class DisabledToolProvider:
        def generate_for(self, team, prompt, **kwargs):
            allowed = (
                prompt[0]["content"].split("Allowed tools: ", 1)[1].split("\n", 1)[0].split(",")
            )
            assert tool not in allowed
            assert "consult_skill" in allowed
            observation = json.loads(prompt[1]["content"])["observation"]
            learned = "Advisory lessons" in prompt[0]["content"]
            action = tool if learned and observation.get("repair") else "query_events"
            return LLMResponse(
                text=json.dumps({"tool": action, "args": {}}),
                model_id="fixture",
                input_tokens=0,
                output_tokens=0,
            )

    controller = Controller(
        spec, tmp_path / "control", creds["controller"], {}, "unused", DisabledToolProvider()
    )
    learner = RangeLearner(controller)
    try:
        skill = learning.actor_skill(controller.learning_world, actor)
        base = learning.prompt_version(controller.store, skill)
        assert base
        controller.choose(actor, {"turn": 0, "result": {}})
        with controller.store.transaction():
            eid = controller.store.event(1, "fixture", "query_events", "collector", 200, {}, {})
            learning.capture(
                controller.learning_world,
                actor,
                {"event_id": eid, "tool": "query_events", "status": 200},
                "collector",
                skill,
            )
            episode = learning.seal(controller.learning_world, actor, "finish")
            assert episode
            proposal = learning.propose(
                controller.learning_world,
                actor,
                episode,
                {
                    "failure_kind": "tool_contract",
                    "applicability": "When choosing a response in the current deployment",
                    "guidance": "Check the deployment capabilities before selecting a tool.",
                    "limitations": "Unavailable tools cannot be executed in this deployment.",
                    "evidence_ids": [eid],
                },
            )
        suite_id = install_suite(
            controller.store,
            {
                "skill": skill,
                "description": "Reject unavailable tools from a stale replay suite",
                "cases": [
                    {
                        "id": "repair",
                        "split": "repair",
                        "observation": {"repair": True},
                        "expected": [{"tool": tool, "args": {}}],
                    },
                    *[
                        {
                            "id": f"regression-{i}",
                            "split": "regression",
                            "observation": {"turn": i},
                            "expected": [{"tool": "query_events", "args": {}}],
                        }
                        for i in (1, 2)
                    ],
                ],
            },
        )
        learner.evaluate(proposal, suite_id)
        assert controller.store.get("learning-proposals", proposal["id"])["status"] == "REJECTED"
        assert controller.store.get("skill-heads", skill) == base["id"]
    finally:
        learner.close()
        controller.close()
