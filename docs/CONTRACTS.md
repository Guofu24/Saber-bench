> **Subtask-based v2 addendum:** Existing Event/Case/Run contracts are foundational and must be extended with a typed `SubtaskSpecV1`, per-subtask answer schemas, grader registry and `ArtifactRef` for HV-01…HV-40. See `docs/SUBTASK_CONTRACT.md`. Do not replace source score formulas with a generic incident F1 metric.

# SABER canonical contracts — v0.1

These are specification-level contracts for code generation, not executable code. Implement them as Pydantic v2 DTOs and SQLAlchemy tables. Prefer explicit schema versioning, e.g. `schema_version: 1` on persisted events and result JSON.

## Identifier, time and provenance rules

- Stable UUIDs: `scenario_id` (scenario definition), `run_id` (one experiment configuration), `episode_id` (one scenario realization), `event_id` (raw/normalized event identity), `case_id`, `finding_id`, `action_id`, `rule_version_id`.
- Every timestamp is timezone-aware UTC ISO 8601. Key distinctions: `occurred_at` (event host time), `ingested_at` (received by pipeline), `visible_at` (first available in permitted query index), `observed_at` (agent query time), `actioned_at` (IR execution).
- Store `raw_ref`, `raw_sha256`, `source`, `normalizer_version`, `dataset_split` (evaluator side only), `run_snapshot_id` (control-plane only).
- Deterministic fixtures use stable IDs and ordering. Runtime-created IDs can use UUID4 but must be stored in run manifest.

## Core data transfer objects

### NormalizedEvent

```json
{
  "schema_version": 1,
  "event_id": "<uuid>",
  "episode_id": "<uuid>",
  "occurred_at": "2026-10-17T09:00:00Z",
  "ingested_at": "2026-10-17T09:00:02Z",
  "visible_at": "2026-10-17T09:00:03Z",
  "host_id": "workstation-01",
  "source": "windows_sysmon",
  "category": "process_activity",
  "action": "process_start",
  "process": {"name": "powershell.exe"},
  "user": {"id": "lab-user"},
  "raw_ref": "s3://saber-raw/dev/<object>",
  "raw_sha256": "<64-hex-digits>",
  "normalizer_version": "1.0.0",
  "attributes": {}
}
```

This is a **minimal OCSF-inspired internal subset**, not a claim of full compliance with OCSF. Define explicit mappings and preserve original fields. A fake fixture may contain simplified attributes only in test/dev mode.

### Resolved EventQuery (internal gateway representation; LLM request omits `as_of`)

```json
{
  "episode_id": "<uuid>",
  "as_of": "2026-10-17T09:10:00Z",
  "time_from": "2026-10-17T09:00:00Z",
  "time_to": "2026-10-17T09:10:00Z",
  "hosts": ["workstation-01"],
  "categories": ["process_activity"],
  "filters": [{"field": "process.name", "operator": "eq", "value": "powershell.exe"}],
  "limit": 100,
  "cursor": null
}
```

In LLM-facing requests, do **not** accept client-supplied `as_of`. The trusted gateway attaches `as_of` from the benchmark clock. Enforce `time_to <= as_of`, `occurred_at <= as_of`, `visible_at <= as_of`, `limit <= max_allowed`, `episode_id == authenticated_episode`, allowlisted filter fields, request quotas, runtime budget and pagination in the **server**. `as_of` is server-clock-driven for online sessions, not arbitrary agent input.

### Finding / Case / Evidence

- `Finding`: `finding_id`, `episode_id`, `agent_id`, `hypothesis`, `verdict` (`malicious|benign|unknown`), `confidence` (`0..1`), `evidence_ids[]`, `affected_hosts[]`, `attack_techniques[]` (optional), `observed_at`, `rationale`, `model_usage_ref`.
- `Case`: `case_id`, `episode_id`, `status` (`open|investigating|escalated|resolved`), `finding_ids[]`, `timeline_event_ids[]`, `assignee_agent`, `created_at`, `resolved_at`, `version` (optimistic concurrency).
- `EvidenceRef`: `event_id`, `sha256`, `source`, `visible_at`, `raw_ref` (read only if permitted). A reference can be verified against EventStore; unsupported IDs fail evaluation rather than being trusted.

### DetectionRuleProposal

`rule_version_id`, `rule_kind` (`sigma|query`), `content`, `content_sha256`, `author_agent`, `status` (`draft|validated|rejected|approved|published`), `field_mapping_version`, `compiler_backend_version`, `evidence_ids[]`, `test_suite_id`, `created_at`. Never publish directly from a Blue agent.

