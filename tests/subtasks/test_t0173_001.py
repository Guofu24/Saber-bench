"""Contract + golden tests for T0173.001 (independent scorer, DEV fixtures)."""

from __future__ import annotations

from tests.subtasks.harness import check_subtask


def test_t0173_001_contract() -> None:
    check_subtask("T0173.001")
