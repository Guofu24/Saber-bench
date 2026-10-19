# T001 — Bootstrap Python monorepo and CI

**Status:** TODO  
**Dependencies:** none  
**Scope:** repo tooling only — no actual range, no alerts, no LLM provider, no offensive tools.

## Objective

The first Claude Code implementation task converts this planning kit into a working Python project with deterministic quality checks. Keep all planning markdown and Claude Code skills in place.

## Files to create/change

```text
pyproject.toml
uv.lock
Makefile
src/saber/__init__.py
src/saber/cli/__init__.py
src/saber/api/__init__.py
tests/conftest.py
tests/unit/test_smoke.py
.github/workflows/ci.yml
.gitignore
.env.example
README.md                    # preserve project intent, add setup commands
```

Allowed to add trivial `__init__.py` files and `tests/__init__.py` only when necessary.

## Implementation details

1. Create an installable Python 3.12+ project named `saber-bench` with source-layout package `saber` and a reproducible uv lockfile. Do not request live provider API keys. Version-pin dependencies through `uv.lock`.
2. Base dependencies **only as needed in T001**: e.g. Pydantic v2 for upcoming contracts, FastAPI as a later-stage known dependency; dev deps `pytest`, `ruff`, `mypy`, `httpx` when API test added. Avoid installing Wazuh/Proxmox client libraries prematurely.
3. Configure Ruff lint and format-check and mypy as strict as reasonably possible; never silence or remove warnings globally just to pass.
4. Build `Makefile` targets `help`, `setup`, `lint`, `format-check`, `typecheck`, `test`; each should execute a real relevant tool, not print a false PASS. Later tasks may add `test-integration`, `smoke`, `benchmark-dev`.
5. Add trivial `tests/unit/test_smoke.py` that asserts package metadata/known constant and Python version; deterministic/no external network.
6. Implement CI that installs verified uv release, syncs locked dependencies, and runs lint, typing, tests on a fresh environment. Avoid admin permissions and live API credentials.
7. `.gitignore` excludes `.env`, `scenarios/private/`, raw telemetry, lab private inventory, run artifacts, `__pycache__`, `.pytest_cache`, local venv, secrets and user credentials; `.env.example` contains only placeholders and documents `SABER_ENV=dev`.
8. `README` explains how to run and what is **not** implemented yet. Do not claim tested lab capabilities.

## Acceptance

From a clean checkout:

```bash
uv sync --locked
make lint
make format-check
make typecheck
make test
uv run python -c "import saber; print('OK')"
```

Expected: exit code 0 from each command. `git status` must not show local `.env` or secret directories. Run a negative check for a temporary file under `scenarios/private/` to confirm ignore rules. GitHub CI must call equivalent commands. Do not mark CI passed unless observed remotely; if no GitHub remote, state **CI not run remotely**.

## Out of scope

Postgres, Alembic, domain models, `/health`, UI, emulation, response and benchmark scoring.

## Claude Code first instruction

```text
Read CLAUDE.md and the T001 task. Inspect the workspace. Implement only
T001. Keep the preexisting plan and safety controls unchanged. Create
an installable `saber` package and deterministic CI. Execute every local
acceptance command. Report exact test output and any unverified items.
```

## Required final implementation report

- Code changes (path list)
- Tests run, commands and exit statuses
- Remaining risks / what is intentionally not yet implemented
- Confirmed no live infrastructure use
- T001 status = DONE | BLOCKED, with factual evidence
