# SABER readiness report

Written for: the account operator and an independent reviewer deciding what SABER can be used for
today and what still needs a lab. Generated from the repository state at the listed commit; all
offline numbers are reproducible from a clean checkout. Nothing here is certified against a real
SOC, real telemetry, or externally validated ground truth.

## One-paragraph summary

SABER's offline benchmark is implemented and tested end to end. The frozen 55/175/40 catalog loads
and verifies against the source hash; a deterministic grading library covers every scorer family
the source uses; and **all 175 subtasks now run build → solve → grade** across the `file`/`soc`/`vm`
modes. Twelve are hand-written higher-fidelity exemplars; the other 163 are served by an archetype
engine that composes a real scorer from each frozen record's parsed score contract over a seeded
synthetic fixture. A family-based train/dev/test split with leakage checks is frozen. The
security-critical boundaries (time-leak, cross-episode, truth isolation, lab-only response, split
contamination) are enforced and tested. Everything that needs real infrastructure — a SIEM/indexer,
a hypervisor lab, attack emulation, forensic artifacts, and any LLM-backed baseline — is wired
behind ports that **fail closed** and marked `BLOCKED_INTEGRATION`. Every subtask is
`VERIFIED_OFFLINE`; **none is `READY_BENCHMARK`**, because the engine's fixtures are structural
synthetic DEV data, not domain-crafted or independently validated gold.

## Coverage at a glance

| Readiness tier | Subtasks |
|---|---|
| VERIFIED_OFFLINE (scorer + fixture + tests ran green on synthetic DEV data) | 175 |
| IMPLEMENTED_OFFLINE / SPECIFIED | 0 |
| BLOCKED_INTEGRATION (real-lab dependency on top of offline-verified) | 65 (18 vm + 47 soc) |
| READY_BENCHMARK | 0 |

`docs/COVERAGE.md` is the full per-subtask matrix (service, environment, aggregate, split, status).
The 12 hand-written exemplars are higher-fidelity; the 163 engine-backed ones are faithful to the
source scoring formula but use structural fixtures. Subtasks whose real mode needs a lab (18 `vm`,
47 `soc`, i.e. 65 of 175) additionally carry a `BLOCKED_INTEGRATION` dependency on the adapters
below; their *offline* implementation is nonetheless verified. (An earlier revision of this report
wrote 64/46 — an off-by-one undercount of the 47 `soc` subtasks; the catalog breakdown is 110
`file` / 47 `soc` / 18 `vm`.)

## Three readiness tiers

### Tier 1 — Implemented software, tested offline

| Area | Component | Tests |
|---|---|---|
| Contracts | Pydantic v2 DTOs: events, constrained query DSL, findings/cases, rule proposals, response actions, runs/episodes, Blue view | unit/domain |
| Catalog | hash-verified loader; 175 score items + 74 aggregate formulas parsed to structured metadata (no `eval`) | unit/catalog |
| Grading | enum, set Fβ, source set-delta, partial-credit sets, Kendall τ, numeric tolerances, citation gate, gates (zero/factor/cap/invalid), penalties, accuracy, macro-average, TPR−FPR, ΔFP−ΔTP, technique/tactic; directory-backed state verifier; sandboxed regex / yara-subset / filter engines | unit/grading |
| Episodes | public-manifest vs sealed-truth split with a leak guard; seeded deterministic fixtures | tests/subtasks, security |
| Telemetry | `FakeEventStore` + bounded `QueryGateway` (server-bound `as_of`/episode, HMAC cursors, budgets, audited denials) | security/test_query_guards |
| Response | deny-by-default policy, operator approval bound to the exact action, dry-run adapter, strict state machine | security/test_response_actions |
| Agents | `StubProvider` (deterministic), specialist router, baselines B0/ORACLE, experiment matrix with bootstrap CIs | unit/test_agents_experiments |
| API | read-mostly FastAPI: health, subtasks, public manifest, gateway-backed events, report | integration/test_api |
| IaC | plan-only lab-isolation validator (rejects production routes/NAT/egress/off-bridge VMs) | unit/test_lab_plan_and_config |
| Split | family-based train/dev/test partition + leakage/contamination checks (`status/split.json`) | security/test_split_leakage |
| Subtask engine | archetype `AutoSubtask`: real scorer composed from each parsed source contract + seeded synthetic fixture; all 175 pass the parametrized contract suite | subtasks/test_all_subtasks |

