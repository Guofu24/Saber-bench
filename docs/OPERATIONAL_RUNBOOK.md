# Operator runbook — from dev to controlled lab

This is an operational design, not permission to run live emulation.

## Developer workstation preflight

- Supported local OS (Linux strongly preferred; macOS with Docker/Colima possible for dev).
- Python 3.12+, uv, Docker/Compose, Git, Node for dashboard phase.
- Verify provider credentials are injected from environment only when agent LLM integration is enabled; use deterministic stub provider for unit tests.
- `make setup`, `make lint`, `make typecheck`, `make test`, `make test-integration`, `make smoke` must be implemented progressively by T001 and later tasks.

## MVP dry-run workflow

1. Start local PostgreSQL and optional MinIO via compose.
2. Apply database migrations.
3. Load a **development-only** fixture episode through the fake telemetry store.
4. Start experiment in DETECTION_ONLY + STUB_AGENT mode.
5. Replay events respecting `visible_at` and fetch via EventQuery gateway.
6. Collect evidence-backed findings; evaluate using private dev fixture truth in evaluator only.
7. Export `report.json`, `run_manifest.json`, `audit.jsonl` with hashes; validate invariant tests.

## Lab-mode preflight (human-controlled)

1. Confirm written authorization identifying owner, lab addresses, allowed scenarios, time window and rollback owner.
2. Verify Proxmox target inventory is allowlisted. Plan infra changes; inspect plan before any apply.
3. Verify a dedicated subnet/VLAN with **no connectivity** to production networks. Run automated egress/isolation tests from lab hosts and keep evidence.
4. Restore baseline snapshot. Check health and clock sync across hosts.
5. Validate Wazuh collection/indexing, raw archival and required event families using benign workloads only.
6. Test runner timeout and abort, snapshot rollback, privileged service separation and ground truth access denial.
7. Execute a single low-impact, pre-reviewed emulation profile after explicit operator approval.
8. Verify actual effect, telemetry completeness and absence of unexpected egress. Mark invalid on failure.
9. Close run, reconcile case/evidence/action records and restore clean snapshot.

## Emergency stop

Control plane needs a high-priority STOP action (not LLM-callable) that terminates workload/emulation scheduling, rejects new response actions, records last known state and invokes operator-guided rollback. Network isolation stays in place throughout stop and recovery.

## Evidence and retention

Persist report plus raw/normalized index manifests and hashes. Separate access and retention for dev fixtures versus hidden test labels. Retention schedules, encryption and access permissions must be approved before any data egress/publication.

## Release checklist

- All project checks pass on clean checkout.
- Real lab smoke test includes actual log generation/collection and verifiable emulation.
- Hidden evaluation has no discovered leakage paths.
- Scoring version and all build/model artifacts are pinned.
- Human review approves reproducible methodology and security posture.
