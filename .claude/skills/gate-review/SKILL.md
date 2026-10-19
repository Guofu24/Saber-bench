---
name: gate-review
description: Independently check a SABER task against contracts, benchmark validity and safety.
disable-model-invocation: true
---

Perform an evidence-oriented read-only review of task `$ARGUMENTS`.

1. Read `CLAUDE.md`, the task specification and relevant architecture/benchmark/security contracts.
2. Review the git diff and available test artifacts without changing code.
3. Check for contract mismatch, unchecked input, leaked evaluator truth, future-event/cross-episode leakage, attack verifier false success, unapproved side effects, misuse of mocked passing tests, non-reproducible outputs and missing budget accounting.
4. Output `BLOCKER`, `MAJOR`, `MINOR` findings with specific paths/lines and exact repro tests; clearly say if no findings were identified from the inspected material.
5. Recommend gate `PASS`, `PASS_WITH_CAVEATS` or `FAIL`; never assert checks were run without evidence.
