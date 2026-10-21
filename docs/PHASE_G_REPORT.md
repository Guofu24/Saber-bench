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

On identical live `web_sqli_probe` episodes (3 seeds), scored with `T1347.001`'s set_delta contract,
invalidation-gated, bootstrap CIs. `multi_agent`, `budget_single` and `multi_no_reviewer` all spend
2 calls AND share the same specialist first-turn prompt, so the comparison isolates the second step.
Data: `range_evidence/g3/g3_eval_haiku_seeds1-2-3.json`.

| Config | Score | 95% CI | Completion | FP | FN | LLM calls | Cost (list) |
|---|---|---|---|---|---|---|---|
| conventional | 1.00 | [1.00, 1.00] | — | 0 | 0 | 0 | — |
| single (1 call) | 1.00 | [1.00, 1.00] | 1.00 | 0 | 0 | 3 | $0.15 |
| specialist (1 call) | 0.93 | [0.80, 1.00] | 1.00 | 0 | 1 | 3 | $0.16 |
| multi_agent (2 calls) | 1.00 | [1.00, 1.00] | 1.00 | 0 | 0 | 6 | $0.37 |
| budget_single (2 calls) | 0.67 | [0.00, 1.00] | 0.67 | 0 | 6 | 5 | $0.23 |
| multi_no_reviewer (2 calls) | 0.67 | [0.00, 1.00] | 0.67 | 0 | — | 6 | $0.30 |

**Does coordination add value beyond spending more calls? On this evidence, no.**

- A **single call already maxes the task** (single 1.00 = conventional 1.00). The task is
  conventionally solvable, so extra inference calls had no headroom to add value.
- The apparent `multi_agent − budget_single` and `multi_agent − multi_no_reviewer` gaps (+0.33 each)
  come **entirely from seed 2**: there both 2-call controls hit a one-off parse failure
  (completion 0.67, scored 0) while `multi_agent` happened to complete. On seeds 1 and 3 every
  config ties at 1.00 (per-seed deltas: 0.0, 1.0, 0.0).
- So the gap is a **reliability artifact on one seed, not a coordination effect**. With n=3, one
  family, and a completion confound, there is **no support** for a claim that the reviewer earns its
  extra call. If anything, `single == multi_agent` shows the second call bought nothing here.

This is a deliberately anti-hype result: the eval did not manufacture a multi-agent win. A fair,
powered test would need many seeds across multiple families and would have to separate completion
reliability from capability.

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
  to a specific action+target with a TTL, require a separate executor token the detector does not
  hold, and enforce the allowlist. Credentials redacted from logs/exports; the public receipt no
  longer discloses the webshells; the published suite receipt hashes the IR target filename.
  Confirmed sound: fs path confinement + inert marker, loopback-only traffic, sandboxed untrusted
  regex, truth sealed from detectors, and the dispatch-only credential-free CI workflow.
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
verified reversible lab-state effect under a bound approval, fair call-budget-matched baselines, and
honest readiness — including the honest negative finding that coordination showed no value beyond
extra calls on this task. What remains is external: an authorized lab (CR-1) and independent gold
validation (ED-1).
