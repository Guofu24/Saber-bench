"""Isolated range control: ports, a DEV directory-backed machine, and blocked hypervisor adapters.

Read-only observation and stateful response use two different permission profiles. The DEV
``LocalDirMachine`` lets state verifiers run offline against a directory tree; a real hypervisor
``RangeController`` / ``EmulationDriver`` fail closed until an isolated lab with verified network
isolation and operator approval exists (SECURITY.md H1-H4).
"""

from saber.range.blocked import BlockedEmulationDriver, BlockedRangeController
from saber.range.localdir import LocalDirMachine
from saber.range.ports import AttackVerifier, EmulationDriver, RangeController, SnapshotRef

__all__ = [
    "AttackVerifier",
    "BlockedEmulationDriver",
    "BlockedRangeController",
    "EmulationDriver",
    "LocalDirMachine",
    "RangeController",
    "SnapshotRef",
]
