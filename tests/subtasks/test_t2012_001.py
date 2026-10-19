"""Contract + golden tests for T2012.001 (independent scorer, DEV fixtures)."""

from __future__ import annotations

from tests.subtasks.harness import check_subtask


def test_t2012_001_contract() -> None:
    check_subtask("T2012.001")
