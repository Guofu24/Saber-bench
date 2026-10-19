# Alternative: single interactive Claude Code prompt (less reliable than supervisor)

Run `claude` in project root and paste:

> You are the implementation owner of SABER. Read CLAUDE.md, docs/ENVIRONMENT_FIRST.md, docs/AUTONOMOUS_EXECUTION.md, the frozen subtask catalog, and engineering backlog. First audit/reuse the present environment and services; install only genuinely missing local project dependencies. Implement, test, review, repair, and advance through the entire source-backed 175-subtask implementation plan without asking me for routine confirmation. Maintain machine-readable receipts and persistent checkpoint status. Stop on hard resource/authorization gaps with explicit blockers; never fabricate real telemetry or benchmark labels, never run production attack/response, and never claim READY without independent lab and truth verification. Keep working while there are reachable, uncompleted safe tasks. Every task needs a fresh independent test.

**Caveat:** One interactive session can still end due to context, rate limits or external blockers. The recommended one-command supervisor in `scripts/run_autonomous.py` is more robust.
