"""Family-based train/dev/hidden-test split with leakage checks (engineering T033).

The scenario *family* is the NICE task: its subtasks (`T####.001/.002/.003/...`) share one
capability, the same artifact shapes, and often the same IOC/host vocabulary, so they must never be
split across train/dev/test. Assignment is therefore at the family level, deterministic from a
published seed, and stratified by primary service so every split covers all four services.

Episode fixtures in different splits also draw from disjoint seed namespaces (the split name is
mixed into the fixture seed) so that no high-entropy identifier recognisable in dev reappears in the
hidden test. The split assignment is metadata (which family is hidden), not an answer: per-episode
ground truth stays sealed regardless of the split.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from saber.catalog.loader import Catalog, default_catalog


class Split(StrEnum):
    TRAIN = "train"
    DEV = "dev"
    TEST = "test"


# Fractions are applied per service (stratified). Deterministic ordering by a keyed hash of the
# family id makes the partition stable and independent of catalog ordering.
DEFAULT_TEST_FRACTION = 0.30
DEFAULT_DEV_FRACTION = 0.15
SPLIT_SEED = "saber-split-v1"


@dataclass(frozen=True)
class SplitAssignment:
    seed: str
    by_family: dict[str, Split]
    by_subtask: dict[str, Split]

    def split_of(self, subtask_id: str) -> Split:
        return self.by_subtask[subtask_id]

    def families(self, split: Split) -> list[str]:
        return sorted(f for f, s in self.by_family.items() if s == split)

    def subtasks(self, split: Split) -> list[str]:
        return sorted(s for s, sp in self.by_subtask.items() if sp == split)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for s in self.by_subtask.values():
            out[s.value] += 1
        return dict(out)


def _rank(family: str, seed: str) -> float:
    digest = hashlib.sha256(f"{seed}:{family}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def build_split(
    catalog: Catalog | None = None,
    *,
    seed: str = SPLIT_SEED,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    dev_fraction: float = DEFAULT_DEV_FRACTION,
) -> SplitAssignment:
    cat = catalog or default_catalog()
    # Family -> its primary service (every subtask of a NICE task shares the service).
    family_service: dict[str, str] = {}
    family_members: dict[str, list[str]] = defaultdict(list)
    for s in cat.subtasks:
        family_service[s.nice_id] = s.service
        family_members[s.nice_id].append(s.id)

    by_service: dict[str, list[str]] = defaultdict(list)
    for family, service in family_service.items():
        by_service[service].append(family)

    by_family: dict[str, Split] = {}
    for families in by_service.values():
        ordered = sorted(families, key=lambda f: _rank(f, seed))
        n = len(ordered)
        n_test = max(1, round(n * test_fraction)) if n >= 3 else 0
        n_dev = max(1, round(n * dev_fraction)) if n - n_test >= 2 else 0
        for i, family in enumerate(ordered):
            if i < n_test:
                by_family[family] = Split.TEST
            elif i < n_test + n_dev:
                by_family[family] = Split.DEV
            else:
                by_family[family] = Split.TRAIN

    by_subtask: dict[str, Split] = {}
    for family, members in family_members.items():
        for sid in members:
            by_subtask[sid] = by_family[family]
    return SplitAssignment(seed=seed, by_family=by_family, by_subtask=by_subtask)


def fixture_seed(base_seed: int, split: Split) -> int:
    """Namespace a fixture seed by split so identifiers cannot collide across splits."""
    mixed = hashlib.sha256(f"{split.value}:{base_seed}".encode()).digest()
    return int.from_bytes(mixed[:4], "big")


# -------- leakage / contamination checks (raise on violation) ---------------------


class SplitContamination(Exception):
    pass


def assert_partition_complete(assignment: SplitAssignment, catalog: Catalog | None = None) -> None:
    cat = catalog or default_catalog()
    ids = {s.id for s in cat.subtasks}
    assigned = set(assignment.by_subtask)
    if assigned != ids:
        missing = ids - assigned
        extra = assigned - ids
        raise SplitContamination(
            f"split is not a complete partition (missing={missing}, extra={extra})"
        )


def assert_no_family_crosses_split(
    assignment: SplitAssignment, catalog: Catalog | None = None
) -> None:
    cat = catalog or default_catalog()
    family_splits: dict[str, set[Split]] = defaultdict(set)
    for s in cat.subtasks:
        family_splits[s.nice_id].add(assignment.by_subtask[s.id])
    crossing = {f: sp for f, sp in family_splits.items() if len(sp) > 1}
    if crossing:
        raise SplitContamination(f"NICE families cross splits: {crossing}")


def assert_all_services_represented(
    assignment: SplitAssignment, catalog: Catalog | None = None
) -> None:
    cat = catalog or default_catalog()
    svc_by_split: dict[Split, set[str]] = defaultdict(set)
    for s in cat.subtasks:
        svc_by_split[assignment.by_subtask[s.id]].add(s.service)
    services = {s.service for s in cat.subtasks}
    for split in (Split.TRAIN, Split.TEST):
        if svc_by_split[split] != services:
            raise SplitContamination(
                f"{split.value} split missing services: {services - svc_by_split[split]}"
            )


def collect_identifiers(
    subtask_id: str, split: Split, *, seeds: tuple[int, ...] = (1, 2, 3)
) -> set[str]:
    """Collect high-entropy identifiers (sha256 values, hosts, ips) from a subtask's fixtures."""
    from saber.episodes import build_episode
    from saber.subtasks import load_subtask

    st = load_subtask(subtask_id)
    found: set[str] = set()
    for base in seeds:
        seed = fixture_seed(base, split)
        for variant in st.VARIANTS:
            ep = build_episode(subtask_id, seed, variant)
            _scan(ep.bundle.public_inputs, found)
    return found


def _scan(obj: object, out: set[str]) -> None:
    import re

    # Only high-entropy identifiers (sha256) function as recognisable IOCs across splits. Benign
    # addresses drawn from the small RFC 5737 test pool collide by chance and are not leakage.
    hexre = re.compile(r"^[0-9a-f]{64}$")
    if isinstance(obj, dict):
        for v in obj.values():
            _scan(v, out)
    elif isinstance(obj, list | tuple):
        for v in obj:
            _scan(v, out)
    elif isinstance(obj, str) and hexre.match(obj):
        out.add(obj)
