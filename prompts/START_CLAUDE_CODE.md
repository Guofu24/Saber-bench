# Operator prompts for Claude Code

## 1. Enter planning mode at repository root

```bash
claude --permission-mode plan
```

Paste:

```text
You are implementing SABER from an existing specification kit, not inventing
a new platform. Read @CLAUDE.md @docs/ARCHITECTURE.md @docs/CONTRACTS.md
@docs/BENCHMARK_PROTOCOL.md @docs/SECURITY.md and @tasks/BACKLOG.md.
Do not execute code yet. Inventory repo files and identify any internal
spec conflicts or unsatisfied prerequisites. Then plan T001 ONLY using
@tasks/T001-BOOTSTRAP.md. Show paths, exact implementation steps,
quality/security tests and Definition of Done. No scope expansion.
```

## 2. Approve one implementation task

After reviewing the plan, exit planning mode / approve the implementation:

```text
Implement the approved T001 plan, limited to
@tasks/T001-BOOTSTRAP.md. Use deterministic tests and do not create
placeholders that claim to pass. Run all local acceptance commands,
fix failures and report actual evidence using
@tasks/REPORT_TEMPLATE.md. Do not begin T002.
```

## 3. Subsequent tasks

Replace `T###` by the next task whose prerequisites are DONE, preferably in a fresh Claude Code session:

```text
Read @CLAUDE.md @tasks/BACKLOG.md and the domain docs relevant to T###.
Inspect code and recent tests. Work ONLY on T###; honor dependencies.
First state the focused plan and exact acceptance checks, then implement.
Run and report actual checks using @tasks/REPORT_TEMPLATE.md.
If a real lab, provider key or operator approval is missing, use the
specified fake adapter only for development and mark real integration BLOCKED.
Do not call live emulation/response tools or infra apply.
```

## 4. Independent review — fresh context

```text
Review the T### diff, associated specification and negative/security
tests as a skeptical independent engineer. Try to disprove correctness,
benchmark validity and authorization boundaries. Do not grade by test
pass status alone. Return severity-ranked findings with file/line refs.
```

## 5. Before a full release

```text
Read @docs/BENCHMARK_PROTOCOL.md and @docs/SECURITY.md. Audit all
benchmark claims for ground-truth leakage, future-log leakage, scenario
family contamination, missing data invalidation, track separation,
and unapproved side effects. Produce a gap report and reproducibility
checklist. Do not run live attack or lab changes without explicit approval.
```
