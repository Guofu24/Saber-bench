# SABER Phase G report — Multi-service operational SOC benchmark

Written for: the account operator and an independent reviewer. All results reproduce from a clean
checkout; LLM results reproduce under the claude.ai subscription CLI. Nothing here is
`READY_BENCHMARK`; the frozen 175-subtask catalog, contracts, splits, grading invariants, and
Phases B–F are unchanged.

## G0 — Preserve and audit

The 175-subtask catalog loads and is used as the authoritative task definition. Phase G binds live
scenarios to exact frozen contracts only where the aggregate genuinely runs on live telemetry:
`T1347.001` (set_delta, "list exploit lines") and `T0020.001` (set_delta, author a rule). No
security invariant was weakened.

## G1 — Three genuinely-different live scenario families

All execute on the host (real loopback service, real traffic/state, hashed telemetry, server-side
truth cross-checked against generation intent, clean reset). Not SQL variants:

| Family | What runs | Hard negatives | Truth derivation |
|---|---|---|---|
| `web_sqli_probe` | HTTP access + inert SQLi probes | benign requests with SQL *words* | SQL token-combination (semantic) |
| `auth_bruteforce` | valid logins + failed-login burst | a single benign typo (one 401) | per-user 401 volume ≥ threshold |
| `fs_change` | admin uploads incl. authorized scripts + a webshell | authorized `health.php`/`status.aspx` | a webshell-marked server-side script on disk |

Telemetry originates from actual execution; nothing is fabricated. Credentials (`pass=`) are
redacted from the logged/exported evidence.

## G2 — Four-service case workflow

`saber.soc` runs Monitoring, Threat Hunting, Incident Response and Content Security over one `Case`
with cited evidence references and audited tool calls; no service reads the sealed truth
(test-enforced). Honest binding:

- **Monitoring** — list the malicious lines; SCORED vs `T1347.001` (set_delta).
- **Content Security** — author a rule; tested on a held-out (same-family, disjoint-seed) episode;
  SCORED vs `T0020.001`. Held-out tests re-draw robustness, NOT cross-family generalization.
- **Threat Hunting** — timeline + affected entities; a genuine artifact (entity-F1 reported), NOT
  claimed as source-contract coverage. On loopback telemetry there is one client entity, so this
  metric carries little independent signal.
- **Incident Response** — determines eligibility and, on `fs_change`, EXECUTES a reversible
  quarantine. The action is deny-by-default, allowlisted, bound to a specific target via an operator
  approval with a separate executor token (the detector never holds it — separation of duties),
  verified from the real post-action filesystem state, with collateral recorded. Targets come from
  the AGENT's confirmed findings, so detection quality drives the IR outcome. IR is a verified
  lab-state effect, NOT a source-contract score.

Conventional coverage run (`range_evidence/soc/`): Monitoring 1.0 on all three families; IR
executed + verified on `fs_change`; proposed-only where no reversible action exists.

## G3 — Six-configuration evaluation and the coordination ablation

On identical live episodes (3 seeds) across TWO scenario families, scored with `T1347.001`'s
set_delta contract, invalidation-gated, cluster-independent bootstrap CIs, model `claude-haiku-4-5`
(`models_observed`). `multi_agent`, `budget_single` and `multi_no_reviewer` all spend 2 calls AND
share the same specialist first-turn prompt, so the comparison isolates the second step
(reviewer vs self-refine vs a 2nd analyst). `auth_bruteforce` is a volume/threshold rule, not a
regex-authoring task, so the six LLM configs are **NOT_EVALUATED** on it (conventional-only — in the
SOC coverage matrix). Data: `range_evidence/g3/g3_eval_haiku_seeds1-2-3.json`.

| Config | web_sqli_probe | fs_change | auth_bruteforce | Completion | Calls | Cost (list) |
|---|---|---|---|---|---|---|
| conventional | 1.00 [1.00,1.00] | 1.00 [1.00,1.00] | 1.00 (coverage matrix) | — | 0 | — |
| single (1 call) | 1.00 [1.00,1.00] | 1.00 [1.00,1.00] | NOT_EVALUATED | 1.00 | 3+3 | $0.19 / $0.12 |
| specialist (1 call) | 1.00 [1.00,1.00] | 1.00 [1.00,1.00] | NOT_EVALUATED | 1.00 | 3+3 | $0.18 / $0.11 |
| multi_agent (2 calls) | 1.00 [1.00,1.00] | 1.00 [1.00,1.00] | NOT_EVALUATED | 1.00 | 6+6 | $0.36 / $0.27 |
| budget_single (2 calls) | 0.94 [0.83,1.00] | 1.00 [1.00,1.00] | NOT_EVALUATED | 1.00 | 6+6 | $0.36 / $0.23 |
| multi_no_reviewer (2 calls) | 1.00 [1.00,1.00] | 0.83 [0.50,1.00] | NOT_EVALUATED | 1.00 | 6+6 | $0.35 / $0.21 |

