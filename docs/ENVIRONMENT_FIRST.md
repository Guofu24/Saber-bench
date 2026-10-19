# Existing infrastructure first — binding implementation policy

This supersedes named technology selections in previous implementation task specifications. Tools such as Proxmox, Wazuh/OpenSearch, MinIO, PostgreSQL, Terraform/uv, and React are **candidate implementations**, not blanket installation orders.

## Required discovery procedure (read-only)

1. Inspect repository and existing local executables/interpreters (`command -v`, version); Python venv / uv / poetry / pip; installed Python packages; web project's package manager, current dependency lockfiles.
2. Inspect only **authorized, configured** services from `config/existing-environment.json`: service ID/type, URL, version, read-only health endpoint, API schema and permissions. Never scan unlisted networks, harvest secrets, or brute-force credentials. Environment variable names can be listed; values should not be exposed.
3. For a requested capability (SIEM, raw store, case engine, object storage, host virtualization, event query, rule testing, browser UI), first identify a compatible implementation. Record an inventory matrix:
   `capability | existing_candidate | actual_version | health | interface_mapping | decision(reuse/adapt/install/block) | evidence | fallback`.
4. Explicitly compare the existing API to the abstract port. Reuse it if it satisfies contracts and isolation constraints; write an adapter when field names/endpoints differ. Do **not** migrate historical data or replace the incumbent stack merely to follow an older plan.
5. Only when required capabilities are genuinely absent, install minimal dependencies into the **existing project environment** or a project-local venv. Verify compatibility, pin versions, test, and note the change. Do not recreate an existing VM, container, DB or SIEM service.
6. For a new host/container/VM, network change, privileged package install, attack emulation or destructive response, require operator-provided scoped authorization and an isolated lab. In its absence, implement the safe adapter with tests but mark integration **BLOCKED**, without pretending it is READY.
7. Cache decisions in `docs/adr/` and reevaluate only when a service changes or fails health.

## Equivalence criteria

- Search backend: time-aware queries, pagination, resource caps, per-run/tenant isolation, evidence refs.
- Case engine: idempotent create/update, statuses, assignment, audit history, mock or sandbox capabilities.
- Object store: immutable content-addressed blobs, checksum verification and authorization boundary.
- VM/lab: isolated networks, reproducible snapshots, explicit lab inventory, independent state verification.
- LLM provider: configured provider and usage accounting, with stub for deterministic CI.
- Testing/build tools: current environment's supported version, reproducible requirements and fast local CI.

**Important:** existing does not automatically mean usable. A SIEM may be deployed but inaccessible to this user/project. Do not confuse a process name, available CLI binary or product mention in the HTML with verified credentials/permissions.

### Network within strict sandbox

The supervisor merges **only explicitly approved** `services[].api_base_url` hostnames from `config/existing-environment.json` into the per-session sandbox domain allowlist. Service entries with `approved_for_read_only_use: false` are not opened. This is not proof of authentication or authorization. Sandbox loopback/private-network policy may still block connections; report a blocker rather than disabling isolation automatically. MCP tools are deliberately off by default; a tool configured on your machine is not sufficient evidence that project access is authorized.
