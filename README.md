# SABER — Claude Code One-Shot v3.2

One **user command** launches a checkpointed development supervisor that automatically calls Claude Code sequentially for **218 work items**: 38 engineering tasks, 5 bridge tasks, and 175 genuine SOC benchmark subtasks from the supplied HTML. It favors **existing infrastructure and tools** over installing a predetermined stack. It does not include an already completed SABER application or 175 real validated datasets.

## Setup once (only prerequisites that are not already present)

- Claude Code CLI installed/authenticated: `claude --version && claude auth status`.
- Python 3.10+ to run the supervisor (`python3 --version`). Individual application code may have its own requirements.
- Work in an **isolated dev VM/container** with a clean checkout; no production secrets/network authority. On Linux/WSL2 with `--strict-sandbox`, have `bubblewrap` and `socat` installed (only if missing).
- Optional: copy `config/existing-environment.example.json` to `config/existing-environment.json`, replace placeholders with **approved existing services** (names, URL, *env-var names* — not actual credentials), or leave absent for offline-only development.

## One command

```bash
cd SABER-Claude-Code-OneShot-v3.2
./run.sh
```

**Default: subscription-only, no $250 API budget.** The supervisor checks `claude auth status` for `authMethod=claude.ai` and refuses known API/provider credential overrides. It never enables pay-as-you-go or extra usage. Your existing Pro/Max/eligible organizational plan supplies usage within its limits; this is NOT free unlimited access. Five-hour/weekly usage limits and account/organization controls still apply. In subscription mode, a recognized quota-limit response is checkpointed as `PAUSED_QUOTA`; the supervisor automatically sleeps and retries on the **same subscription**, with no API billing fallback. By default it polls every 60 minutes (or uses a clear relative reset hint) and stops safely after 192 consecutive hours without successful model access. The host must stay running and connected.

To verify authentication (no secrets printed):

```bash
claude auth status
```

To ensure the shell does not override subscription billing:

```bash
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL
claude auth login
```

For users **explicitly choosing metered Claude API billing**, switch modes yourself with:

```bash
./run.sh --billing-mode api --budget-usd 100
```

Do not use API mode merely to prevent subscription rate limits. The API budget is not a top-up to your plan, nor does subscription usage count as an API charge.

This call runs while the terminal/host stays on. No repeated prompting or manually restarting Claude for normal work or subscription usage-limit resets. It may stop on missing lab evidence, authorization, repeated failing tests, long quota unavailability (8-day wait cap), or invocation safety caps; in those cases it **reports a blocker** instead of lying about completion. It cannot guarantee that all real inputs/VM permissions exist.

Before spending, inspect the queue with:

```bash
python3 scripts/run_autonomous.py --dry-run
```

To adjust quota waiting (still no paid API), e.g. check every 30 minutes and allow up to eight days, use:

```bash
./run.sh --quota-recheck-minutes 30 --max-quota-wait-hours 192
```

To **disable** automatic quota waiting and stop at the first quota limit, pass `--no-wait-on-quota`. The default behavior is auto-wait. Do not suspend or shut down the host while it waits; interruption saves a checkpoint but requires launching again.

For a very small smoke test (optional):

```bash
python3 scripts/run_autonomous.py --only T001 --strict-sandbox
```

To resume after interruption or solving a blocker, run **the same command**. Progress lives in `.saber-autonomous/state.json`; see `.saber-autonomous/REPORT.md` for the final status and `.saber-autonomous/logs/` for per-item evidence. Full logs may contain sensitive data: do not share them publicly.

## Read these first

- `CLAUDE.md`: binding instructions for unattended development.
- `docs/ENVIRONMENT_FIRST.md`: reuse/adapt/install decision procedure.
- `docs/AUTONOMOUS_EXECUTION.md`: queue, receipts, independent tests, budgets.
- `docs/IMPLEMENTATION_SEQUENCE.md`: ordering and cross-task acceptance gates.
- `catalog/subtasks.json`: frozen source-backed operational contract.

**Not a promise of autonomous real-world certification:** Real customer SOAR/SIEM, proprietary scanner output, 175 held-out corpora, permissions, VM snapshots and human-adjudicated ground truth may be absent. The supervisor will build safe DEV implementations when possible but cannot reasonably claim all 175 subtasks are `READY_BENCHMARK` without those inputs.

After resolving a concrete blocker, run with the same flags plus `--retry-blocked`; otherwise exhausted items are skipped to prevent endless reattempts. The supervisor also performs read-only `docker ps`/`podman ps`/`virsh list` checks when those CLIs are already present, and records the results in the environment snapshot without inspecting secrets.

Strict sandbox access to existing network services is restricted to hosts whose entries in `config/existing-environment.json` set `approved_for_read_only_use: true`; this does not bypass API credentials or any additional sandbox restrictions.

## Implementation status (this build)

This repository now contains a working **offline benchmark core** on top of the planning kit.
See `docs/READINESS.md` for the full three-tier breakdown and `docs/PROGRESS.md` (generated from
`status/ledger.json`) for per-item status. Quick start:

```bash
uv sync --locked
uv run python scripts/validate_catalog.py     # frozen 55/175/40 catalog, source hash verified
uv run pytest                                  # offline suite (unit, security, subtasks, API)
uv run saber task list --implemented           # subtasks with a runnable scorer
uv run saber smoke --subtask T1112.001         # build -> oracle -> reference -> grade
uv run saber experiment --seeds 1,42           # B0 vs ORACLE across implemented subtasks
```

Implemented and tested offline: domain contracts, catalog loader, deterministic grading library,
episode builder (public manifest vs sealed truth), bounded time-guarded query gateway, lab-only
response policy + state machine, specialist router + baselines + experiment matrix, read-mostly
API, and a plan-only lab-isolation validator. Twelve subtasks run end to end across `file`/`soc`/
`vm`. Everything needing a real SIEM, hypervisor, emulation, forensic artifacts, or an LLM-backed
baseline is wired behind fail-closed adapters marked `BLOCKED_INTEGRATION`. **No result is
`READY_BENCHMARK`.**
