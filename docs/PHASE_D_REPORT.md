# SABER Phase D report — validity of the Gold Evaluation Pilot v1

Written for: the account operator and an independent reviewer deciding what the gold pilot can and
cannot support today. All offline numbers are reproducible from a clean checkout at the listed
commit. Nothing here is certified against a real SOC, real telemetry, or externally validated
ground truth, and nothing is `READY_BENCHMARK`.

This report answers five questions separately, then records what two independent reviews found and
what remains a limitation. It covers the research-validity mission (a testable evaluation pilot),
not framework expansion; the 175-subtask offline engine is unchanged.

## Scope recap

- The 175-subtask offline execution milestone stands as an engineering result: every subtask runs
  build → solve → grade on seeded synthetic fixtures, and every scorer is `VERIFIED_OFFLINE`.
- Phase B built a **Gold Evaluation Pilot v1**: twelve file-mode subtasks (three per service) with
  domain-faithful artifacts, independently cross-checked ground truth, hard negatives, a sealed
  dev/hidden split, provenance, and a human-adjudication queue.
- Phase C ran two baselines on the same episodes: a deterministic naive **rules** floor and a
  genuine **LLM** baseline (Claude Haiku 4.5) through the authenticated Claude Code CLI under
  claude.ai subscription auth.
- Phase D (this report) ran independent security and benchmark-methodology reviews, fixed the
  material findings, and measured discrimination across three seeds with confidence intervals.

## 1. Structural scorer correctness

The deterministic grading library implements every scorer family the frozen source uses (enum, set
Fβ, source set-delta, partial-credit sets, Kendall τ, numeric tolerances, citation gate, zero/
factor/cap/invalid gates, penalties, accuracy, macro-average, TPR−FPR, ΔFP−ΔTP, and the sandboxed
regex / YARA-subset / filter engines). Grading fails closed, and scorers are composed from each
record's parsed source contract with no `eval` of source formula text.

For the three gold pilots that delegate to the registered subtask scorer, the source aggregate was
confirmed to match the frozen record exactly:

| Pilot | Source aggregate | Items |
|---|---|---|
| T1112.002 | weighted sum | verdict 0.5, triggering_rule 0.25, affected_asset 0.25 (enum) |
| T1102.002 | F2 (β=2, recall-weighted) | compromised-host set |
| T0020.001 | `max(0, M′/M − N′/(N′+M′))` | regex over corpus (sandboxed) |

The nine pilots with custom scorers faithfully implement their stated formulas (macro-F1 over six
IOC types; per-item accuracy; 0.6 verdict + 0.4 byte-offset IoU; 0.6 τ·recall order + 0.4 ±5-minute
UTC; 0.6 order + 0.4 preservation accuracy; sample-F1 via the YARA engine; 0.7 ΔFP−ΔTP + 0.3 cause
enum). Verdict: structural scorer correctness is **established** and tested.

## 2. Domain fidelity of the evaluation artifacts

The twelve pilots produce realistic artifacts rather than structural placeholders: URL-encoded
web-access logs, byte samples carrying a stable family marker, multi-host extracts including a
host with only historical traces, autoruns exports mixing signed vendor persistence with attacker
persistence, multi-timezone event logs, an IDS alert plus session payload, and so on. Each embeds
hard negatives designed to defeat a naive rule (a SQL word in a benign URL, a near-miss family
marker, a signed packed installer, a benign look-alike domain, a cross-zone pair whose local order
reverses the true UTC order).

Caveat: these are **domain-faithful SYNTHETIC** artifacts, labeled `SYNTHETIC_DOMAIN_FAITHFUL` and
`DEV_SIMULATION_ONLY`. They are not drawn from real telemetry or a real incident, and their realism
has not been signed off by a domain expert. Fidelity is a design claim supported by the artifacts
and the hard negatives, not an external validation.

## 3. Independently validated gold-label coverage

**Human/externally validated gold labels: 0.** No label here is expert-signed.

What the pilots do have is **two-route automated cross-checking**: the ground truth is derived from
the authored construction intent, and `independent_verify` re-derives it by a genuinely different
code path that must agree. After the Phase D fixes this holds for all twelve pilots (it did not
before — see Finding 1 below). Examples of the two routes:

