"""T033: family-based split is a clean partition with no family/identifier leakage across splits."""

from __future__ import annotations

import pytest

from saber.benchmark.splits import (
    Split,
    assert_all_services_represented,
    assert_no_family_crosses_split,
    assert_partition_complete,
    build_split,
    collect_identifiers,
    fixture_seed,
)
from saber.subtasks import implemented_ids


@pytest.fixture(scope="module")
def assignment():  # noqa: ANN201
    return build_split()


@pytest.mark.security
def test_partition_is_complete_and_disjoint(assignment) -> None:  # noqa: ANN001
    assert_partition_complete(assignment)
    counts = assignment.counts()
    assert sum(counts.values()) == 175
    # Every split is non-empty and together they cover all 175.
    assert counts.get("train", 0) > 0 and counts.get("test", 0) > 0


@pytest.mark.security
def test_no_nice_family_crosses_split(assignment) -> None:  # noqa: ANN001
    assert_no_family_crosses_split(assignment)
    # Spot check: all three base variants of a family share one split.
    splits = {assignment.split_of(s) for s in ("T1112.001", "T1112.002", "T1112.003")}
    assert len(splits) == 1


@pytest.mark.security
def test_all_services_represented(assignment) -> None:  # noqa: ANN001
    assert_all_services_represented(assignment)


@pytest.mark.security
def test_split_is_deterministic() -> None:
    a = build_split()
    b = build_split()
    assert a.by_subtask == b.by_subtask


@pytest.mark.security
def test_fixture_seed_namespaced_by_split() -> None:
    base = 42
    seeds = {split: fixture_seed(base, split) for split in Split}
    assert len(set(seeds.values())) == 3  # disjoint per split


@pytest.mark.security
def test_no_identifier_overlap_across_splits(assignment) -> None:  # noqa: ANN001
    # For implemented subtasks, identifiers generated under the dev-split seed namespace must not
    # reappear under the test-split namespace (prevents recognisable-IOC leakage into the holdout).
    for sid in implemented_ids():
        dev_ids = collect_identifiers(sid, Split.DEV)
        test_ids = collect_identifiers(sid, Split.TEST)
        overlap = dev_ids & test_ids
        assert not overlap, (sid, sorted(overlap)[:5])