(FP/FN totals: all 0 except budget_single one FN on web_sqli seed 2, and multi_no_reviewer one FP on
fs_change seed 2. Evidence references valid in every cell. 100% completion everywhere — the earlier
run's one-seed completion artifact is gone.)

**Does coordination add value beyond spending more calls? On this evidence, no — and the task is
ceiling-saturated, so the question cannot even be answered here.**

- On **both** families, `conventional (0 calls) == single (1 call) == specialist == multi_agent = 1.00`.
  A single call already maxes the task, so extra inference and coordination have no headroom.
- `multi_agent − single = 0.00` on every seed of both families. The reviewer's second call bought
  nothing over one call.
- The only sub-1.0 cells are two ISOLATED single-episode errors in the budget-matched controls (one
  FN, one FP, both on seed 2). At n=3 with wide CIs these are noise, not a coordination signal; per
  the ceiling-saturation caveat we do **not** read multi_agent's +0.06 / +0.17 edges as improvement.
- Verdict: **no support for "coordination beats more calls."** A real test needs genuinely hard
  (non-ceiling) tasks, many seeds, and multiple families, separating reliability from capability.

This is a deliberately anti-hype result: the eval did not manufacture a multi-agent win.

## G4 — Independent gold-label readiness

`docs/adjudication/` holds a PENDING_EXPERT_REVIEW package (disjoint seed 9001): per-family evidence
bundles, PROPOSED automated-lab labels with rationale, scoring conventions, accepted alternatives,
and unresolved ambiguities (brute-force threshold, authorized-pentest exclusions, legitimate script
deployments). Nothing is auto-approved: sign_off null, every reviewer_decision null,
independently-validated gold labels **0**, READY_BENCHMARK **0**. The exact external review needed —
a qualified SOC/IR lead independent of the project — and the promotion rule are named.

## G5 — Reviews

Both independent reviews ran read-only; actionable findings fixed (commit `a76e727`).

- **Security:** the IR approval model was weaker than SECURITY.md required — now approvals are bound
  to a specific action+target with a TTL, are **single-use (a replayed approval fails closed)**,
  require a separate executor token the proposing detector does not hold, and enforce the allowlist.
  Credentials (`pass=`) are redacted from logs/exports; the public receipt no longer discloses the
  webshells; the published suite receipt replaces the IR target filename with a **keyed opaque id**
  (HMAC with an unpublished per-publish key — a plain hash of the tiny filename space was
  brute-forceable). Confirmed sound: fs path confinement + inert marker, loopback-only traffic,
  sandboxed untrusted regex, truth sealed from detectors, and the dispatch-only credential-free CI
  workflow. Regression re-run after these fixes: provenance (frozen 175-subtask catalog), reset
  repeatability (deterministic truth, clean reset on all three families), and the security subset
  all green.
- **Methodology:** the ablation was unconfounded (budget-matched controls now share the specialist
  first turn); IR targets now come from the agent's findings; `fs_change` gained authorized-script
  hard negatives; the OR-ensemble bias and the same-family held-out are disclosed; invalid episodes
  are excluded from efficacy denominators. Confirmed sound: the exact set_delta formula, honest
  binding (only Monitoring/Content Security claim coverage), ground-truth independence, and no
  answer-key leakage into prompts.

## Readiness, blockers, and definition of done

Five-tier accounting unchanged: 175 VERIFIED_OFFLINE, 65 BLOCKED_INTEGRATION, 0 READY_BENCHMARK.
Automated-lab ground truth remains a distinct, lower tier than independently-validated gold (still
**0**). `DEV_SIMULATION_ONLY` preserved.

Outstanding blockers:

| # | Blocker | Unblock |
|---|---|---|
| CR-1 | local Docker daemon down; no `gh` CLI | operator starts Docker/WSL2 for a local container run, or triggers the `cyber-range` workflow |
| ED-1 | 0 independently-validated gold labels | qualified SOC/IR lead signs off the adjudication package |
| G-1 | 3 seeds, limited families, completion confounds | many seeds × multiple families, reliability separated from capability, before any agent-configuration claim |

**Definition of done:** demonstrated a reproducible, genuinely executed multi-service SOC workflow
across three scenario families, with evidence-backed agent decisions (cited evidence refs), a
verified reversible lab-state effect under a bound, single-use approval, fair call-budget-matched
baselines, and honest readiness — including the honest negative finding that coordination showed no
value beyond extra calls on this task. What remains is external: an authorized lab (CR-1) and
independent gold validation (ED-1).

## Phase H recommendation

The internal engineering is now ahead of the evidence it can produce; the limiting factors are
external and statistical, not code. Phase H should:

1. **Unblock independent validation (ED-1).** Route the `docs/adjudication/` package to a qualified
   SOC/IR lead for sign-off. Only a signed, independent confirmation may move a subtask from
   `AUTOMATED_LAB_GROUND_TRUTH` toward `INDEPENDENTLY_VERIFIED` — the single gate to any
   `READY_BENCHMARK` promotion.
2. **Stand up an authorized lab (CR-1).** With the operator starting Docker/WSL2 (or attaching a
   real SIEM), run the container backend via the `cyber-range` workflow for stronger isolation and
   real host/network telemetry beyond loopback.
3. **Power the coordination question (G-1).** The current ablation is underpowered (3 seeds, and the
   one apparent gap was a completion artifact). Phase H should run many seeds across several
   scenario families, SEPARATE reliability (completion) from capability (score on completed
   episodes), add a completion-robust budget-matched single, and only then test coordination value
   with clustered uncertainty over families — expecting, on current evidence, little to no benefit
   on conventionally-solvable tasks and reserving the question for genuinely ambiguous ones.
4. **Broaden beyond regex-detectable families.** auth_bruteforce (threshold) and richer host/network
   scenarios need agent interfaces beyond regex authoring to exercise more source contracts live.

No new framework is required for Phase H — only the external lab, the independent reviewer, and a
powered experiment.
