# SABER — autonomous Claude Code instructions (v3.2)

Goal: build a reproducible benchmark of **175 SOC subtasks** in the supplied HTML catalog (55 NICE tasks; 110 file, 47 SOC, 18 VM), using **whatever compatible environment and services already exist**. Engineering items T001–T038 and bridge items B001–B005 are implementation work, *not* SOC benchmark tasks.

## Supervisor mode overrides the previous one-item-only plan

When invoked by `scripts/run_autonomous.py`, **finish the current WORK_ITEM without asking the operator; write the prescribed receipt, then exit that invocation**. The outside supervisor automatically starts the next item. The user issues **one launch command**, not 218 manual prompts. Do not try to execute the entire backlog inside a single context window. Use the on-disk checkpointer, not conversational memory, for durable progress.

## Non-negotiable precedence

1. Original user source: `source/nice_coverage_4dichvu_SOC_subtask.html` and frozen `catalog/subtasks.json` + 175 source-backed task cards.
2. `docs/SECURITY.md`, `docs/BENCHMARK_PROTOCOL.md`, `docs/GRADER_CONTRACT.md`: isolation, sealed truth, genuine execution and grading.
3. `docs/ENVIRONMENT_FIRST.md`, `docs/AUTONOMOUS_EXECUTION.md`: resource choice, progress, receipts and stopping.
4. `docs/IMPLEMENTATION_SEQUENCE.md`, `tasks/BACKLOG.md`, `tasks/subtasks/*.md`: requirements and implementation order.
5. **Named technology products in older T001–T038 specifications are preferences, not required substitutions**. Existing compatible SIEM, search, DB, object store, hypervisor, orchestrator and tooling take priority. Record deviations in ADRs.

## Environment-first requirements

- **Discover → Verify → Reuse → Adapt → Install only missing components**. Never replace a functioning existing service to match the suggested stack, and never reinstall an already usable dependency.
- Read-only discovery first; check versions, health, schema, API and the approved inventory. Do not enumerate networks, bypass auth, retrieve secrets or attempt unauthorised endpoints.
- Choose the smallest additional dependency, installed **only in the project workspace** if no compatible equivalent exists. Prefer existing virtualenv/runtime, compose services or VM templates. Never `sudo`, `terraform apply`, start a cyber attack or mutate a real host automatically.
- Adapter architecture over product lock-in; stub/dev adapter only if real access missing, explicitly labeled `DEV_SIMULATION_ONLY`.

## Benchmark truth requirements

- Preserve source inputs HV-01...HV-40, score semantics and special gates; don't eval source formula text or manufacture private gold labels.
- A synthetic DEV fixture is permitted but is NOT an externally validated benchmark sample. Missing private data or lab authorization => BLOCKED for that scope.
- All conclusions based on evidence IDs, cutoff timestamps and per-tenant isolation. No future-log access.
- Every domain subtask needs its **own contract, scorer, fixtures, golden/negative tests, trace and runnable smoke**. No empty placeholder passes.
- `file`, `soc`, `vm` are different execution modes; VM stateful defensive actions must have a verified isolated snapshot, allowlisted action and independent state verifier.
- Do not auto-publish rules, change SIEM production config, destroy data, or alter customer systems.

## Completion protocol

For each supervised item, write `.saber-autonomous/receipts/<ID>.json`, use status DONE_DEV/IMPLEMENTED_DEV only after actual tests, otherwise BLOCKED and exact missing prerequisites. The supervisor reruns independent tests and updates `.saber-autonomous/REPORT.md`. Never call a subtask READY_BENCHMARK based on self-reported success or synthetic data.

## Billing for the development supervisor

The `./run.sh` supervisor defaults to Claude.ai **subscription** mode, not pay-as-you-go API. Do not suggest enabling additional credits or changing to API billing. Authentication and subscription usage limits are the account operator's responsibility. No automatic upgrade or paid usage may be authorized by the agent.
