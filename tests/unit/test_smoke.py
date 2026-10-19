"""T001 smoke: package metadata, interpreter version, no network."""

from __future__ import annotations

import sys

import saber


def test_package_metadata() -> None:
    assert saber.PACKAGE_NAME == "saber-bench"
    assert saber.__version__.count(".") == 2
    assert saber.CATALOG_SUBTASK_COUNT == 175
    assert saber.CATALOG_NICE_TASK_COUNT == 55
    assert saber.CATALOG_ARTIFACT_TYPE_COUNT == 40


def test_python_version() -> None:
    assert sys.version_info >= (3, 12)
