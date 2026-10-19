# T002 — Domain contracts and validation

**Prereq:** T001 passes. This task must not add a DB or API implementation.

## Files

`src/saber/domain/{events,cases,runs,responses,query,errors}.py`, `tests/unit/domain/`, optional `docs/adr/0001-event-schema.md`.

## Implementation instructions

1. Read `docs/CONTRACTS.md` in full. Define stable enums and Pydantic v2 DTOs. All wire formats use `schema_version: 1`.
2. Event model includes `occurred_at`, `ingested_at`, `visible_at`, raw SHA256 and source. Reject naive datetimes. Normalize to UTC with explicit validation.
3. EventQuery accepts only documented fields/operators (`eq`, `in`, `gte`, `lte`, `contains` only for approved string fields); `limit` is bounded and excludes unbounded arbitrary backend DSL.
4. Finding requires `evidence_ids` with at least one ID for a positive malicious claim; empty evidence is permitted for benign/unknown only when explicitly captured in rationale.
5. ResponseAction validates target shape, type, approved modes and TTL; it must NOT contain free-form shell or executable command fields.
6. Run/Episode models distinguish invalid operational execution from undetected successful attack; do not expose sealed truth in a Blue DTO.
7. Test JSON serialization, strict unknown field rejection, invalid timezones, IDs, confidence bounds, forbidden tool parameters and backward-compatible schema snapshots.

## Required tests

- Construct one valid NormalizedEvent; JSON roundtrip succeeds.
- `visible_at` greater than `as_of` is rejected **at service query layer** (test DTO validation only for obvious invalid query bounds; the server-trusted clock is added in T009).
- Event with naive datetime rejected.
- Finding confidence outside `[0,1]` rejected.
- Positive finding without evidence rejected.
- Response action with arbitrary executable payload rejected.
- `attack_success_verified` does **not** appear on any Blue-facing response schema.

## Definition of done

`make lint && make typecheck && make test` pass, Pydantic schema snapshots tracked, no web/LLM/lab operations. Add no unnecessary general-purpose framework.
