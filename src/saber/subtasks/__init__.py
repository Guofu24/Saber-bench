"""Benchmark subtask modules: one package per T####.NNN (e.g. `saber.subtasks.t1112_001`).

Each module defines a `Subtask` class derived from `saber.subtasks._framework.SubtaskBase` with an
output model, a seeded DEV fixture builder, an independent scorer and golden cases.
"""

from __future__ import annotations

import importlib
import re
from functools import cache
from pathlib import Path

from saber.domain.errors import NotFound
from saber.subtasks._framework import SubtaskBase

_MODULE_RE = re.compile(r"^t(\d{4})_(\d{3})$")


def module_name(subtask_id: str) -> str:
    if not re.fullmatch(r"T\d{4}\.\d{3}", subtask_id):
        raise NotFound(f"not a benchmark subtask id: {subtask_id!r}")
    return "t" + subtask_id[1:].replace(".", "_")


def subtask_id_from_module(name: str) -> str:
    m = _MODULE_RE.match(name)
    if not m:
        raise NotFound(f"not a subtask module: {name!r}")
    return f"T{m.group(1)}.{m.group(2)}"


@cache
def load_subtask(subtask_id: str) -> SubtaskBase:
    name = module_name(subtask_id)
    try:
        mod = importlib.import_module(f"saber.subtasks.{name}")
    except ModuleNotFoundError as exc:
        raise NotFound(f"subtask {subtask_id} has no implementation module yet") from exc
    cls = getattr(mod, "Subtask", None)
    if cls is None or not issubclass(cls, SubtaskBase):
        raise NotFound(f"module saber.subtasks.{name} lacks a Subtask class")
    instance: SubtaskBase = cls()
    if subtask_id != instance.SUBTASK_ID:
        raise NotFound(f"module {name} declares {instance.SUBTASK_ID}, expected {subtask_id}")
    return instance


def implemented_ids() -> list[str]:
    here = Path(__file__).resolve().parent
    ids = []
    for child in here.iterdir():
        if child.is_dir() and _MODULE_RE.match(child.name) and (child / "__init__.py").is_file():
            ids.append(subtask_id_from_module(child.name))
    return sorted(ids)


__all__ = ["SubtaskBase", "implemented_ids", "load_subtask", "module_name"]
