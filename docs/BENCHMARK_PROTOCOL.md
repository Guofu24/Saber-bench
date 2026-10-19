> **Subtask-based v2 addendum:** The original 24-scenario pilot is a generic engineering smoke-test proposal, **not** the scope of the user-provided domain benchmark. The authoritative workload taxonomy is 55 NICE tasks and 175 benchmark subtasks in `catalog/subtasks.json`; repeated episodes are counted separately. Apply the protocol to each subtask, then aggregate carefully across service/mode, with task-specific score/gates. See `docs/GRADER_CONTRACT.md`.

# SABER-Bench experimental protocol — v0.1

## Research objectives

Measure whether specialized SOC agents, shared case state, and controlled coordination improve cyber-defense outcomes over deterministic detection rules and a single general-purpose agent under **comparable information, model and resource budgets**.

Do not infer effectiveness from impressive narratives or a working dashboard. Evaluate the correctness and operational consequences of decisions.

## Two independent tracks

### Track A: DETECTION_ONLY

- Never execute containment actions (even if IR suggests one). Suggested actions can be scored separately for quality but cannot change the environment.
- Run an approved scenario to completion. Compute detection/triage/hunting/content metrics against verified observed events.
- Avoid any SIEM detection that prelabels the scenario class to agents unless it is also equally provided to other relevant baselines; report whether each configuration uses raw telemetry, alerts, or both.

### Track B: RESPONSE_ENABLED

- Fixed, preapproved allowed response actions are executed against **lab-only** assets, with TTL and rollback.
- Strong emphasis on time-to-containment, prevention/termination success, false containment, missed containment and benign-service impact.
- Attack sequence can be shortened by successful containment. Do **not** penalize Track B for techniques the attack never performed as a result of successful containment.
- Human approval latency is measured separately from autonomous agent latency to avoid mixing workflow delays with model speed.

## Dataset units

- **Scenario family:** abstract causal pattern (e.g. legitimate administration mistaken for persistence; multi-stage discovery-to-access).
- **Scenario definition:** parameterized workflow with deterministic success criteria.
- **Episode:** execution of a scenario for a particular seed, host assignment, background workload and infrastructure snapshot.
- **Experiment run:** model/architecture/threshold/tool-budget configuration evaluated over episode set.

Pilot: 24 scenario definitions (8 atomic, 8 multistage, 8 benign hard negatives) with ≥3 seeds each if compute permits. This is **development-scale**, not statistical proof of generalization. Freeze an independent hidden evaluation split after pilot quality gates.

Split **by scenario family/behavior**, not merely event rows or repeated seeds. A model must not see the same recognizable template/IOC in dev and hidden test. Maintain a hidden blind set with withheld host names, timings, benign workload parameters and noisy variants. Do not publish hidden answers in repo, prompt context, telemetry aliases or shared logs.

## Ground truth schema and validity

The evaluator-only record for each episode includes:

- verified attacker/emulation outcome (`VERIFIED|NOT_VERIFIED|INDETERMINATE` for malicious scenarios; `NOT_APPLICABLE_BENIGN` for verified benign scenarios) and verification method;
- first observed malicious action, attack start/end, verified affected asset set, and evidence event IDs;
- independently verified technique/action labels with ATT&CK version pinned;
- expected response targets and explicitly protected benign assets;
- expected raw log families and actual sensor/ingestion coverage;
- benign-only expected verdict for negative episodes;
- environment/snapshot hash, scenario configuration hash, scheduling seed, clock skew estimate and raw evidence hashes.

**Invalidation policy:** If the attack did not execute as intended, required sensors were absent, event visibility cannot be reconstructed, or the snapshot was contaminated, label the episode `INVALID`. Operationally failed episodes remain in the reliability report; they are **excluded from security efficacy denominators** and are never converted to false negatives.

## Leakage prevention

- Public manifest includes only environment/workload prerequisites. Private truth kept behind evaluator-only credentials and a distinct storage boundary.
- Agent-facing tool results have only opaque `episode_id`, not `scenario_id`, attack execution plan, seed, split, label, evaluator details or upcoming timestamps.
- The gateway computes `as_of` from benchmark time; query filter must satisfy `visible_at <= as_of` and `occurred_at <= as_of` except explicitly documented clock-skew handling.
- Cache keys include episode ID and evaluation timestamp; never serve cached future log results.
- Content agent cannot push a rule into hidden test runs, either before scoring ends or mid-run. Evaluate content on frozen holdout data.
- An adversarial unit test must attempt future-event queries and ground-truth API access; both must be denied and audited.

## Baselines and comparisons

