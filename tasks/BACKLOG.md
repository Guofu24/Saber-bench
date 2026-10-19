> **v2 warning:** This is the ENGINEERING BACKLOG (38 development PRs), not the user-provided 175 SOC benchmark subtasks. For benchmark delivery open `tasks/DOMAIN_BACKLOG.md` and one `tasks/subtasks/T####.NNN.md`.

# SABER coding backlog — 38 reviewable tasks

Use this as a **task ledger**, not as permission to execute every task in one session. A single task is the maximum implementation scope unless an explicit operator decision changes it. Tasks have dependencies; later tasks must not be marked complete because a mock returns the expected result.

| Milestone | Tasks | High-level exit gate |
|---|---|---|
| M0 Foundation | T001–T005 | `uv run pytest`, typing, migrations, auth/audit |
| M1 Offline vertical slice | T006–T014 | seeded replay → time-guarded search → deterministic grade → manifest/report |
| M2 Isolated range | T015–T024 | safe provisioning, real benign logs, approved emulation verification, clean reset |
| M3 SOC agents | T025–T032 | bounded gateway, 4 specialists, coordinator, comparable baselines |
| M4 Evaluation/release | T033–T038 | hidden family split, separate tracks, rigorous reports, security gates |

## Common Definition of Done (every task)

1. Code only requested scope and preserve backward-compatible typed interfaces.
2. Commit reviewable tests, including relevant negative/security tests and no secrets.
3. Run applicable lint, type, unit tests, migration/integration tests; paste actual exit statuses.
4. Validate no hidden truth or unapproved infrastructure command exposure.
5. Report changed files, assumptions, limitations, performance/latency impact, and follow-up TODOs.
6. Do not declare “DONE” unless all checkable criteria pass; use BLOCKED for unavailable lab/provider checks.

## Exact task specs