### ResponseAction

`action_id`, `case_id`, `kind` (`isolate_lab_host|block_lab_address|disable_lab_account|collect_evidence`), `target`, `reason`, `supporting_evidence_ids[]`, `mode` (`dry_run|approved_lab`), `policy_decision`, `approval_id`, `status` (`proposed|approved|executed|verified|rolled_back|denied|expired|failed`), `expires_at`, `rollback_ref`, `result_ref`. Use deterministic adapter only for lab targets.

### ExperimentRun / Episode

- `ExperimentRun`: `run_id`, `experiment_config_hash`, `baseline_id`, `model_id`, `model_version`, `agent_architecture_version`, `prompt_hashes`, `code_commit`, `rule_registry_hash`, `provider_token_budget`, `tool_budget`, `wall_clock_budget_seconds`, `random_seed`, `started_at`, `finished_at`, `status`.
- `Episode`: `episode_id`, `run_id`, `scenario_id` (private control-plane relation), `environment_snapshot_hash`, `workload_profile_hash`, `telemetry_health`, `attack_verification`, `result_ref`, `status`.
- Agent DTO must not include `scenario_id` if this would reveal a scenario's ground-truth class. Use opaque `episode_id` at tool interface.

## API surface (implement progressively)

| Endpoint | Purpose | Consumer | Required task |
|---|---|---|---|
| `GET /health` | process status; avoid leaking secrets | dev | T004 |
| `GET /api/v1/events` | constrained event search with pagination | tool gateway | T009 |
| `GET /api/v1/cases/{case_id}` | permitted case/evidence references | agents, UI | T025 |
| `POST /api/v1/cases` | create validated case | gateway | T025 |
| `POST /api/v1/findings` | validate and store finding | gateway | T025 |
| `POST /api/v1/rules/proposals` | draft rule (not live deployment) | Content Agent | T029 |
| `POST /api/v1/rules/{id}/validate` | pinned compiler + dev fixture tests | Content | T029 |
| `POST /api/v1/responses/proposals` | dry-run proposal | IR | T030 |
| `POST /api/v1/responses/{id}/approve` | only authorized operator | operator | T030 |
| `POST /api/v1/responses/{id}/execute` | guarded side-effect action | approved lab only | T030 |
| `GET /api/v1/runs/{run_id}` | metadata, status and score refs | evaluator/UI | T011, T013 |
| `POST /api/v1/runs` | authenticated experiment creation | control-plane | T011 |
| `GET /api/v1/runs/{run_id}/report` | sealed report, only post-evaluation | operator | T013 |

OpenAPI is generated from actual Pydantic/FastAPI DTOs. Do not independently maintain divergent OpenAPI YAML.

## Run state machine

```text
CREATED → PREPARING → READY → RUNNING → OBSERVING → EVALUATING → COMPLETED
                     └─────────────┐
Any nonterminal state → FAILED (operational fault)
Any state with invalid ground truth / missing coverage → INVALID (excluded from detection scores)
```

Each state change stores previous, new, actor, UTC time, idempotency key and reason. Invalid transitions produce a typed error and are audited. `COMPLETED`, `FAILED`, `INVALID` are terminal. Retry only under a new idempotency key according to the retry policy; no implicit restart that reuses contaminated state.

## Response action state machine

```text
PROPOSED → APPROVED → EXECUTED → VERIFIED
         ↘ DENIED      ↘ ROLLED_BACK
Any pre-execution proposal → EXPIRED
Any attempted execution with confirmed error → FAILED (audit outcome, recovery decision)
```

Only the operator-authorized policy service may set `APPROVED`. A decision must be bound to action ID, target, environment, scope and TTL; an IR agent cannot self-approve. For detection-only track, execute is forbidden by design.

## Required SQL tables

`experiment_runs`, `episodes`, `scenario_registry`, `cases`, `findings`, `evidence_refs`, `rule_versions`, `response_actions`, `approval_records`, `audit_events`, `tool_calls`, `agent_turns`, `benchmark_reports`, `transition_history`. Ground truth stored in **separate evaluator-only storage**, not generally queryable through this DB credential. Unit/integration tests prove normal service roles cannot access private truth.

## Errors and idempotency

All APIs use normalized error fields `code`, `message`, `trace_id` without exposed stacktraces. Require idempotency key for state-changing run/action operations. Every timed-out tool call has an explicit failure record; unknown outcome is not silently retried when it may have a side effect.
