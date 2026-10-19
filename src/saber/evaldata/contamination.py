"""Scenario-lineage contamination control across train/dev/test.

The existing family split (``saber.benchmark.splits``) partitions the 175 catalog subtasks by
family. That is not enough for real data: the SAME attack can appear under different NICE/subtask
IDs (e.g. a T1059 PowerShell scenario reused by a Monitoring and a Hunting subtask). If one copy
lands in dev and another in test, the test is contaminated.

A **lineage key** fingerprints the underlying attack, independent of the task ID: the sorted set of
ATT&CK technique IDs plus the sorted set of salient IOCs plus a hash of any detection logic. Two
scenarios that share that fingerprint get the same lineage key and must stay on one side of a split.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from typing import Any

_TECH_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
# Keys whose values are identifiers, not attack signatures — excluded so a technique-shaped
# task ID (e.g. "T1112.002") does not leak into the lineage and defeat task-ID independence.
_ID_KEYS = {"task_id", "subtask_id", "nice_id", "id", "episode_id", "rule_id"}


class LineageGuardError(AssertionError):
    """Raised when one attack lineage appears in more than one split."""


def _techniques(obj: Any) -> set[str]:
    """Pull ATT&CK technique IDs from anywhere in a scenario record."""
    found: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, str):
            found.update(m.group(0).upper() for m in _TECH_RE.finditer(x))
        elif isinstance(x, Mapping):
            for k, v in x.items():
                # Skip only a SCALAR identifier string (e.g. task_id="T1112.002"); still recurse
                # into nested structures so genuine techniques nested under an id-named dict/list
                # are not dropped.
                if str(k).lower() in _ID_KEYS and isinstance(v, str):
                    continue
                walk(v)
        elif isinstance(x, (list, tuple, set)):
            for v in x:
                walk(v)

    walk(obj)
    return found


def _iocs(record: Mapping[str, Any]) -> set[str]:
    raw = record.get("iocs") or record.get("indicators") or []
    out: set[str] = set()
    if isinstance(raw, Mapping):
        for v in raw.values():
            if isinstance(v, (list, tuple, set)):
                out.update(str(i).lower() for i in v)
            else:
                out.add(str(v).lower())
    elif isinstance(raw, (list, tuple, set)):
        out.update(str(i).lower() for i in raw)
    return out


def lineage_key(record: Mapping[str, Any]) -> str:
    """Stable fingerprint of a scenario's underlying attack (NOT its task ID).

    Combines ATT&CK techniques + salient IOCs + a hash of any detection logic. Deterministic and
    task-ID-independent, so the same attack under two subtask IDs maps to the same key.
    """
    techniques = sorted(_techniques(record))
    iocs = sorted(_iocs(record))
    logic = record.get("detection") or record.get("logic") or ""
    logic_s = str(logic)
    material = "|".join(
        ["T:" + ",".join(techniques), "I:" + ",".join(iocs), "L:" + logic_s.strip().lower()]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def assert_no_lineage_crosses_split(assignments: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Given (lineage_key, split) pairs, raise if any lineage appears in more than one split.

    Returns the resolved {lineage_key: split} map on success.
    """
    seen: dict[str, str] = {}
    for key, split in assignments:
        prior = seen.get(key)
        if prior is not None and prior != split:
            raise LineageGuardError(
                f"lineage {key} crosses splits: {prior!r} and {split!r} "
                "(same attack under different scenarios/task IDs)"
            )
        seen[key] = split
    return seen