### T001 — Bootstrap repository and CI
**Dependencies:** `—`.
**Primary paths:** `pyproject.toml, uv.lock, Makefile, src/saber/__init__.py, tests/unit/test_smoke.py, .github/workflows/ci.yml, .gitignore, .env.example`.
**Implement:** Create installable single-package Python workspace, uv dependencies, Ruff/mypy/pytest, deterministic local tests and CI; no business logic or live infrastructure.
**Acceptance:** Clean checkout installs; `make lint`, `make typecheck`, `make test` pass; `.env` and scenario private directory are ignored; no real credentials.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T002 — Canonical DTOs and schema validation
**Dependencies:** `T001`.
**Primary paths:** `src/saber/domain/{events,cases,runs,responses,query}.py, tests/unit/domain/`.
**Implement:** Implement Pydantic v2 contracts and enums from CONTRACTS.md, timestamp and ID validation, evidence references, strict extra-field behavior and JSON schema snapshots.
**Acceptance:** Timezone-naive inputs fail; unknown transition values fail; non-UUID IDs fail where specified; schema snapshots are deterministic.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T003 — Durable metadata and migrations
**Dependencies:** `T002`.
**Primary paths:** `src/saber/persistence/{models,repositories,db}.py, alembic/, infra/compose/postgres.yml, tests/integration/persistence/`.
**Implement:** Create SQLAlchemy 2 tables for runs, episodes, cases, findings, actions, rules, audit and histories; apply migrations; transactional optimistic locks.
**Acceptance:** Upgrade/downgrade on ephemeral DB, FK and unique constraints, concurrent update race and rollback tests pass.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T004 — Minimal API and CLI shell
**Dependencies:** `T001,T002`.
**Primary paths:** `src/saber/api/{app,routes}.py, src/saber/cli/main.py, tests/integration/api/`.
**Implement:** Implement app factory, `/health`, versioned API namespace, typed errors, config loader and initial `saber --help`; no unguarded infra calls.
**Acceptance:** OpenAPI generates, health returns 200, invalid payload returns structured 4xx, `uv run saber --help` works.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T005 — Security policy, auth and audit core
**Dependencies:** `T003,T004`.
**Primary paths:** `src/saber/security/{policy,auth,audit}.py, tests/security/test_policy.py, docs/adr/`.
**Implement:** Implement dev identity plus role-based service scopes, policy deny-by-default, audit record writer, protected endpoints and operator authorization scaffolding.
**Acceptance:** Blue agent cannot call evaluator/control endpoints; unauthorized action denies and audits; no bypass via missing role.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T006 — Development-only fixture generator
**Dependencies:** `T002`.
**Primary paths:** `tests/fixtures/events/, src/saber/telemetry/fixtures.py, scenarios/dev/`.
**Implement:** Generate a time-stamped benign and malicious-looking event sequence with deterministic seed, visibly marked DEV_FIXTURE metadata; labels stored evaluator side.
**Acceptance:** Same seed and profile produce identical event IDs/order/hash; both benign and attack-shaped cases exist; fixtures cannot be loaded in lab mode.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T007 — Telemetry normalizer and coverage checker
**Dependencies:** `T002,T006`.
**Primary paths:** `src/saber/telemetry/{normalize,coverage}.py, tests/unit/telemetry/`.
**Implement:** Normalize Windows Event/Sysmon, Linux audit/auth, and generic app/network envelopes to internal schema; preserve raw references and ingest gaps.
**Acceptance:** Known fixtures map with correct fields, UTC normalization and original payload ref; malformed lines quarantined; per-source coverage report.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T008 — FakeEventStore with temporal replay
**Dependencies:** `T006,T007`.
**Primary paths:** `src/saber/telemetry/{ports,fake_store}.py, tests/unit/telemetry/test_fake_store.py`.
**Implement:** Build backend Protocol and deterministic in-memory store supporting episode filtering, pagination, cursor and visibility time.
**Acceptance:** Future `visible_at` is not observable; pagination is stable; no cross-episode leakage; seeded replay matches hashes.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T009 — Constrained EventQuery gateway
**Dependencies:** `T004,T005,T008`.
**Primary paths:** `src/saber/telemetry/{query,service}.py, src/saber/api/routes/events.py, tests/security/test_query_guards.py`.
**Implement:** Implement safe field/operator DSL, server-generated as-of and signed page cursors, quotas, policy checks and resource bounds.
**Acceptance:** Future queries denied; arbitrary SQL/OpenSearch DSL denied; unknown filter fields denied; limit cap enforced; attempts audited.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T010 — Immutable evidence references
**Dependencies:** `T003,T007`.
**Primary paths:** `src/saber/telemetry/{evidence,hashing}.py, tests/unit/telemetry/test_evidence.py`.
**Implement:** Build content-addressed evidence references and sha256 verification with local filesystem dev adapter; reserve MinIO adapter for T017.
**Acceptance:** Evidence hash mismatch fails closed; duplicate contents deduplicate predictably; output references are non-mutable.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T011 — Experiment state machine and idempotency
**Dependencies:** `T003,T004,T005`.
**Primary paths:** `src/saber/benchmark/{runner,state}.py, src/saber/api/routes/runs.py, tests/integration/benchmark/test_transitions.py`.
**Implement:** Implement experiment and episode transitions, append-only transition history, idempotent run creation, failure and INVALID termination.
**Acceptance:** All transitions tested; invalid transitions reject; duplicate idempotency key does not create another run; data survives restart.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T012 — Evaluator-only truth boundary
**Dependencies:** `T005,T011`.
**Primary paths:** `src/saber/benchmark/{truth,roles}.py, tests/security/test_truth_isolation.py, infra/compose/evaluator-policy/`.
**Implement:** Separate sealed truth data from agent stores (distinct storage credentials in lab; strict mocked policies in dev); independent truth accessor used only by evaluator.
**Acceptance:** Blue service cannot retrieve truth by URL, DB query, object key or joined response; test asserts blocked paths and audit entries.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T013 — Deterministic graders and invalidity rules
**Dependencies:** `T008,T011,T012`.
**Primary paths:** `src/saber/benchmark/{grading,metrics}.py, tests/unit/benchmark/test_grading.py`.
**Implement:** Score episode verdict, evidence support, affected-host accuracy, TTD, benign host-hour false positives and INVALID semantics.
**Acceptance:** Hand-calculated golden cases match exact scores; failed attack never becomes false negative; no evidence ID gets full credit.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T014 — Run reports and reproducible manifest
**Dependencies:** `T010,T013`.
**Primary paths:** `src/saber/benchmark/{report,manifest}.py, src/saber/cli/report.py, tests/golden/`.
**Implement:** Export ReportV1, manifest hashes, JSONL audit, data coverage, model/telemetry/config versions; deterministic serialization.
**Acceptance:** Same frozen run inputs yield same content hashes excluding explicitly ephemeral fields; valid JSON schema; fixture end-to-end smoke.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T015 — Proxmox lab IaC plan-only
**Dependencies:** `T005,T014`.
**Primary paths:** `infra/proxmox/, docs/adr/lab-network.md, tests/security/test_lab_inventory.py`.
**Implement:** Specify dedicated lab bridge, VM inventory/resources/snapshots and provider secrets; implement plan and topology validation only, never auto-apply.
**Acceptance:** Static validation works without credentials; production CIDRs rejected; plan cannot create NAT to production; apply requires manual review.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T016 — Ansible baseline provisioning
**Dependencies:** `T015`.
**Primary paths:** `infra/ansible/{inventory,roles,playbooks}/, tests/infra/`.
**Implement:** Implement idempotent benign setup for Windows/Linux/application/database/workload runner; local/test inventories and pinned versions.
**Acceptance:** Syntax and dry-run validations pass; tasks target allowlisted lab hosts only; no passwords checked into repo.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T017 — MinIO raw archive adapter
**Dependencies:** `T010,T016`.
**Primary paths:** `src/saber/telemetry/minio_store.py, infra/compose/minio.yml, tests/integration/telemetry/test_minio.py`.
**Implement:** Implement immutable raw archives, checksums, versioned references, evaluator/blue bucket policies and retention config.
**Acceptance:** Put/get hash match; mutation rejected; unauthorized role denied; outage surfaces typed error.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T018 — Wazuh and OpenSearch adapters
**Dependencies:** `T009,T016`.
**Primary paths:** `src/saber/telemetry/{wazuh_manager,opensearch_store}.py, tests/integration/telemetry/test_opensearch.py`.
**Implement:** Separate Wazuh manager management/health API from indexer/OpenSearch event searches; map constrained EventQuery to controlled DSL with index/field allowlists.
**Acceptance:** Adapter parity with FakeEventStore on contract fixtures; pagination/time guards enforced at backend; no broad wildcard indexes by default.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T019 — Endpoint telemetry validation
**Dependencies:** `T016,T018`.
**Primary paths:** `infra/ansible/roles/{windows_logging,linux_logging}/, tests/infra/telemetry_smoke/`.
**Implement:** Deploy benign log forwarding for Windows Sysmon/Event Log and Linux audit/auth/application, with health and ingestion timestamp checks.
**Acceptance:** Produce a real benign event on each host; locate original raw record and normalized event; measure ingestion delay; otherwise lab gate blocked.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T020 — Network telemetry profile (optional gate)
**Dependencies:** `T015,T019`.
**Primary paths:** `infra/ansible/roles/network_sensor/, src/saber/telemetry/network_normalize.py, tests/infra/network/`.
**Implement:** Optionally add Zeek/Suricata sensor with safe passive capture and privacy-conscious event mapping; skip when lab resources insufficient.
**Acceptance:** Selected DNS/HTTP connection metadata appears with timestamps and source provenance; benchmark declares coverage if omitted.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T021 — Benign workload scheduler
**Dependencies:** `T016,T019`.
**Primary paths:** `src/saber/workloads/{registry,scheduler,drivers}.py, scenarios/public/benign/, tests/integration/workloads/`.
**Implement:** Run safe user/admin activity patterns using dedicated lab accounts, seeded timing, health checks and predictable cleanup.
**Acceptance:** 3 workload classes run with different seeds; emit real logs and app activity; rerun from snapshot without residue.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T022 — Scenario manifest registry
**Dependencies:** `T011,T021`.
**Primary paths:** `src/saber/scenarios/{registry,manifest}.py, scenarios/public/, tests/unit/scenarios/`.
**Implement:** Versioned schema for environment, workload, prerequisites, allowlisted emulation profile and expected sensor coverage; keep private truth separate.
**Acceptance:** Schema validation rejects public manifests containing truth/answer keys; seed/profile hashes stable; invalid refs fail.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T023 — Allowlisted emulation driver (lab only)
**Dependencies:** `T015,T016,T022`.
**Primary paths:** `src/saber/scenarios/{emulation,approval}.py, tests/security/test_emulation_policy.py`.
**Implement:** Adapter for pre-reviewed, low-impact ATT&CK-aligned emulation profiles; bind each run to explicit operator approval, allowlisted hosts, timeouts and abort.
**Acceptance:** In dev, no live execution; arbitrary shell/unknown profile rejected; lab without isolation proof blocked; approval scope verified.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T024 — Snapshot, success verification, cleanup
**Dependencies:** `T019,T021,T023`.
**Primary paths:** `src/saber/range/{controller,verifier,reset}.py, tests/e2e/lab/`.
**Implement:** Snapshot/reset controller and independent attack-success verifier based on observable lab effects; validate telemetry coverage before score.
**Acceptance:** Restore returns verified baseline hash; unsuccessful emulation becomes INVALID; prior episode residue absent; operator STOP recorded.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T025 — Agent-facing bounded tool gateway
**Dependencies:** `T009,T010,T011,T005`.
**Primary paths:** `src/saber/tools/{registry,gateway,quotas}.py, tests/security/test_tool_permissions.py`.
**Implement:** Typed read/search/case/finding tools, case isolation, provenance validation, budgets, redaction, timeout and audit; no arbitrary tools or shell.
**Acceptance:** Prompt-injection content cannot alter tools; unsupported evidence rejected; budget exceeded fails cleanly; every call audit linked to run.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T026 — LLM provider abstraction and stub
**Dependencies:** `T025`.
**Primary paths:** `src/saber/agents/{provider,stub_provider,budget}.py, tests/unit/agents/test_provider.py`.
**Implement:** Normalize prompt/tool messages, token usage, retries, timeouts, model version and seed metadata; implement deterministic stub and one real provider behind optional secrets.
**Acceptance:** Offline CI uses stub; provider errors typed and counted; budgets and no-secret-logging tests pass.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T027 — Monitoring agent
**Dependencies:** `T025,T026`.
**Primary paths:** `src/saber/agents/monitor.py, tests/integration/agents/test_monitor.py`.
**Implement:** Constrained triage with evidence IDs, severity and case grouping; distinguish benign administration from suspicious activity in dev fixtures.
**Acceptance:** Valid JSON schema; 1 positive + 1 benign fixture with reasoned evidence; no future event access; baseline result exported.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T028 — Threat Hunting agent
**Dependencies:** `T025,T026`.
**Primary paths:** `src/saber/agents/hunt.py, tests/integration/agents/test_hunt.py`.
**Implement:** Plan bounded hunting hypotheses, query accessible raw events, build timeline, cite evidence and stop within budget.
**Acceptance:** Reproducible stub hunt links event IDs and hosts; zero-result path handled; false evidence rejected; live provider optional.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T029 — Detection content agent + validation
**Dependencies:** `T025,T026,T018`.
**Primary paths:** `src/saber/agents/content.py, src/saber/content/{sigma_validate,registry,test_rules}.py, tests/integration/content/`.
**Implement:** Generate versioned draft Sigma rules; validate syntax, logsource mapping, pySigma target compatibility and held-out replay; do not publish automatically.
**Acceptance:** Bad rule rejects; good rule converts with pinned compatible backend; false-positive evaluation reported; hidden-set write denied.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T030 — IR agent + policy-controlled response
**Dependencies:** `T025,T026,T005`.
**Primary paths:** `src/saber/agents/ir.py, src/saber/response/{policy,drivers,state}.py, tests/security/test_response_actions.py`.
**Implement:** Agent proposes evidence-backed actions; dry-run only by default, operator-exact-action approval/TTL, lab-only adapter, verification and rollback.
**Acceptance:** Track A execute forbidden; benign host target rejected; approval mismatch denied; dry run has no side effects; rollback tests pass.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T031 — Multi-agent orchestration and shared cases
**Dependencies:** `T027,T028,T029,T030`.
**Primary paths:** `src/saber/orchestration/{workflow,case_bus,coordination}.py, tests/integration/orchestration/`.
**Implement:** Implement independently-triggered agent workflows, stateful case handoff, concurrency-safe coordination and full tool-call trace.
**Acceptance:** Monitoring→Hunting→IR and independent Hunting paths work; no mandatory linear chain; duplicate handoff idempotent.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T032 — Single-agent and rules-only baselines
**Dependencies:** `T027,T031`.
**Primary paths:** `src/saber/experiments/{baseline_rules,baseline_single,config}.py, tests/integration/experiments/`.
**Implement:** Expose same bounded tools, telemetry slices and budgets to rules-only/single agent; register architecture flags and cost accounting.
**Acceptance:** Baseline pair uses matching episode settings; no hidden labels in single-agent prompt; output contract identical for graders.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T033 — Family-based dataset split and blind tests
**Dependencies:** `T022,T024,T032`.
**Primary paths:** `src/saber/benchmark/{splits,blind}.py, tests/security/test_leakage.py`.
**Implement:** Separate family-based dev/test split, private labels and parameter/IOC contamination checks; freeze test configuration and rule hashes.
**Acceptance:** Same family never crosses split; labels inaccessible to agents; seen IOCs in hidden sample trigger review, not silent pass.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T034 — Experiment matrix and statistics
**Dependencies:** `T013,T031,T032,T033`.
**Primary paths:** `src/saber/experiments/{matrix,statistics}.py, tests/unit/experiments/`.
**Implement:** Run B0–B3 on matched seeded episodes; report cost/latency/FP/evidence metrics, bootstrap CIs grouped by scenario family and ablation comparisons.
**Acceptance:** Paired baseline results & denominators audited; identical inputs give reproducible deterministic stub outputs; missing results documented.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T035 — Detection/response tracks E2E
**Dependencies:** `T024,T030,T034`.
**Primary paths:** `src/saber/benchmark/tracks.py, tests/e2e/test_two_tracks.py, tests/e2e/lab/`.
**Implement:** Implement two separate execution tracks with explicit control-plane switches, safe containment and live episode verification after approval.
**Acceptance:** Track A never side-effects; Track B action/approval/postcondition recorded; prematurely stopped attack not penalized as missed later step.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T036 — Read-only research dashboard
**Dependencies:** `T014,T034,T035`.
**Primary paths:** `web/src/{pages,components,api}/, web/package.json, tests/e2e/web/`.
**Implement:** Build run list/detail, metric vector, episode validity, waterfall timeline, evidence refs, baseline comparison and failure counts; no attack control buttons.
**Acceptance:** Data from real API contracts, not hardcoded demonstration JSON; filtering works; screenshots or UI tests collected; no secret/truth leaks.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T037 — Hardening and adversarial testing
**Dependencies:** `T025,T030,T033,T035`.
**Primary paths:** `tests/security/, src/saber/security/, .github/workflows/ci.yml`.
**Implement:** Test prompt injection via log fields, cross-episode leakage, as-of bypass, approval replay, IR target escape, denial audit and storage policy.
**Acceptance:** All critical negative tests pass; documented review findings resolved; CI blocks regressions; no ability to invoke unreviewed attack.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

