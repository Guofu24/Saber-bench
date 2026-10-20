# SABER Phase F report — Operational Cyber Range & Evidence-Based Agent Validation

Written for: the account operator and an independent reviewer judging whether a genuine, observable,
repeatable live SOC evaluation episode exists. All results reproduce from a clean checkout; the LLM
results reproduce under the claude.ai subscription CLI. Nothing here is `READY_BENCHMARK`, and the
175 offline-verified subtasks, contracts, splits, grading invariants, and Phase B–E work are
unchanged.

## F0 — Usable execution environment (read-only inventory)

- Local **Docker daemon is stopped** (Linux engine pipe absent) and there is **no `gh` CLI**, so a
  GitHub Actions run cannot be dispatched or observed from this environment.
- A **permitted runtime IS available**: the host Python with loopback networking. That is the live
  runtime used below. The Linux-container flavor is provided as an opt-in GitHub Actions workflow
  the operator can trigger.
- No infrastructure was purchased; no paid service enabled; no container restriction bypassed.

## F1 — The operational live lab (genuinely executable)

A minimal, loopback-isolated lab (`saber.range.live`) with two backends sharing one control plane:

- **process-local (executed here, verified):** `service_main.py` runs a REAL `ThreadingHTTPServer`
  as a subprocess bound to `127.0.0.1` only (refuses any non-loopback IP). The control plane drives
  bounded benign + inert-probe traffic, collects the service's REAL JSON access log, derives ground
  truth from server-side observations, verifies a clean reset (process dead + port closed), and
  stores SHA256-hashed, timestamped evidence. No telemetry is fabricated; all traffic is loopback
  with inert payloads; nothing external is contacted.
- **container / CI (authorized Linux runner):** the opt-in `cyber-range` GitHub Actions workflow
  (`workflow_dispatch` only, `contents: read`, 10-min timeout, loopback-only, no exposed ports, no
  secrets) runs the same lab on Ubuntu and uploads hashed evidence as an artifact. No Claude
  credentials are used in CI.

Lifecycle, benign workload, bounded security-event generator, telemetry collection, independent
observation plane, clean reset, and hashed raw-evidence storage are all present. Scenarios:
`web_sqli_probe` (benign browsing + SQL-word hard negatives + inert SQLi probes) and
`auth_bruteforce` (valid logins + a benign typo + a threshold brute-force burst).

**Reproducible deployment and execution:**

```bash
uv run saber range run --scenario web_sqli_probe --seed 1 --out evidence   # one genuine episode
uv run saber range bench --no-llm --seeds 1,2,3                            # T0020 contract, no LLM
uv run saber range bench --llm --model haiku --seeds 1,2,3                 # + single & multi-agent
# Authorized Linux runner: Actions -> cyber-range -> Run workflow, then download live-lab-evidence.
```

Verified runtime evidence and a telemetry sample are committed under `range_evidence/`
(`sample/web_sqli_probe_seed1.access.log` + a truth-free public receipt).

## F2/F3 — Live end-to-end benchmark (T0020.001 on real telemetry)

Subtask **T0020.001**'s source aggregate `max(0, M'/M − N'/(N'+M'))` is exercised VERBATIM on the
live `web_sqli_probe` access log: the corpus is the real log, M is the control-plane malicious-line
set, and each baseline's regex is run through the existing sandbox (`run_regex_rule`, ReDoS-bounded)
over the real lines. Four baselines on identical episodes; 3 seeds; invalidation-gated (all 3
episodes valid — cross-check and reset held); evidence references all valid (matched ids ⊆ episode
evidence ids). Data: `range_evidence/live_bench_haiku_seeds1-2-3.json`.

| Baseline | Score | 95% CI (bootstrap) | FP | FN | Completion | LLM calls | Cost (list) |
|---|---|---|---|---|---|---|---|
| naive regex (floor) | 0.04 | [0.00, 0.13] | 17 | 6 | 1.00 | 0 | — |
| strong conventional regex | 1.00 | [1.00, 1.00] | 0 | 0 | — | 0 | — |
| LLM single (Haiku 4.5) | 0.90 | [0.71, 1.00] | 2 | 0 | 1.00 | 3 | $0.17 |
| LLM multi-agent | 1.00 | [1.00, 1.00] | 0 | 0 | 1.00 | 6 | $0.42 |

