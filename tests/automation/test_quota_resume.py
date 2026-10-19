"""Subscription quota tests run without a Claude CLI, account, or network."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("saber_autonomous_quota", ROOT / "scripts/run_autonomous.py")
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SubscriptionQuotaTests(unittest.TestCase):
    def test_only_error_usage_limit_triggers_wait(self):
        cases = [
            (3, "Usage limit reached, resets at 8am", True),
            (1, "You've reached your weekly limit", True),
            (1, "Rate limit exceeded", True),
            (0, "The user's analysis says usage limit reached", False),
            (2, "Cannot access approved SIEM API; missing credentials", False),
            (1, "Test assertion failed: account has no available logs", False),
            (1, "Authentication expired: please log in", False),
        ]
        for rc, msg, expected in cases:
            with self.subTest(msg=msg):
                self.assertEqual(runner.subscription_quota_exhausted(rc, msg), expected)

    def test_relative_reset_hint_and_default(self):
        self.assertEqual(runner.quota_recheck_seconds("Resets in 1 hour 15 minutes", 60), 4590)
        self.assertEqual(runner.quota_recheck_seconds("Resets in 3 minutes", 60), 270)
        self.assertEqual(runner.quota_recheck_seconds("resets at tomorrow 9AM", 45), 2700)
        self.assertEqual(runner.quota_recheck_seconds("Resets in 18 hours", 60), 7200)

    def test_one_launch_waits_retries_then_completes_without_new_work_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / ".saber-autonomous" / "logs"
            logs.mkdir(parents=True)
            item = {"id": "T001", "kind": "engineering", "phase": "foundation",
                    "spec": "tasks/T001-BOOTSTRAP.md", "environment": "development"}
            state = {"created_at": runner.utcnow(), "updated_at": runner.utcnow(),
                     "estimated_api_cost_usd": 0, "invocations": 0, "quota_rechecks": 0,
                     "items": {"T001": {"status": "PENDING", "attempts": 0,
                                        "reason": "", "last_update": ""}}}
            responses = [(3, 0.0, "Usage limit reached, resets in 2 minutes"),
                         (0, 0.0, "Work completed")]
            def mock_invoke(*args, **kwargs):
                return responses.pop(0)
            runner_code = [sys.argv[0], "--quota-recheck-minutes", "1", "--max-quota-wait-hours", "2"]
            with patch.object(runner, "ROOT", root), \
                 patch.object(runner, "STATE_DIR", root / ".saber-autonomous"), \
                 patch.object(runner, "STATE_FILE", root / ".saber-autonomous" / "state.json"), \
                 patch.object(runner, "RUN_LOGS", logs), \
                 patch.object(runner, "RECEIPTS", root / ".saber-autonomous" / "receipts"), \
                 patch.object(runner, "work_items", return_value=[item]), \
                 patch.object(runner, "initial_state", return_value=state), \
                 patch.object(runner, "environment_snapshot"), \
                 patch.object(runner, "preflight"), \
                 patch.object(runner, "invoke", side_effect=mock_invoke) as invocation, \
                 patch.object(runner, "verify", return_value=(True, "verified")) as verifier, \
                 patch.object(runner.time, "sleep") as sleeper, \
                 patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess(
                     ["python", "-m", "pytest", "-q"], 0, "all good", "")), \
                 patch.object(runner.sys, "argv", runner_code):
                self.assertEqual(runner.main(), 0)
                self.assertEqual(invocation.call_count, 2)
                self.assertEqual(verifier.call_count, 1)
                self.assertEqual(sleeper.call_count, 1)
                self.assertEqual(state["items"]["T001"]["attempts"], 1)
                self.assertEqual(state["items"]["T001"]["status"], "DONE_DEV")
                self.assertEqual(state["invocations"], 2)
                self.assertEqual(state["quota_rechecks"], 1)
                self.assertEqual(state["estimated_api_cost_usd"], 0.0)

    def test_wait_cap_stops_with_checkpoint_and_without_api(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            item = {"id": "T001", "kind": "engineering", "phase": "foundation",
                    "spec": "tasks/T001-BOOTSTRAP.md", "environment": "development"}
            state = {"created_at": runner.utcnow(), "updated_at": runner.utcnow(),
                     "estimated_api_cost_usd": 0, "invocations": 0,
                     "items": {"T001": {"status": "PENDING", "attempts": 0,
                                        "reason": "", "last_update": ""}}}
            with patch.object(runner, "ROOT", root), \
                 patch.object(runner, "STATE_DIR", root / ".saber-autonomous"), \
                 patch.object(runner, "STATE_FILE", root / ".saber-autonomous" / "state.json"), \
                 patch.object(runner, "RUN_LOGS", root / ".saber-autonomous" / "logs"), \
                 patch.object(runner, "work_items", return_value=[item]), \
                 patch.object(runner, "initial_state", return_value=state), \
                 patch.object(runner, "environment_snapshot"), \
                 patch.object(runner, "preflight"), \
                 patch.object(runner, "invoke", return_value=(3, 0, "Usage limit reached")), \
                 patch.object(runner, "quota_wait_elapsed_hours", return_value=200), \
                 patch.object(runner.time, "sleep") as sleeper, \
                 patch.object(runner.sys, "argv", [sys.argv[0]]):
                self.assertEqual(runner.main(), 6)
                sleeper.assert_not_called()
                self.assertEqual(state["items"]["T001"]["status"], "PAUSED_QUOTA")
                self.assertEqual(state["items"]["T001"]["attempts"], 0)
                self.assertEqual(state["quota_rechecks"], 1)

if __name__ == "__main__":
    unittest.main()