| Pilot | Truth route | Independent verify route |
|---|---|---|
| T0167.002 | source pool (benign/malicious) | signer + suspicious-API count |
| T1348.002 | generative branch | whitelist/scope policy |
| T1102.002 | construction kind | live/historical indicator scan |
| T1406.001 | family-generator membership | byte-marker scan of decoded bytes |
| T2013.001 | documented `_extract` spec | line-marker completeness count (distinct from the value regexes) |
| T0020.001 | construction labels | URL-decode + SQL-token-combination semantic verifier |

This is stronger than self-consistency, but it is still automated agreement between two code paths,
not external truth. Six conventions are queued for human adjudication (`gold/ADJUDICATION_QUEUE.md`):
the attack-vs-policy-violation label, the FP-cause taxonomy, domain-vs-URL IOC scoping, unknown-
signer border cases, the WMI persistence type, and the preservation-method mapping. Verdict:
independently cross-checked, **not** independently validated; coverage toward `READY_BENCHMARK`
remains **0**.

## 4. Actual baseline discrimination

Measured over three seeds × twelve pilots (n = 36 episodes), dev split. The 95% CI is a **cluster
bootstrap that resamples the twelve pilots** (the three seeds of a pilot share templates and are
correlated, so an i.i.d. episode bootstrap would understate uncertainty); these CIs are therefore
wider and more honest. Reproduce with `saber gold baseline --llm --model haiku --seeds 1,2,3`; full
data (committed) in `gold/baselines/haiku_dev_seeds1-2-3.json`, generated under provider
`firstParty`, model `claude-haiku-4-5`, process exit 0.

| Baseline | Mean | 95% CI (cluster bootstrap) |
|---|---|---|
| Oracle (answer from gold) | 1.00 | [1.00, 1.00] |
| Naive rules (public inputs only) | 0.44 | [0.26, 0.61] |
| Claude Haiku 4.5 — completed episodes | 0.944 | [0.88, 0.99] |
| Claude Haiku 4.5 — all episodes | 0.917 | [0.84, 0.98] |

- **Separation.** oracle − rules = 0.56 [0.39, 0.74]; LLM − rules (paired, completed) = 0.51
  [0.34, 0.67]. The eval places a capable LLM well above the naive floor and below the oracle; the
  separation is positive across the cluster-bootstrap interval.
- **Run-to-run variability (per seed).** rules 0.35 / 0.49 / 0.48; LLM completed 0.957 / 0.974 /
  0.901; completion 0.917 / 1.00 / 1.00 for seeds 1 / 2 / 3. The LLM mean moves ~0.07 across seeds.
  **Three seeds is limited evidence of stability**; more seeds (and repeats of the stochastic LLM
  per episode) are needed before any run-to-run claim.
- **Completion / tool failures.** 35/36 episodes returned a gradeable answer (completion 0.972).
  The one miss was a 150-second timeout on T1112 (seed 1), not a wrong answer; it is the single
  tool failure recorded. No permission denials, no MCP or filesystem tool use.
- **Latency.** mean ~20 s, p95 ~69 s per one-shot call. Cost is reported as list price ($1.21 for
  the 36 calls) and is informational only under subscription auth; provider observed `firstParty`.
- **Where the LLM is weak (per-pilot, mean over seeds).** T1387.002 IDS byte-offset 0.67;
  T1324.002 forensic order + preservation 0.84; T2013.001 IOC extraction 0.94; T1111.002 FP-filter
  diagnosis 0.90. Removing the leaked preservation catalog (Finding 4) pulled T1324 from a near-1.0
  freebie down to 0.84, which is the intended effect.
- **Per-pilot heterogeneity (honest caveat).** The headline gap is a mean over very different
  per-pilot gaps. Two pilots separate weakly: T1406.002 (rules 0.90 — a single near-miss gives a
  trivial substring rule F1 ≈ 0.9) and T1112.002 (rules 0.83 — an always-"TP" guess earns the rule
  and asset sub-scores plus verdict credit whenever the episode is a true positive). The aggregate
  should be read alongside the per-pilot table, not on its own.

