# T003 — Postgres metadata, repositories, Alembic

**Prereq:** T002 passes. Only local dev PostgreSQL integration, no live range.

## Files

`src/saber/persistence/{base,models,repositories,session}.py`, `alembic/`, `infra/compose/postgres.yml`, `tests/integration/persistence/`, Makefile target `test-integration`.

## Implementation instructions

1. Model only durable metadata: runs, episodes, cases, findings, evidence refs, rule proposals, response actions, approvals, transitions, audit, tool calls and report refs. Event payload storage is out of scope; the telemetry index is a separate adapter.
2. Use SQLAlchemy 2 typed declarations and Alembic migrations; use timezone-aware timestamps, UUID primary keys, FKs, unique idempotency constraints and constrained enum states.
3. Use explicit repositories/transactions; no SQL raw strings from LLM/query tools.
4. Add optimistic concurrency (`version`) to cases/actions and append-only transition history. Commit transition + audit transactionally.
5. Use a local, disposable Postgres Compose service with documented environment placeholders. No hardcoded credentials beyond obvious documented **development-only**, non-deployable sample values; prefer `DATABASE_URL` from environment.
6. Integration tests must check rollback, repeated migration from clean DB, foreign-key invalid references, uniqueness constraints and concurrent state mutations.
7. Do not put private ground-truth JSON in the metadata schema. Keep evaluator-only separation for T012.

## Acceptance

`make lint`, `make typecheck`, `make test`, `make test-integration` pass with local disposable DB. If Docker is unavailable, commit tests and mark integration **BLOCKED/not run** rather than treating mocks as a pass. Confirm migrations are reversible for all tables with data-safe semantics or document irreversibility before acceptance.
