# SABER readiness report

Written for: the account operator and an independent reviewer deciding what SABER can be used for
today and what still needs a lab. Generated from the repository state at the listed commit; all
offline numbers are reproducible from a clean checkout. Nothing here is certified against a real
SOC, real telemetry, or externally validated ground truth.

## One-paragraph summary

SABER's offline benchmark **core** is implemented and tested: the frozen 55/175/40 catalog loads
and verifies against the source hash, a deterministic grading library covers every scorer family
the source uses, twelve benchmark subtasks run end to end (build → solve → grade) across all three
execution modes, and the security-critical boundaries (time-leak, cross-episode, truth isolation,
lab-only response) are enforced and tested. Everything that needs real infrastructure — a SIEM/
indexer, a hypervisor lab, attack emulation, forensic artifacts, and any LLM-backed baseline — is
wired behind ports that **fail closed** and is marked `BLOCKED_INTEGRATION`. No result in this
repository is `READY_BENCHMARK`.

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

Run it yourself from a clean checkout:

```bash
uv sync --locked
uv run python scripts/validate_catalog.py
uv run ruff check src tests scripts && uv run ruff format --check src tests
uv run mypy
uv run pytest
uv run saber experiment --seeds 1,42
```

### Tier 2 — Tested offline benchmarks (DEV_SIMULATION_ONLY)

Twelve subtasks are implemented, one per distinct scorer family and spanning all three modes. Each
has an output schema, a seeded synthetic fixture, an independent scorer bound to the source
formula, an evaluator oracle that reaches full credit, a rules-only B0 baseline, and golden cases
(perfect / empty / false-positive / schema-invalid / cross-episode, plus task-specific traps such
as relocation-not-removal and service-killed).

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

Offline baseline snapshot (12 subtasks, seeds 1 and 42, `reports/experiment-dev.json`):

| Baseline | Subtasks scored | Mean | 95% CI (bootstrap over subtasks) |
|---|---|---|---|
| B0 rules-only | 9 (abstained on 3) | 1.000 | [1.000, 1.000] |
| ORACLE (upper bound) | 12 | 1.000 | [1.000, 1.000] |

B0 abstains on the three subtasks that have no rules oracle (T0397.002, T0845.001, T1109.003);
those are excluded from its aggregate rather than scored zero. On the synthetic DEV fixtures the
rules reference solves every subtask it attempts, so B0 equals the oracle here — expected for
designed fixtures, and not a measurement of any model. Per-environment CIs over fewer than three
subtasks are flagged `reliable_ci=false`. These numbers describe the **scorer and the rules
baseline on synthetic fixtures**; they are not evidence that the 12 subtasks are validated
benchmark cases. The remaining 163 subtasks are `SPECIFIED` in the frozen catalog but not yet
implemented.

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

## Suggested next steps (no new infrastructure required for the first three)

1. Implement the next tranche of FILE subtasks (the remaining `.001/.002` across services) using
   the same framework; each is a self-contained PR with an independent scorer and golden tests.
2. Have the business owner adjudicate the conventions in `docs/adr/0001-scorer-conventions.md`
   (empty-set credit, FQDN host equality, tie policy, soft-gate semantics).
3. Add a hidden family-based split and leakage checks (engineering T033) once enough subtasks
   exist to make a holdout meaningful.
4. When a lab is authorized, turn on one BLOCKED_INTEGRATION adapter at a time behind its human
   gate; keep the offline suite green as the contract regression.

## Provenance

- Progress ledger: `status/ledger.json` → `docs/PROGRESS.md` (machine-generated).
- Scorer conventions: `docs/adr/0001-scorer-conventions.md` (immutable per `score_v1`).
- Sample experiment artifact: `reports/experiment-dev.json` (labelled DEV_SIMULATION_ONLY).
