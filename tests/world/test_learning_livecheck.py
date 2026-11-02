from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from saber.agents.gemini import KeyPool
from saber.world.key_layout import TeamKeyLayout
from saber.world.quota import TeamQuotaProvider
from saber.world.runtime import Runner
from saber.world.store import Store


def test_live_harness_exercises_gate_without_faking_an_improvement(tmp_path, capsys):
    script = Path(__file__).resolve().parents[2] / "scripts/smoke_learning_gemini.py"
    spec = importlib.util.spec_from_file_location("learning_livecheck", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def transport(url, key, body):
        data = json.loads(body["contents"][-1]["parts"][0]["text"])
        if "episode" in data:
            value = {
                "lesson": {
                    "failure_kind": "tool_contract",
                    "applicability": "When an observed tool requires prerequisites.",
                    "guidance": "Check the observed session or resource prerequisites before retrying the action.",
                    "limitations": "A successful prerequisite does not prove task completion.",
                    "evidence_ids": [data["episode"]["records"][0]["event_id"]],
                }
            }
        elif "work_request" in data["observation"]:
            value = {
                "actions": [
                    {
                        "tool": "call_app" if data["observation"]["logged_in"] else "login",
                        "args": {},
                    }
                ]
            }
        elif data["role"] == "monitor":
            value = {
                "actions": [
                    {"tool": "share", "args": {"text": "The referenced case was not available."}}
                ]
            }
        else:
            value = {"actions": [{"tool": "login", "args": {}}]}
        return 200, {
            "candidates": [{"content": {"parts": [{"text": json.dumps(value)}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10},
        }

    layout = TeamKeyLayout.from_pool(KeyPool(keys=[f"unit-secret-{i}" for i in range(602)]))
    store = Store(tmp_path)
    runner = Runner(store, module.config())
    provider = TeamQuotaProvider(
        store, layout, model="fake-livecheck", call_budget=24, transport=transport
    )
    try:
        raw_suite = json.loads(
            (script.parents[1] / "config/learning/client-session.json").read_text()
        )
        module.install_suite(store, raw_suite)
        result = module.exercise(runner, provider)
        assert result["pipeline_completed"] is True
        assert result["skill_improved_on_submitted_replay"] is False
        assert result["evaluations"][0]["status"] == "REJECTED"
        assert all(c["base_ok"] and c["candidate_ok"] for c in result["evaluations"][0]["checks"])
        assert store.get("meta", "llm_usage")["attempts"] == 18
        assert "unit-secret" not in capsys.readouterr().out
        assert set(result["plans"]) == {"client", "red", "blue"}
    finally:
        runner.close()
        store.close()
