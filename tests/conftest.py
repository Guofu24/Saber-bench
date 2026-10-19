"""Shared pytest configuration: offline, deterministic, no secrets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Tests must never run in lab mode or with a real provider key.
os.environ["SABER_ENV"] = "dev"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault("SABER_MODEL_PROVIDER", "stub")
os.environ.setdefault("SABER_RESPONSE_MODE", "dry-run")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT
