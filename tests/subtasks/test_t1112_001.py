"""Contract + golden tests for T1112.001 (independent scorer, DEV fixtures)."""

from __future__ import annotations

from tests.subtasks.harness import check_subtask


def test_t1112_001_contract() -> None:
    check_subtask("T1112.001")
