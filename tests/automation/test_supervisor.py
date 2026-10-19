"""No Claude/auth/network calls: structural tests for the one-command supervisor."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_autonomous", ROOT / "scripts/run_autonomous.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SupervisorTests(unittest.TestCase):
    def test_coverage_count_and_uniqueness(self) -> None:
        items = module.work_items()
        self.assertEqual(len(items), 218)
        self.assertEqual(len({x["id"] for x in items}), 218)
        self.assertEqual(sum(x["kind"] == "domain" for x in items), 175)
        self.assertEqual(sum(x["kind"] == "engineering" for x in items), 38)
        self.assertEqual(sum(x["kind"] == "bridge" for x in items), 5)

    def test_all_spec_files_exist(self) -> None:
        for item in module.work_items():
            self.assertTrue((ROOT / item["spec"]).is_file(), item["id"])

    def test_reuse_before_install_in_prompt(self) -> None:
        item = next(x for x in module.work_items() if x["id"] == "T1112.001")
        prompt = module.build_prompt(item, 1)
        self.assertIn("REUSE", prompt)
        self.assertIn("independent", prompt)
        self.assertIn("tests/subtasks/test_t1112_001.py", prompt)

    def test_cli_has_guarded_permissions(self) -> None:
        cmd = module.claude_command("prompt", 1.0, 3, True)
        self.assertIn("dontAsk", cmd)
        self.assertNotIn("--max-budget-usd", cmd)
        api_cmd = module.claude_command("prompt", 1.0, 3, True, "api")
        self.assertIn("--max-budget-usd", api_cmd)
        self.assertIn("--strict-mcp-config", cmd)
        self.assertNotIn("--dangerously-skip-permissions", cmd)
        self.assertIn("--settings", cmd)

    def test_subscription_rejects_api_env_even_with_claude_login(self) -> None:
        auth = subprocess.CompletedProcess(
            ["claude", "auth", "status"],
            0,
            stdout=json.dumps({"authMethod": "claude.ai"}),
            stderr="",
        )
        with (
            patch.object(module.shutil, "which", return_value="/usr/bin/claude"),
            patch.object(module.subprocess, "run", return_value=auth),
            patch.dict(module.os.environ, {"ANTHROPIC_API_KEY": "dummy"}),
        ):
            with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY"):
                module.preflight(False, "subscription")

    def test_subscription_rejects_api_key_auth_method(self) -> None:
        auth = subprocess.CompletedProcess(
            ["claude", "auth", "status"], 0, stdout=json.dumps({"authMethod": "api_key"}), stderr=""
        )
        env = {
            k: v
            for k, v in module.os.environ.items()
            if k
            not in (
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_AUTH_TOKEN",
                "ANTHROPIC_BASE_URL",
                "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX",
                "CLAUDE_CODE_USE_FOUNDRY",
                "ANTHROPIC_FOUNDRY_API_KEY",
                "ANTHROPIC_VERTEX_PROJECT_ID",
                "AWS_BEARER_TOKEN_BEDROCK",
            )
        }
        with (
            patch.object(module.shutil, "which", return_value="/usr/bin/claude"),
            patch.object(module.subprocess, "run", return_value=auth),
            patch.dict(module.os.environ, env, clear=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "authMethod=api_key"):
                module.preflight(False, "subscription")


if __name__ == "__main__":
    unittest.main()