Reading (honestly):

- **The hard negatives make precision matter.** The naive word-level regex collapses to 0.04 — it
  false-positives on the 17 benign requests that merely contain a SQL word (`select+ssd`,
  `SQL_union_types`, `drop-shipping`, …). This is not a toy perfect-separation task.
- **Coordination fixed the single agent's false positives.** The single LLM scored 0.90 and left 2
  false positives (it dipped to 0.71 on seed 3); the multi-agent analyst→reviewer pass drove false
  positives to 0 and scored 1.00 on every seed — but at **2× the calls and cost** (6 vs 3; $0.42 vs
  $0.17). The comparison is not equal-budget; the call/cost delta is reported alongside.
- **A precise conventional rule also scores 1.00.** As in Phase E, a competent conventional regex
  matches the oracle on this well-specified task; the LLM's value is not a higher ceiling here but
  the FP-reduction that coordination buys.
- **Completion and evidence integrity: clean.** 100% completion, 0 tool failures, all evidence
  references valid, all episodes valid (none excluded by the invalidation gate).

Honest limits: 1 scenario family, 3 seeds, a single unreplicated LLM run per episode — the CIs are
wide and development-grade, not a benchmark claim. The ground truth is `AUTOMATED_LAB_GROUND_TRUTH`,
derived by the control plane; it is NOT expert-validated gold.

## F4 — Independent validity and review

Both reviews ran read-only against the live lab; their actionable findings were fixed (commit
`6eb9d66`).

- **Security:** the one MAJOR — the CI artifact would have carried the sealed answer key via
  `episode.json` — is fixed: `range run` now writes only a truth-free public receipt, verified by a
  test. Plus a loopback request-shape guard, IP-literal-only binding, and a stale-ready-file fix.
  Confirmed sound: loopback-only traffic, inert payloads, no shell, the sandboxed untrusted regex,
  subscription-only env scrub, clean reset, and the dispatch-only least-privilege workflow.
- **Methodology:** added SQL-word hard negatives (the task is no longer trivially separable),
  invalidation gating (valid episodes only in efficacy denominators), bootstrap CIs with an honest
  small-n / single-family / unequal-budget caveat, a threshold-based auth truth with a benign-typo
  hard negative, and relocated output out of `gold/`. The benchmark report is sanitized so no
  per-seed answer key (matched line ids) is published. Confirmed sound: T0020 contract fidelity
  (formula verbatim), genuine (not fabricated) telemetry, truth sealed from the agent prompt, and
  per-mode resource attribution.

Scenario fidelity, evidence integrity (SHA256 over real bytes), network isolation (loopback refusal
tested), reset correctness (process-death + port-closed), and leakage resistance (public receipt /
sanitized report) are all verified by tests.

## Readiness and blockers

Five-tier accounting unchanged: 175 VERIFIED_OFFLINE, 65 BLOCKED_INTEGRATION, 0 READY_BENCHMARK.
Phase F adds the `LIVE_LAB_EXECUTION` / `AUTOMATED_LAB_GROUND_TRUTH` evidence tags; automated-lab
truth is a distinct, lower tier than independently validated gold (still **0**). `DEV_SIMULATION_ONLY`
preserved.

Outstanding external prerequisites:

| # | Blocker | Unblock |
|---|---|---|
| CR-1 | Local Docker daemon stopped; no `gh` CLI | operator starts Docker (or WSL2) for a local container run; triggers the `cyber-range` workflow from the Actions tab for a Linux-runner run |
| ED-1 | 0 independently validated gold labels | expert adjudication of the control-plane truth, or a labeled external corpus with an independent derivation route |
| F-1 | Single scenario family, 3 seeds | more families + seeds and replicated LLM runs before any quantitative agent claim |

## Success criterion

Met for the available runtime: at least one independently observable, repeatable, live SOC
evaluation episode executes here — a real loopback service, real traffic, real hashed telemetry,
server-side ground truth cross-checked against generation intent, a verified clean reset, and the
T0020 source contract exercised verbatim on it, with a four-way baseline comparison. It is a live
execution, not another synthetic-scoring expansion. The credibility gap that remains is the same
one named since Phase D: zero independently validated gold and no authorized real-data lab beyond
the loopback host / opt-in CI runner.
