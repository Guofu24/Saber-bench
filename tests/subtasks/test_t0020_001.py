"""Contract + golden tests for T0020.001 (independent scorer, DEV fixtures)."""

from __future__ import annotations

from tests.subtasks.harness import check_subtask


def test_t0020_001_contract() -> None:
    check_subtask("T0020.001")
