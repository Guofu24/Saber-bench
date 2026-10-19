# SABER developer targets. Each target runs a real tool; nothing prints a fake PASS.
# On Windows without GNU make, run the same commands via: python -m uv run <tool> ...
UV ?= uv

.PHONY: help setup lint format-check typecheck test test-security test-subtasks smoke catalog ci

help:
	@echo "setup         uv sync --locked (project-local .venv)"
	@echo "lint          ruff check src tests scripts"
	@echo "format-check  ruff format --check src tests"
	@echo "typecheck     mypy (strict) on src/saber"
	@echo "test          pytest (unit + security + subtasks, offline)"
	@echo "test-security pytest tests/security"
	@echo "test-subtasks pytest tests/subtasks"
	@echo "smoke         build/run/grade one DEV episode end-to-end"
	@echo "catalog       validate frozen 55/175/40 catalog"
	@echo "ci            lint + format-check + typecheck + test"

setup:
	$(UV) sync --locked

lint:
	$(UV) run ruff check src tests scripts

format-check:
	$(UV) run ruff format --check src tests

typecheck:
	$(UV) run mypy

test:
	$(UV) run pytest

test-security:
	$(UV) run pytest tests/security

test-subtasks:
	$(UV) run pytest tests/subtasks

smoke:
	$(UV) run saber smoke --subtask T1112.001 --seed 42

catalog:
	$(UV) run python scripts/validate_catalog.py

ci: lint format-check typecheck test
