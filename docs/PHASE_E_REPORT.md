# SABER Phase E report — Realistic Evaluation Foundation

Written for: the account operator and an independent reviewer judging evidence-backed progress
toward a credible, independently testable SOC benchmark. All offline results reproduce from a clean
checkout; LLM results reproduce from the committed manifests under the subscription CLI. Nothing
here is `READY_BENCHMARK`, and the 175 offline-verified subtasks, contracts, splits, and grading
invariants are unchanged.

This report delivers the seven Phase E artifacts: real-data ingestion evidence, the independent-
label provenance report, the strong-baseline comparison, the environment/cyber-range readiness
report, the updated readiness matrix, the remaining external prerequisites, and the final security
and methodology reviews.

## E1 — Independent evaluation data

`saber.evaldata` ingests genuine external security data into normalized records, each carrying a
provenance record (source, license, SHA256, size, retrieval time) and a **label tier**.

- **Importers/validators** for event logs (Windows/Sysmon JSON or JSON-lines), network captures
  (Zeek `conn.log` TSV / JSON flows; raw pcap reports the missing dpkt/scapy dependency instead of
  skipping), host artifacts (autoruns/registry CSV/JSON), and detection-test corpora (Sigma and
  Atomic Red Team YAML).
- **Four label tiers** keep external labels honest: `SOURCE_PROVIDED`, `INDEPENDENTLY_VERIFIED`,
  `SYNTHETIC`, `EXPERT_ADJUDICATION_REQUIRED`. The license gate is **enforced**: a source with
  `usage_permitted=False` is refused, not merely recorded.
- **Scenario-lineage contamination control**: `lineage_key` fingerprints a scenario by ATT&CK
  techniques + canonicalized/de-fanged IOCs + whitespace-normalized detection logic, excluding
  scalar identifier fields, so the same attack under different task IDs maps to one key;
  `assert_no_lineage_crosses_split` refuses to split it. It is an advisory guard (not yet wired into
  an enforced pipeline) and a content fingerprint, not a cryptographic boundary.

**Real-data ingestion evidence:** 4 genuine SigmaHQ rules (DRL-1.1, pinned commit
`4d47b8ff8a8b4f85ea099a79313158badea1feed`) ingested and validated, real ATT&CK techniques
extracted (`T1218`, `T1560.001`), per-file SHA256 recorded (`gold/evaldata/sigmahq_ingestion.json`,
reproducible). **Independently validated gold labels: 0** — external rules are `SOURCE_PROVIDED`,
not gold. Full provenance report: `docs/EVAL_DATA_PROVENANCE.md`.

## E2 — Strong baselines and controlled comparison

Six baselines graded on identical gold episodes (dev, seed 1, n=12 pilots) with the same graders;
cluster-bootstrap 95% CIs over pilots. Reproduce with `saber gold compare --llm --model haiku
--seeds 1`; data in `gold/baselines/compare_haiku_dev_seeds1.json`.

| Baseline | Score | 95% CI (cluster) | FP | FN | Completion | LLM calls | Latency mean/p95 | Cost (list) |
|---|---|---|---|---|---|---|---|---|
| oracle | 1.00 | [1.00, 1.00] | 0 | 0 | — | — | — | — |
| naive rules (floor) | 0.35 | [0.18, 0.52] | 14 | 15 | — | — | — | — |
| strong (conventional ceiling) | 0.97 | [0.90, 1.00] | 0 | 0 | — | — | — | — |
| LLM single | 0.86 | [0.69, 0.99] | 7 | 5 | 1.00 | 12 | 17.4s / 88.5s | $0.39 |
| LLM specialist | 0.80 | [0.57, 0.99] | 3 | 5 | 1.00 | 12 | 21.9s / 75.9s | $0.42 |
| LLM multi-agent | 0.95 | [0.88, 1.00] | 3 | 0 | 1.00 | 24 | 31.5s / 122.5s | $0.74 |

Reading (honestly):

- **Discrimination is real but the top is crowded.** The naive floor (0.35) is cleanly separated
  from every competent method. Among the rest the CIs overlap heavily (n=12, one seed), so the
  ordering strong ≈ multi-agent > single > specialist is suggestive, not significant.
- **Coordination helped; a role prompt did not.** Multi-agent (analyst + reviewer) beat single
  (0.95 vs 0.86) and drove FN to 0 — the reviewer caught missed items — but at **2× the calls,
  latency, and cost**. The specialist role prompt did **worse** than plain single (0.80),
  collapsing on YARA authoring (T1406) and FP-filter diagnosis (T1111). More prompting is not
  monotonically better.
- **The conventional ceiling is a ceiling, not a verdict.** `strong` (0.97) edges the best LLM but
  its CI overlaps multi-agent's, and for ~8/12 pilots it coincides with the detection rule the gold
  truth is built around (see `strong.py` for the per-pilot independence classification). On the one
  pilot whose answer key is withheld from inputs (T1324 preservation mapping) it scores 0.60 — an
  honest conventional shortfall. So this does **not** show conventional methods beat LLMs in the
  wild; it shows these file-mode tasks are largely conventionally solvable by construction.