Run it yourself from a clean checkout:

```bash
uv sync --locked
uv run python scripts/validate_catalog.py
uv run ruff check src tests scripts && uv run ruff format --check src tests
uv run mypy
uv run pytest
uv run saber split
uv run saber experiment --seeds 1,42
```

### Tier 2 — Tested offline benchmarks (DEV_SIMULATION_ONLY)

All 175 subtasks run end to end and pass a parametrized contract suite (oracle reaches full credit
on two seeds, deterministic, no truth key in the agent-visible payload, cross-episode submission
denied, empty submission never beats the oracle). Twelve are hand-written higher-fidelity exemplars
(one per distinct scorer family, spanning all three modes) with bespoke fixtures and task-specific
golden traps such as relocation-not-removal and service-killed. The other 163 are generated by the
archetype engine, which is faithful to each source scoring formula but uses structural synthetic
fixtures rather than domain-crafted scenarios — hence `VERIFIED_OFFLINE`, never `READY_BENCHMARK`.

Offline baseline snapshot over all 175 subtasks (seeds 1 and 42, `reports/experiment-dev.json`):

| Baseline | Subtasks scored | Mean | 95% CI |
|---|---|---|---|
| B0 rules-only | 172 (abstained on 3) | 1.000 | [1.000, 1.000] |
| ORACLE (upper bound) | 175 | 1.000 | [1.000, 1.000] |

B0 equals the oracle on the engine-backed subtasks **by construction**: the rules baseline applies
the same inference rule (anomaly-score threshold, sort-by-time, stated computation) that the
structural generator encodes, so it recovers the exact answer. This is the expected signature of
structural synthetic fixtures and is why they are `VERIFIED_OFFLINE`, not `READY_BENCHMARK`:
discriminating real systems needs domain-crafted or independently validated fixtures where the
answer is not recoverable by a single stated rule. What the DEV suite proves is that the **scorers**
are correct — adversarial golden cases (all-fields-wrong, hard-gate-violated, one-dimension-wrong)
confirm wrong answers are scored down, caps/penalties/gates bind, and product factors all count.

| Subtask | Service / mode | Source aggregate | Mechanic exercised |
|---|---|---|---|
| T1112.001 | MON / file | `[verdict]` | enum exact-match |
| T1112.002 | MON / file | `Σ wᵢ·sᵢ` | weighted sum of enums |
| T1112.003 | MON / soc | `Σ wᵢ·sᵢ ; cap 0.30` | weighted sum + classification cap + citation gate |
| T1348.001 | MON / file | `max(0, M′/M − N′/(N′+M′))` | set-delta (masquerade identity = name@path) |
| T1290.001 | MON / file | `(số ô đúng)/5` | fraction-of-correct numeric cells |
| T2012.001 | HUNT / file | `max(0, M′/M − N′/(N′+M′))` | set-delta over (ip,port) |
| T0845.001 | HUNT / file | technique/tactic | 1.0 technique / 0.5 tactic |
| T1487.003 | HUNT / vm | `(Σ wᵢ·sᵢ) × [máy không đổi]` | read-only observation gated by machine-unchanged |
| T0020.001 | CNT / file | `max(0, M′/M − N′/(N′+M′))` | regex rule run in the exec sandbox |
| T0173.001 | IR / file | `Kendall tau` | UTC reordering |
| T0397.002 | IR / file | `F1 (sai loại = 0.5)` | partial-credit set (location vs type) |
| T1109.003 | IR / vm | `Π[4 điều kiện]` | eradication × clean-intact × config-restored × service-alive |

The other 163 subtasks are implemented by the archetype engine against the same contracts. B0
abstains where a subtask has no rules oracle (excluded from its aggregate, not scored zero);
per-group bootstrap CIs over fewer than three subtasks are flagged `reliable_ci=false`. These
numbers describe the **scorer and the rules baseline on synthetic fixtures**, not any model and not
validated benchmark cases.

## Independent review history

Three independent read-only reviews were run (two benchmark-methodology, two security; the engine
got a dedicated methodology re-review). All findings were addressed:

