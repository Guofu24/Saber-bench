---
name: implement-task
description: Implement one SABER task with strict scope, tests, and audit evidence.
disable-model-invocation: true
---

Implement **only** task `$ARGUMENTS` from `tasks/BACKLOG.md`.

1. Read `CLAUDE.md` and the relevant sections of `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/BENCHMARK_PROTOCOL.md`, `docs/SECURITY.md` and the task-specific file if available.
2. Verify dependencies are DONE **from evidence**, not only from prose. Check git status and current code before changing files.
3. State a small implementation plan: touched files, invariants, exact tests, approval requirements and rollback plan (if any).
4. If task is blocked by required operator authorization, implement no live side effects; report BLOCKED for real integration and complete only explicitly permitted dev/test portions.
5. Write tests first when practical, including at least one negative test addressing unauthorized access, time leaks or input validation where relevant.
6. Implement only the requested task. Run actual verification commands; record exit statuses and missing dependencies. Never call any live emulation, IR action or infrastructure apply without an explicit current approval.
7. Compare changed code against relevant docs and report using `tasks/REPORT_TEMPLATE.md`. No false-pass placeholders, no claims of tests not run.
8. Stop. Do not start the next task.