- **Completion and tool failures: clean.** 100% completion, 0 tool failures across all 36 LLM
  episodes, after the timeout fix below. FP/FN are reported only where the scorer exposes them, so
  the columns are not comparable across all pilots.

**Completion-discrepancy investigation (from the earlier 3-seed run).** The reported "35/36
completions, one timeout, one tool failure" was **one event**: a 150s timeout on T1112 seed 1, the
first call of that batch (cold start + 59 KB system-prompt cache creation). The tool-failure counter
includes timeouts, so it is not a second problem. Investigating it surfaced a **real bug**:
`subprocess.run`'s timeout signalled only the direct child while the CLI's node grandchildren held
the stdout pipe open, so wall time overran the bound (343s against 150s). Fixed by running via
`Popen` and killing the whole process tree on timeout (verified: a 3s timeout now returns in 3.2s);
the definitive run above has 0 timeouts.

## E3 — Cyber range

- **Read-only inventory** taken first (`docs/CYBER_RANGE.md`): ample compute (28 CPU, 194 GB) and
  working HTTPS egress, but the Docker Linux daemon is stopped, WSL and all hypervisors are absent,
  and no SIEM/indexer/DB/forensic tooling is installed.
- **Reproducible lab** (`lab/`): an isolated (`internal` network, no egress), hardened (`cap_drop
  ALL`, `no-new-privileges`, read-only rootfs) docker-compose lab whose benign workload emits
  Sysmon-like JSON telemetry ingestible by E1. The plan passes offline isolation validation.
- **Adapter** (`saber.range.DockerLabController`): implements the `RangeController` port, fails
  closed (`IntegrationBlocked`, CR-1) while the daemon is down, and keeps stateful snapshot/restore
  `BLOCKED_INTEGRATION` until an authorized lab with an independent state verifier and per-run
  approval exists. The agent never starts Docker; no real integration is claimed until exercised.

## Updated readiness matrix (unchanged tiers)

| Readiness tier | Subtasks |
|---|---|
| VERIFIED_OFFLINE | 175 |
| IMPLEMENTED_OFFLINE / SPECIFIED | 0 |
| BLOCKED_INTEGRATION (18 vm + 47 soc) | 65 |
| READY_BENCHMARK | 0 |

Phase E adds evaluation-data ingestion, a strong-baseline comparison, and a lab substrate, but
promotes nothing: 0 independently validated gold labels, synthetic (not real) telemetry, and
`soc`/`vm` still gated on an authorized lab. `DEV_SIMULATION_ONLY` preserved throughout.

## Remaining external prerequisites (precise blockers)

| # | Blocker | Unblock |
|---|---|---|
| ED-1 | 0 independently validated gold labels | a labeled real corpus + an independent re-derivation route, or expert adjudication of the 6 queued conventions |
| ED-2 | Large labeled real logs/pcaps absent | operator accepts each dataset license and downloads (OTRF Security-Datasets, CIC-IDS-2017), then re-run the importers |
| ED-3 | Raw pcap parsing | add `dpkt`/`scapy` to the project venv only if binary pcap ingestion is needed |
| CR-1 | Docker Linux daemon stopped | operator starts Docker Desktop or installs WSL2; `docker info` succeeds |
| CR-2 | No SIEM/indexer service | bring up a compatible container in the lab, or point an adapter at an authorized existing SIEM |
| CR-3 | No authorized lab for `vm` stateful actions | isolated authorized lab with snapshots + an independent state verifier |

## Final reviews

Both independent reviews ran read-only against the Phase E code and their material findings were
fixed (commits `cfe1a7d`, `58f5be5`).

- **Security:** hardened `validate_lab_plan` against docker-socket mounts, `cap_add`, host
  namespaces, egress-network attachment, unconfined seccomp/apparmor, device/port exposure, and
  long-form writable binds; made the dataset license gate enforced; tightened the lineage id-field
  exclusion; extended the LLM tool denylist. Confirmed sound: data-only parsing, byte-accurate
  provenance, the sealed-truth/prompt boundary, multi-agent isolation, the subscription-only env
  scrub, the process-tree kill, the fail-closed adapter, and the benign committed lab.
- **Methodology:** corrected the headline validity issue — the strong baseline was tautological for
  ~8/12 pilots, now relabeled an honest conventional *ceiling* with per-pilot independence and the
  three hard-coded answers removed (T1324 now 0.60); fixed FP/FN double-counting; stopped a
  reviewer-call timeout from discarding a valid multi-agent draft and reported completed-only vs
  all-episode scores separately; hardened the lineage fingerprint. Confirmed sound: label tiers, the
  0-independently-validated claim, `DEV_SIMULATION_ONLY`/hidden-split sealing, and the cluster
  bootstrap.

## Bottom line

Phase E is evidence-backed progress toward a credible benchmark: genuine data can now be ingested
with provenance and kept uncontaminated; a four-way baseline comparison with uncertainty shows the
evaluation discriminates a naive floor from competent methods and surfaces where a one-shot LLM is
weak (YARA authoring, FP diagnosis, forensic mapping) and where coordination helps at a cost; and an
isolated lab + fail-closed adapter are ready for an authorized environment. The credibility ceiling
remains the same gap it was: zero independently validated gold and no authorized real-data lab.
Those are the next external prerequisites, documented, not papered over.