### T038 — Reproducibility release and researcher report
**Dependencies:** `T034,T035,T036,T037`.
**Primary paths:** `docs/REPRODUCIBILITY.md, docs/DATASET_CARD.md, reports/, scripts/reproduce_dev.sh`.
**Implement:** Create pinned environment report, dataset card, benchmark recipe, threat model, known limitations and independently rerunnable fixture benchmark.
**Acceptance:** Clean local checkout reproduces dev result; lab runs flagged separately; all external assets/version hashes and unresolved limitations disclosed.
**PR output:** source diff + new tests + actual command outputs + one-paragraph risk note.

## Cross-cutting evaluation gates

- After T009: future telemetry and cross-episode query tests must be impossible to bypass.
- After T014: seed-stable fixture report validates independently without an LLM.
- After T024: lab run is real only when effect verifier and sensor coverage checks pass.
- After T030: IR action without operator approval has no side effects.
- After T035: DETECTION_ONLY and RESPONSE_ENABLED always yield distinct report schemas/track labels.
- After T038: publish comparative claims only with family-based blind holdout and disclosed uncertainty.

## Suggested task progression in Claude Code

For each ID: (1) read docs and targeted spec, (2) plan mode, (3) implement only named ID, (4) run checks, (5) fresh-context review, (6) commit/PR with evidence, (7) start next task in a new session.

## Critical dependency edges

`T002 → T008 → T009 → T025 → T026 → T027/T028/T029/T030 → T031 → T032 → T034 → T035`.
`T011 → T012 → T013 → T014` independent of the real lab.
`T015 → T016 → T019 → T021 → T022 → T023 → T024` required for real scenario validity.

**Important:** Development can proceed on offline fixtures before lab hardware is ready. Efficacy results from dev fixtures must be tagged `DEV_SIMULATION_ONLY`.