Verdict: the pilot **discriminates** between a naive baseline, a capable LLM, and the oracle, with
measurable weak spots and uncertainty bounds. This is a discrimination measurement on synthetic
episodes, not a validated comparative benchmark.

## 5. Readiness for full SOC/VM integration

Unchanged and gated. Of 175 subtasks, 65 (18 `vm` + 47 `soc`) carry a `BLOCKED_INTEGRATION`
dependency on real infrastructure (SIEM/indexer, hypervisor lab, attack emulation, forensic
artifacts). The gold pilot covers **file-mode subtasks only**; it does not advance `soc` or `vm`
readiness, which still require an authorized lab, sealed real data, and the independent state
verifier for stateful VM actions. No rule is auto-published, no production SIEM config is changed,
and the response path stays deny-by-default.

## Independent reviews

Two read-only reviews ran against the gold pilots and the Phase C runner.

**Security review — fixed:**
- MCP lockdown: the LLM child now runs with `--strict-mcp-config`, so no operator-configured MCP
  server can load and reach the repo or network; combined with the isolated empty cwd, disallowed
  file/exec/network tools, and one bounded turn.
- Sealing: baseline reports strip truth-derived component detail; writing a hidden-split report to
  disk is refused.
- Billing claim corrected (see Limitations); a planted `claude` in the working directory is
  refused; an errored envelope no longer counts as a completed episode.

**Benchmark-methodology review — fixed:** circular verification in four pilots (now two genuine
routes); a single-path IOC truth (now cross-checked by an independent completeness count, which
caught and fixed two real extractor bugs); an answer leak in T1324 (catalog removed from inputs);
the overstated "independently cross-validated" wording; and the absence of uncertainty (now
multi-seed with bootstrap CIs).

## Limitations that remain (not fixed, stated plainly)

1. **No external validation.** Zero human-signed labels; six conventions await adjudication. The
   two-route check is automated agreement, not truth.
2. **The hidden split is not a blind holdout.** dev and hidden are distinct deterministic instances
   but draw from the same scenario templates/markers (`splits_are_blind_holdout: false` in the
   manifest). A true holdout needs disjoint template authoring.
3. **Synthetic, not real telemetry.** `DEV_SIMULATION_ONLY`; no real workload, emulation, or lab.
4. **Billing is the operator's responsibility.** The runner scrubs API-key/provider env vars and
   does not itself introduce API billing, but it cannot override an operator `apiKeyHelper`, a
   settings `env` block, or stored console credentials. Provider and cost basis are recorded for
   audit; a subscription call reports a nonzero list-price cost, so cost alone is not a billing
   signal.
5. **The grounding metric is a coarse proxy.** It flags entity-like answer tokens absent from the
   artifact; it is inert on pilots whose answers have no such tokens and can mis-flag a correctly
   transformed value. Use it as a directional hallucination signal, not a rate.
6. **Weak-discrimination pilots (heterogeneous gaps).** The headline oracle−rules gap is a mean
   over very different per-pilot gaps. T1406 and T1112 separate the naive floor from the oracle only
   narrowly (rules ≈ 0.90 and 0.83); they would benefit from more hard negatives before any
   benchmark use. Read the per-pilot table, not the aggregate alone.
7. **Limited seeds.** Three seeds and a single unrepeated LLM call per episode give only limited
   evidence of run-to-run stability; the cluster-bootstrap CIs quantify the between-pilot spread but
   not the LLM's per-episode stochasticity, which is unmeasured.

## Five-tier readiness accounting (unchanged)

| Readiness tier | Subtasks |
|---|---|
| VERIFIED_OFFLINE | 175 |
| IMPLEMENTED_OFFLINE / SPECIFIED | 0 |
| BLOCKED_INTEGRATION (real-lab dependency) | 65 (18 vm + 47 soc) |
| READY_BENCHMARK | 0 |

The gold pilot does not change this table. It makes twelve file-mode subtasks **independently
testable** with domain-faithful artifacts, two-route cross-checked labels, a sealed split, hard
negatives, and a measured baseline — the step before, not into, `READY_BENCHMARK`.
