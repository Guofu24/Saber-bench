from __future__ import annotations

import json
import threading

import pytest

from saber.agents.provider import LLMResponse
from saber.world import learning
from saber.world.agents import action
from saber.world.learning_eval import ReplaySuite, install_suite, rollback
from saber.world.learning_worker import Learner
from saber.world.models import Actor, default_config
from saber.world.runtime import Runner
from saber.world.store import Store


def suite():
    return {
        "skill": "client-user",
        "description": "Development next-action checks for session-aware application work.",
        "cases": [
            {
                "id": "missing-session",
                "split": "repair",
                "observation": {"logged_in": False},
                "expected": [{"tool": "login", "args": {}}],
            },
            {
                "id": "normal-work",
                "split": "regression",
                "observation": {"logged_in": True},
                "expected": [{"tool": "call_app", "args": {}}],
            },
            {
                "id": "known-outage",
                "split": "regression",
                "observation": {"logged_in": True, "service_down": True},
                "expected": [
                    {"tool": "wait", "args": {"ticks": 1, "reason": "Service unavailable."}}
                ],
            },
        ],
    }


class ReflectingProvider:
    model_id = "fake-learning-test"

    def __init__(self, *, regression=False, forged=False):
        self.calls = []
        self.regression, self.forged = regression, forged

    def generate(self, messages, *, max_tokens=1024):
        self.calls.append(messages)
        data = json.loads(messages[-1]["content"])
        if "episode" in data:
            e = data["episode"]
            response = {
                "lesson": {
                    "failure_kind": "tool_contract",
                    "applicability": "When an application requires an authenticated session.",
                    "guidance": "Inspect the session and sign in before attempting authenticated application work.",
                    "evidence_ids": [999999] if self.forged else [e["records"][0]["event_id"]],
                    "limitations": "A session alone does not establish service availability.",
                }
            }
        else:
            obs = data["observation"]
            learned = bool(obs.get("learned_lessons"))
            chosen = {"tool": "call_app", "args": {}}
            if obs.get("service_down"):
                chosen = {"tool": "wait", "args": {"ticks": 1, "reason": "Service unavailable."}}
            elif not obs.get("logged_in") and learned:
                chosen = {"tool": "login", "args": {}}
            if learned and self.regression and obs.get("logged_in"):
                chosen = {"tool": "login", "args": {}}
            response = {"actions": [chosen]}
        return LLMResponse(
            text=json.dumps(response), model_id=self.model_id, input_tokens=10, output_tokens=10
        )


@pytest.fixture
def lab(tmp_path):
    cfg = default_config(1)
    store = Store(tmp_path)
    runner = Runner(store, cfg)
    try:
        failed = runner.clients["client-1"].act(action("call_app"))
        assert failed["status"] == 401
        runner.clients["client-1"].act(
            action("write_note", kind="observation", text="own observation")
        )
        runner.clients["blue-monitor"].act(
            action("write_note", kind="hypothesis", text="OTHER_TEAM_PRIVATE")
        )
        runner.clients["client-1"].act(action("finish", reason="Review this task."))
        yield runner
    finally:
        runner.close()
        store.close()


def test_reflect_replay_publish_pin_and_rollback(lab):
    provider = ReflectingProvider()
    learner = Learner(lab.world, provider)
    old = learning.prompt_version(lab.store, "client-user")
    try:
        assert learner.process_one()
        proposal = next(iter(lab.store.items("learning-proposals").values()))
        assert proposal["status"] == "AWAITING_SUITE"
        assert learner.process_one() is False  # No suite means no self-approval.
        install_suite(lab.store, suite())
        assert learner.process_one()
        p = lab.store.get("learning-proposals", proposal["id"])
        assert p["status"] == "PUBLISHED"
        report = lab.store.get("learning-evaluations", p["evaluation_id"])
        assert report["passed"] and len(report["checks"]) == 6
        assert len(provider.calls) == 13
        assert "OTHER_TEAM_PRIVATE" not in json.dumps(provider.calls)
        assert all(
            "expected" not in json.loads(m[-1]["content"]).get("observation", {})
            for m in provider.calls
        )
        # Published does not mean mid-episode activation.
        assert learning.prompt_version(lab.store, "client-user")["id"] == old["id"]
        for _ in range(lab.config.learning_interval_ticks):
            lab.world.advance()
        with lab.store.transaction():
            assert learning.activate(lab.world)
        assert learning.prompt_version(lab.store, "client-user")["id"] == p["published_version"]
        rollback(lab.store, "client-user", old["id"])
        assert lab.store.get("skill-heads", "client-user") == old["id"]
        assert lab.store.get("skill-releases", p["published_version"])  # History survives.
        assert (
            lab.clients["client-1"].act(action("publish_lesson", proposal_id=p["id"]))["status"]
            == 403
        )
    finally:
        learner.close()


@pytest.mark.parametrize("regression,forged", [(True, False), (False, True)])
def test_bad_lessons_never_promote_or_retry_forever(lab, regression, forged):
    provider = ReflectingProvider(regression=regression, forged=forged)
    learner = Learner(lab.world, provider)
    old = lab.store.get("skill-heads", "client-user")
    try:
        install_suite(lab.store, suite())
        learner.flush()
        assert lab.store.get("skill-heads", "client-user") == old
        before = len(provider.calls)
        assert learner.process_one() is False
        assert len(provider.calls) == before
        if forged:
            assert next(iter(lab.store.items("learning-episodes").values()))["status"] == "DEFERRED"
        else:
            assert (
                next(iter(lab.store.items("learning-proposals").values()))["status"] == "REJECTED"
            )
    finally:
        learner.close()


def test_suite_requires_repair_and_independent_regression_inputs():
    raw = suite()
    raw["cases"][1]["observation"] = raw["cases"][0]["observation"]
    with pytest.raises(ValueError, match="distinct"):
        ReplaySuite.model_validate(raw)


def test_slow_reflection_does_not_block_clients(lab):
    entered, release = threading.Event(), threading.Event()

    class Slow(ReflectingProvider):
        def generate(self, messages, *, max_tokens=1024):
            entered.set()
            release.wait(timeout=5)
            return super().generate(messages, max_tokens=max_tokens)

    learner = Learner(lab.world, Slow())
    try:
        learner.poll()
        assert entered.wait(timeout=2)
        lab.world.advance()
        assert lab.clients["red-recon"].act(action("browse"))["status"] == 200
        assert not release.is_set()
    finally:
        release.set()
        learner.close()


def test_runner_automatically_reflects_failed_episodes_without_live_api(tmp_path):
    cfg = default_config(1).model_copy(
        update={
            "actors": [Actor(id="client-1", team="client", role="person")],
            "learning_interval_ticks": 1,
            "tick_seconds": 0.01,
        }
    )
    store = Store(tmp_path)
    provider = ReflectingProvider()
    runner = Runner(store, cfg, provider=provider)
    try:
        # A real HTTP failure before the loop, not a manufactured evaluator label.
        runner.clients["client-1"].act(action("call_app"))
        runner.run(ticks=3)
        assert store.items("learning-proposals")
        assert any("episode" in json.loads(m[-1]["content"]) for m in provider.calls)
    finally:
        runner.close()
        store.close()
