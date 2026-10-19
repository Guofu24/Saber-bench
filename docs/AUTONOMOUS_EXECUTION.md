# One launch → repeated Claude Code calls with durable checkpoints

## Why a supervisor exists

A single `claude -p` call terminates when its answer finishes. Building 38 engineering items + 175 operational subtasks cannot safely be assumed to fit a single context/session. `scripts/run_autonomous.py` invokes Claude Code once per work item and *automatically invokes it again* for the next item. The **operator launches only once**. Each child invocation has fresh context, inheriting project documents and the on-disk implementation state.

## Work queue

- T001–T005: project contracts/base and persistence/API
- B001–B005: source importer/typed specification/scorer/episodes/CLI bridge
- T006–T014: offline engine and independent evaluator
- five domain FILE vertical slices: T1112.001, T1348.001, T2012.001, T0020.001, T0173.001
- T015–T024: lab control **adapters** and integration probes (no unapproved provisioning)
- T025–T032: specialist agents, policy tools, orchestration and baselines
- remaining FILE subtasks, then SOC, then VM
- T033–T038: evaluation and reproducibility/reporting

The 218 work items are *development units*, not 218 independent benchmark episodes. Source catalog remains 175 subtasks.

## Receipt contract

`/.saber-autonomous/receipts/<ID>.json` relative to repository root:

```json
{
  "id": "T1112.001",
  "status": "IMPLEMENTED_DEV",
  "tests": [{"command": "python -m pytest -q tests/subtasks/test_t1112_001.py", "exit_code": 0}],
  "changed_files": ["src/saber/subtasks/t1112_001/__init__.py", "tests/subtasks/test_t1112_001.py"],
  "blockers": ["Missing independently sourced private held-out labels for READY_BENCHMARK"],
  "notes": "Synthetic dev scenarios only; no lab certification"
}
```

Blockers to READY can coexist with DONE_DEV/IMPLEMENTED_DEV, but do not invent a live pass. If safe DEV implementation itself cannot be completed, set status BLOCKED and list concrete blockers. Receipt paths are model-authored and not trusted as proof. Supervisor ensures they stay inside the repo, require test files, and *reruns relevant pytest commands independently*. Tests must exercise actual operations; hollow tests or self-generated labels can't establish real accuracy.

## State, reports and resume

- `.saber-autonomous/state.json`: status/attempt count/API estimate per item.
- `.saber-autonomous/environment.json`: read-only observed capabilities + explicitly provided inventory.
- `.saber-autonomous/logs/`: full Claude output and stderr per item — **may contain confidential data; never commit or share without review**.
- `.saber-autonomous/REPORT.md`: machine-generated remaining work, blockers and costs.

On interruption, run the **same** command again. Recognized Pro/Max quota exhaustion does **not** require relaunch as long as the process/host stays alive; `PAUSED_QUOTA` is persisted and retried without burning item attempts. Completed verified items are skipped, incomplete items are retried within their attempt limit. Do not delete the state directory to manufacture a clean status. If attempts run out, fix underlying blocker before changing retries.

## Completion semantics

- `DONE_DEV` = item has implementation files, a reported test and a fresh independent green test (basic local verification).
- `BLOCKED` = missing evidence, credentials, lab approval, incompatible services, or irreducible specification ambiguity.
- `PAUSED_QUOTA` = confirmed Claude subscription usage limit. Supervisor waits/retries when enabled and its safety cap has not elapsed.
- `PENDING` = no attempt yet, possibly due to invocation caps or missing prerequisites.
- This supervisor **never** awards `READY_BENCHMARK` automatically; requires independent reference truth, real lab/SIEM verification, human adjudication of ambiguous source score formulas and data rights. A 218/218 DEV result is **not** a claim that all 175 subtasks are certified research benchmark cases.

## Budget and safety

- Default is `--billing-mode subscription`, which requires a Claude.ai subscription login, rejects known environment API credential overrides and does not enforce artificial dollar budgets or use `--max-budget-usd`. **It is not unlimited or necessarily free**: included plan usage has session/weekly limits; recognized quota exhaustion automatically pauses and rechecks the *same* subscription hourly (or at a clearly indicated reset interval), preserving attempts and checkpoint; after 192 consecutive hours without access, it stops with `PAUSED_QUOTA` rather than using paid API. The account operator should keep usage credits disabled to prevent additional paid use.
- API pay-as-you-go is explicit: `--billing-mode api --budget-usd 100`. This mode has a client-estimated overall USD cap and an $8 per-item cap by default; these client estimates do not guarantee exact final billing.
- External costs (cloud, LLM/model API, VM hosting) are **not** represented in the supervisor's API estimate.
- Prefer `--strict-sandbox` (Linux/WSL2 require installed bwrap/socat). It explicitly forbids unsandboxed retries and fails if isolation is unavailable. Sandbox blocks some local/network service access; only expose approved endpoints and don't loosen it blindly.
- `dontAsk` permission mode denies tools not preapproved, rather than seeking user input. This ensures unattended operation but means some nonroutine tasks become BLOCKED instead of silently elevating privileges.
- Do not use `--dangerously-skip-permissions` on a machine connected to production assets. Do not put passwords/API keys in the repo or prompt.

## Observation, time and error handling

- Keep the terminal/job/host running; on a Linux host use tmux or an operator-approved persistent job manager. No guarantee of finishing on a closed/laptop-suspended host.
- External missing dependencies are BLOCKED and the supervisor advances to other items. At most 2 substantive development attempts per item by default. Recognized subscription quota responses do not consume those attempts and have a separate 192-hour consecutive-wait safety cap.
- Child session completion is **not** proof that a task passed. The independent tests determine DEV status. Hard-stopping budget returns a distinct nonzero exit status and leaves durable state.

If new credentials, corpora or isolated lab inventory become available, repeat the same command with `--retry-blocked` to reset exhausted blocked attempts (without deleting checkpoint history). Do not use this just to cycle repeatedly through unavailable external dependencies.
