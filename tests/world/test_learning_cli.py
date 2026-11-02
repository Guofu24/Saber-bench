from __future__ import annotations

import json
from types import SimpleNamespace

from click.testing import CliRunner

from saber.agents.provider import LLMResponse
from saber.cli.main import cli
from saber.world import learning
from saber.world.agents import action
from saber.world.models import WorldConfig
from saber.world.runtime import Runner, WorldLock
from saber.world.store import Store


def test_learning_cli_registers_suite_exports_and_retries_without_provider(tmp_path, monkeypatch):
    invoke = CliRunner()
    out = tmp_path / "world"
    assert invoke.invoke(cli, ["world", "init", "--out", str(out), "--clients", "1"]).exit_code == 0
    cfg = WorldConfig.model_validate_json((out / "config.json").read_text())
    store = Store(out)
    runner = Runner(store, cfg)
    try:
        event = runner.clients["client-1"].act(action("call_app"))["event_id"]
        runner.clients["client-1"].act(action("finish", reason="Review outcome."))
        episode = next(iter(store.items("learning-episodes").values()))
        with store.transaction():
            proposal = learning.propose(
                runner.world,
                runner.world.actors["client-1"],
                episode["id"],
                {
                    "failure_kind": "tool_contract",
                    "applicability": "Before authenticated application work.",
                    "guidance": "Check the session before calling an authenticated application.",
                    "limitations": "Login does not establish service availability.",
                    "evidence_ids": [event],
                },
            )
            episode["status"] = "DEFERRED"
            store.put("learning-episodes", episode["id"], episode)
    finally:
        runner.close()
        store.close()
    prefix = ["world", "learning"]
    install = prefix + [
        "install-suite",
        "--out",
        str(out),
        "--file",
        "config/learning/client-session.json",
    ]
    with WorldLock(out):
        assert invoke.invoke(cli, install).exit_code != 0
    assert invoke.invoke(cli, install).exit_code == 0
    result = invoke.invoke(cli, prefix + ["status", "--out", str(out)])
    assert result.exit_code == 0 and json.loads(result.output)["tick"] == 0
    result = invoke.invoke(cli, prefix + ["list", "--out", str(out)])
    assert json.loads(result.output)["proposals"][0]["status"] == "AWAITING_SUITE"
    assert json.loads(result.output)["episodes"][0]["id"] == episode["id"]
    result = invoke.invoke(
        cli, prefix + ["inspect", "--out", str(out), "--proposal", proposal["id"]]
    )
    assert json.loads(result.output)["proposal"]["lesson"]["evidence_ids"] == [event]
    target = tmp_path / "proposal.md"
    args = prefix + [
        "export",
        "--out",
        str(out),
        "--proposal",
        proposal["id"],
        "--file",
        str(target),
    ]
    assert invoke.invoke(cli, args).exit_code == 0
    assert "AWAITING_SUITE" in target.read_text()
    assert invoke.invoke(cli, args).exit_code != 0  # Never overwrite an existing review artifact.
    result = invoke.invoke(
        cli, prefix + ["retry", "--out", str(out), "--kind", "episode", "--id", episode["id"]]
    )
    assert result.exit_code == 0
    result = invoke.invoke(cli, ["world", "run", "--out", str(out), "--learning-only"])
    assert result.exit_code != 0 and "requires --llm" in result.output

    class OfflineReflection:
        model_id = "fake-cli-reflection"

        def generate(self, messages, *, max_tokens=1024):
            return LLMResponse(
                text='{"lesson":null}', model_id=self.model_id, input_tokens=1, output_tokens=1
            )

    monkeypatch.setattr(
        "saber.world.cli.TeamKeyLayout.from_file",
        lambda *a, **k: SimpleNamespace(counts=lambda: {}),
    )
    monkeypatch.setattr("saber.world.cli.TeamQuotaProvider", lambda *a, **k: OfflineReflection())
    (out / "STOP").write_text("keep this stop request")
    before = (
        json.loads((out / "report.json").read_text()) if (out / "report.json").exists() else None
    )
    result = invoke.invoke(
        cli, ["world", "run", "--out", str(out), "--learning-only", "--llm", "--call-budget", "20"]
    )
    assert result.exit_code == 0, result.output
    assert (out / "STOP").read_text() == "keep this stop request"
    assert json.loads((out / "learning.json").read_text())["tick"] == 0
    assert json.loads((out / "learning.json").read_text())["episodes"]["NO_LESSON"] == 1
    after = (
        json.loads((out / "report.json").read_text()) if (out / "report.json").exists() else None
    )
    assert after == before
