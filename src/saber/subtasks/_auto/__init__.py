"""Archetype engine: implement any catalog subtask from its parsed source score contract.

A subtask that has no bespoke module under `saber.subtasks.t####_nnn` is served by `AutoSubtask`,
which reads the frozen catalog record's parsed score items and aggregate and composes a real,
executable scorer from the tested grading primitives, plus a seeded synthetic fixture with a hidden
label per scored field.

Honesty: these fixtures are STRUCTURAL synthetic DEV data, not domain-crafted or validated
scenarios. The scorer faithfully implements the parsed source formula (weights, gates, caps,
penalties, set/order/enum/numeric/cite/state/exec item kinds), so the subtask is genuinely
executable and testable (VERIFIED_OFFLINE), but it is never READY_BENCHMARK: that needs
independently validated gold data and expert adjudication of the scenario semantics.
"""

from saber.subtasks._auto.engine import AutoSubtask, auto_subtask_for

__all__ = ["AutoSubtask", "auto_subtask_for"]
