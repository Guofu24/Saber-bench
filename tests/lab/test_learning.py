import json

from click.testing import CliRunner

from saber.agents.provider import LLMResponse
from saber.cli.main import cli
from saber.lab.controller import Controller
from saber.lab.learning import RangeLearner, messages
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