| ID | System | Shared tools | Shared visibility | Notes |
|---|---|---|---|---|
| B0 | Deterministic SIEM rules | N/A | Same raw/alert sources | No LLM cost |
| B1 | Single general-purpose LLM agent | Yes | Yes | Same model family + total token/tool budget |
| B2 | Four specialists, no shared case memory | Yes | Yes | Tests specialization alone |
| B3 | Four specialists + shared case state + orchestrator | Yes | Yes | Tests coordination |
| B4 | B3 plus Content feedback | Yes | Yes | Detection content frozen between evaluation epochs |

For B1–B4, record actual provider/model revision, prompts, temperature if supported, total prompt/output tokens, tool calls, wall-clock and dollar estimates where available. Where an LLM provider does not guarantee determinism, replicate runs and report variation. Do not label identical tokens as identical computational cost when architectures cause unequal cached context or concurrency.

## Primary metrics (pre-register before hidden test)

### Monitoring / detection

- Episode-level malicious detection recall: `TP_malicious_episodes / verified_malicious_episodes`.
- Episode-level precision: `TP_detected_malicious / (TP_detected_malicious + FP_detected_benign)`.
- False positive **cases per benign host-hour** (less sensitive to differing scenario duration), plus benign episode FPR.
- Detection delay (`detected_at - first_observable_at`) and separately (`detected_at - attack_start`). Missing detections are censored; never remove them silently from latency summaries.
- Alert deduplication / case grouping correctness.

### Hunting / investigation

- Attack-scoped asset recall and precision, timeline event precision/recall vs annotated evidence, evidence support rate (`verifiable evidence IDs / asserted evidence IDs`).
- Investigation tool-call count, tokens and wall-clock; unsupported claims rate.
- For observations without deterministic truth, independent human adjudication with blind rubric; **LLM judge scores not the sole ground truth**.

### Detection content

- Syntax/semantic validity, compiler compatibility with pinned backend, field-mapping correctness, unit-test coverage.
- Performance of a proposed rule on **held-out** events, with alert/episode-level precision, recall and false positives.
- Drift robustness and duplicated / overfit rule rates.

### Incident response

- Proportion of truly impacted assets contained, time to executed containment, verified containment success, unnecessary response to benign assets, service disruption, rollback success.
- Per-action approval and policy violation rate. Any unauthorized action is a critical failure regardless of aggregate detection score.

### Efficiency and reliability

- Tokens, LLM/tool calls, $ cost, end-to-end wall-clock P50/P95, worker crashes, invalid episodes, telemetry loss, errors by category.
- State-machine idempotency and retry correctness.

**Reporting policy:** Publish the metric vector and per-task table. Do not declare a universal winner using a single arbitrary weighted score. If a composite is needed for visualization, define and publish weights before hidden evaluation and include sensitivity analysis.

## Repeatability

- For pilot: ≥3 distinct episode seeds per scenario where budget allows; for publication, choose sample size by power/precision analysis rather than an arbitrary number.
- Record seed, snapshot image/checksum, run config, Git SHA, image versions, tool versions, model ID, prompt hash, telemetry and rule-registry hashes, data coverage and runtime budget.
- Use bootstrap confidence intervals over **scenario families**, not individual highly correlated event records; report uncertainty and per-family performance.
- Paired comparisons where possible: B1/B2/B3 on matched equivalent episodes with clean snapshots.
- Reproduce cold vs warm model context appropriately; do not permit accumulated hidden-set knowledge between trials.
- Preserve raw, normalized and audit logs with hashed provenance and configurable retention policy.

## Evaluator design

- An evaluator-only service/process reads `sealed_truth_ref`, agent outputs, tool audit and verified episode metadata.
- Deterministic graders check event IDs, observed time, target accuracy, severity mapping when objective, response result and control-policy violations.
- Human blind-review rubric covers analytical reasoning only where evidence doesn't admit a crisp deterministic answer.
- Output `ReportV1` with sections: `validity`, `results`, `efficiency`, `safety`, `data_coverage`, `uncertainty`, `artifact_hashes`, `software_versions`.
- `grading_version` is immutable per experiment; changing graders invalidates before/after comparisons unless all outputs are regraded.

## Go/no-go gates

- G1 Fixture replay honors visibility cutoff, pagination and deterministic hash.
- G2 Failing attack verifier makes episode INVALID, not FN.
- G3 Agent attempts to request hidden truth or future events are denied and logged.
- G4 B0/B1/B2/B3 see the same authorized telemetry and measured budgets.
- G5 Track A cannot execute IR; Track B logs side effects and rollback.
- G6 At least one pilot has real workload telemetry and independent verified emulation in isolated lab; otherwise label all results `DEV_SIMULATION_ONLY`.
- G7 Full run can be replayed from a manifest without a human manually assigning answers.
