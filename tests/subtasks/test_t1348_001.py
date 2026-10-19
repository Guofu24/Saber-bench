"""Contract + golden tests for T1348.001 (independent scorer, DEV fixtures)."""

from __future__ import annotations

from tests.subtasks.harness import check_subtask


def test_t1348_001_contract() -> None:
    check_subtask("T1348.001")