- **Security (round 1):** no blocker. Fixed fail-closed response-approval defaults and a required
  executor token; hardened the query gateway, lab-plan route check, and added a redaction seam.
- **Methodology (round 1):** fixed value-level label leakage, an omission-gameable Kendall-τ, an
  unevidenced fixture, and VM state gates that trusted a submitted snapshot.
- **Security (round 2, engine):** no blocker; made scoring fail closed with a recorded zero on
  malformed input and added sandbox CPU/memory limits. Confirmed sandbox isolation, declared-action
  VM verification, leak-guard namespacing, and per-subtask class isolation sound.
- **Methodology (rounds 2–3, engine):** fixed the engine to apply source caps and penalties, to
  multiply all product factors, to bind non-ENUM hard gates, to honour per-component set-delta, and
  to stop leaking answers verbatim; let the baseline cite real evidence; added adversarial golden
  cases and a gate-backing invariant test. Remaining documented (not silent) gaps are at
  `VERIFIED_OFFLINE` fidelity: mixture term weights, one order-in-mixture metric choice, and a
  stricter-than-source set-guarded cap.

### Tier 3 — Awaiting real lab / data (BLOCKED_INTEGRATION)

Each item below is implemented as a port with a fail-closed adapter and, where meaningful, a
tested translation layer. None is reachable without the named external prerequisite.

| Capability | Adapter | Missing prerequisite |
|---|---|---|
| SIEM / event search | `telemetry.opensearch_store` (query→DSL translation tested) | an approved, reachable, authenticated OpenSearch / Wazuh Indexer |
| Raw object store | `RawEvidenceStore` port + compose service | an approved MinIO / S3 bucket with policy separation |
| Hypervisor range | `range.blocked.BlockedRangeController` | an isolated lab with verified network isolation (SECURITY.md H1/H2) |
| Attack emulation | `range.blocked.BlockedEmulationDriver` (lists allowlist, refuses execution) | operator-approved profile + target + window (H3) |
| Lab response execution | `response.BlockedLabResponseDriver` | approved containment with rollback + executor token (H4) |
| LLM baselines B1–B4 | `agents.BlockedAnthropicProvider` | operator-approved provider key **and** an explicit API budget decision (the project is subscription-only) |
| Private held-out labels | — | independently sourced gold labels and expert adjudication of ambiguous source formulas |

## What is explicitly NOT claimed

- No subtask is `READY_BENCHMARK`. That needs independently validated data, lab verification, and
  human adjudication (`docs/GRADER_CONTRACT.md`, `docs/DECISIONS_REQUIRED.md`).
- No real attack was run and no production or lab host was touched.
- The synthetic fixtures are inert and abstracted; they are not real customer data, real malware,
  or validated samples.
- Enum label domains chosen where the source left them unspecified (e.g. T1112.003) are flagged in
  the subtask's `ADJUDICATION_NOTES` and in `docs/adr/0001-scorer-conventions.md` as pending
  business-owner sign-off.

## Suggested next steps (no new infrastructure required for the first two)

1. Upgrade engine-backed subtasks to hand-written fidelity where the scenario semantics matter
   most (the SOC/VM cases with hard business gates), promoting their fixtures from structural to
   domain-crafted. The scorer contract and tests already exist; only the fixture deepens.
2. Have the business owner adjudicate the conventions in `docs/adr/0001-scorer-conventions.md`
   (empty-set credit, FQDN host equality, tie policy, soft-gate semantics) and the enum label
   domains the engine chose where the source left them unspecified.
3. Source independently validated gold data for a priority subset; only then can any subtask move
   past `VERIFIED_OFFLINE` toward `READY_BENCHMARK`.
4. When a lab is authorized, turn on one `BLOCKED_INTEGRATION` adapter at a time behind its human
   gate; keep the offline suite green as the contract regression.

## Provenance

- Progress ledger: `status/ledger.json` → `docs/PROGRESS.md` (machine-generated).
- Scorer conventions: `docs/adr/0001-scorer-conventions.md` (immutable per `score_v1`).
- Sample experiment artifact: `reports/experiment-dev.json` (labelled DEV_SIMULATION_ONLY).
