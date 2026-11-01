# Environment profiles for the continuous world

## Decision

Provide four deployment choices around the same existing application runtime:
`local`, `sandbox` (one hardened Linux container), `vm` (operator-built guest), and
`remote` (operator-managed lab server). Profile selection must not imply that
per-actor OS machines, browser automation or vendor integrations are implemented.

Generate portable, secret-free bundles. Do not copy the workspace wholesale, mount
the Docker socket, provision hypervisors, or expose the world control plane on LAN.
VM/server users run the bundle on their chosen host; no SSH passwords or arbitrary
remote commands belong in configuration. Existing services are a separate inventory;
an approved health check is evidence of reachability, not of adapter compatibility.

Keep lifecycle actions explicit, budgets persistent, and STOP/resume semantics intact.
Normal stop preserves data. Runtime snapshots/backups and Git rollback are separate.

## Delivery checkpoints

1. Typed profile catalog, CLI selection and configuration validation.
2. Portable bundles, local/guest execution and hardened Compose lifecycle.
3. Read-only environment/service diagnostics with truthful readiness states.
4. Operator README, VM/server runbooks, rollback guide and integration validation.

Each checkpoint is a separate tested commit. Docker runtime verification depends on
an available Linux engine; offline plan validation must never be presented as proof
that a container or VM was launched.
