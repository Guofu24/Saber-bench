# T030 — Lab-only response agent and approval flow

## Hard invariants

- `DETECTION_ONLY` track never permits side effects; dry-run proposal is allowed only as annotation.
- Default action mode = `dry_run`.
- IR agent cannot approve its own action.
- Only predefined action kinds on lab asset registry targets; no arbitrary shell command field.
- Approval binds exact action hash, target, lab environment ID and TTL.
- Executor verifies policy a second time right before execution and records verification plus rollback.

## Implementation scope

Implement structured IR proposal based on evidence refs, policy evaluator, operator approval interface, dry-run adapter, audit, durable action state machine and **lab-only, explicitly operator-approved** side-effect adapter design. In the initial implementation, verify dry-run E2E; real host action integration can be marked BLOCKED until lab gate H4.

## Required failure tests

1. Track A action execution rejected.
2. Unapproved proposal rejected.
3. Approval for host A cannot execute on host B.
4. Approval after TTL rejected.
5. Unregistered/protected host rejected.
6. Duplicate execution idempotent or explicitly rejected, never double-applied.
7. Failed action remains FAILED/unknown, not VERIFIED.
8. Rollback refusal/failure audited and escalated.
9. Tool-emitted malicious instructions cannot request an extra privilege.

Do not test by altering the developer's own laptop or external network.
