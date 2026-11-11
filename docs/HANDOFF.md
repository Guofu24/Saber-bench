# SABER — current AI / engineer handoff

**Snapshot:** 2026-11-11. **Implementation baseline:** Phase 4.1B-2 (online-search
red policy + controlled evaluation) on top of `1aaf5a5` (Phase 4.1B-1 multi-path
scenarios) and `5e81c93` (Phase 4.1A witness), branched from `e9b0c46`.
**Branch:** `feat/mission-outcome-metrics` (not merged to `main`).
**Repository:** <https://github.com/Guofu24/Saber-bench>.

**This branch adds a red-team upgrade** on top of the environment-profiles work:
a continuous always-on client, a mission-outcome score, an inert exfiltration
stage, a rule-based adaptive red planner, independently verified red-objective
metrics, a stateful scenario system with an independent feasibility solver, an executable
feasibility witness that validates that solver at the execution level, genuine
multi-path scenarios (two distinct executable paths to one objective), and an
online-search red policy with a controlled four-policy evaluation.
See **§5a** for the current architecture, phase status and validity limits; the
rest of this handoff still describes the shared baseline. Full red-team reference:
[docs/REDTEAM_SYNTHESIS.md](REDTEAM_SYNTHESIS.md) §8.

This handoff is committed after that implementation; compare `git log` before
assuming it describes a newer checkout. It records goals, implemented behavior,
evidence and unfinished work. It does not certify every deployment as operational.

**Cho AI tiếp theo:** Đây là bản bàn giao hiện tại: mục tiêu, những gì đã làm,
đã kiểm thử tới đâu và phần còn thiếu. Đọc file này cùng `CLAUDE.md`, rồi kiểm tra
code/commit thực tế. Không coi đề xuất nghiên cứu là tính năng đã triển khai;
không đọc hoặc in nội dung file API keys. Tài liệu cũ Phase G đã được lưu riêng.

## 1. What the user is trying to build

SABER should be a persistent, observable **client / red-team / blue-team lab**:

- Clients represent ordinary users, employees, developers and administrators.
  They log in, browse, search, open documents, use applications and maintain
  systems. Their work produces logs and must continue to matter during attacks.
- Red agents conduct offensive exercises against the authorized lab. Effects
  may be covert or visible to clients; an agent's narrative is not proof of an effect.
- Blue agents monitor, hunt, investigate, perform DFIR, contain incidents, improve
  detections and recover services, using evidence and considering disruption to users.
- Each team can contain multiple actors and specialists. The operator can change
  the roster and inspect what individual actors actually did in Agent Office.
- Runs can continue for long periods, resume after interruption, handle provider
  quota failures and learn from reviewed failures without losing auditability.
- A lightweight mode should work on modest hardware; larger isolated hosts should
  support sandbox, VM and multi-service Windows/Linux SOC deployments.

The project also retains its original **frozen SOC benchmark**: 55 NICE tasks,
175 subtasks (110 file / 47 SOC / 18 VM), and 40 HV source artifacts. These are
benchmark contracts, not agent counts. The persistent world and practice tracks
do not replace those contracts or establish benchmark readiness by themselves.
Synthetic fixtures remain `DEV_SIMULATION_ONLY` unless the separate readiness
requirements are satisfied.

The user wants implementation and honest validation, not repeated claims of
“100% complete.” Continuous operation and reproducible experiments are compatible:
future experiments should still have seeds, boundaries, resets and held-out cases.

## 2. Read these first

1. [CLAUDE.md](../CLAUDE.md): repository instructions and their precedence.
2. [English README](../README.md), [Vietnamese README](../README.vi.md) and
   [command notes](../notes.md): operator entry points.
3. [Security](SECURITY.md), [benchmark protocol](BENCHMARK_PROTOCOL.md),
   [grader contract](GRADER_CONTRACT.md): scope, evidence and scoring rules.
4. [SOC completion record](SOC_COMPLETION.md) and
   [end-to-end audit](END_TO_END_AUDIT_VI.md): implementation and deployment limits.
5. The relevant subsystem guide linked below, then its source and tests.

This document does not override those contracts. Read files explicitly; a fresh
AI does not automatically load all repository documentation. `runs/` and local
`.saber-autonomous/REPORT.md` are ignored and do **not** accompany a git clone.
The [Phase G handoff](history/HANDOFF_PHASE_G.md) is preserved only as history;
its old blockers, model restrictions and “not implemented” statements are stale.

## 3. What exists, and what has not been proven

| Area | Implemented behavior | Validation boundary / remaining work |
|---|---|---|
| Persistent world | Client/red/blue actors, real local HTTP app effects, SQLite state, cases, work queues, journals, stop/resume and quota controls | Synthetic lab accounts/workflows; not a complete enterprise or OS per actor |
| Native execution | Fixed Python child processes with measured process, command-line, file, DNS and TCP evidence | Real local execution, but bounded tools; not arbitrary shell access or full-host EDR |
| Deployment profiles | `local`, Docker `sandbox`, operator-built `vm`, and `remote` packaging | Lightweight world profiles; choosing `vm` does not provision AD or a full SOC |
| SOC presets | `linux-small`, `windows-ad`, `expanded`; services, workers, collectors, search, browser, network sensors and Office | Code/bundles and local integrations tested; full Docker/Windows AD acceptance still requires a capable target |
| Windows / AD | Hyper-V/PowerShell Direct provisioning, Sysmon collection, guest jobs and scoped AD response with rollback | Host edition, hypervisor, guest images, credentials and actual target acceptance remain deployment prerequisites |
| Blue operations | Twelve specialties, cited findings/cases, assignments, handoffs, notebooks, detection versions and recovery checks | Workflow availability is not proof that an LLM makes correct security decisions |
| Analysis / SOAR | Ghidra, IDA, Volatility, YARA and PCAP tool adapters; durable response jobs and effect checks; optional Shuffle/webhook | Adapters do not install licensed tools or supply samples/symbols; external services need target verification |
| Learning | Failure notes, proposals, version pinning, replay/review checks, release and rollback | Controlled skill improvement, not RL/gradient training or automatic truth verification |
| Forensic imports | Private originals, hashes, structured queries, byte-verifiable record citations, sessions and response-gap review | Supported text formats only; integrity and review completeness are not semantic correctness |
| HTB-informed practice | Nine original offline tracks, role guides, registered evidence and attributed reviews | No live HTB connector, VPN, account automation, downloaded course content or automatic pass grading |
| Agent Office | Team seating, expandable roster, actor traces, evidence, quota state, supported browser screenshots and forensic views | A bounded viewer of retained evidence; not a general remote desktop for every actor |
| Research integrations | Candidate papers and design directions identified | No CybORG/CAGE/NASimEmu/Cyberwheel backend or paper-derived RL implementation has been added |

### Runtime layers and where to edit

- [`src/saber/world/`](../src/saber/world/): `models.py` roster/configuration,
  `agents.py` planning, `runtime.py` execution/budgets, `environment.py` app tools,
  `store.py` persistence, `native*.py` measured execution, `work.py` and
  `operations.py` collaboration/cases, `office*.py` viewer evidence.
- [`src/saber/environments/`](../src/saber/environments/): lightweight deployment
  profiles. See [environment guide](ENVIRONMENTS_VI.md).
- [`src/saber/lab/`](../src/saber/lab/): portable SOC deployment, controller/team
  workers, guest jobs/sensors, analysis, SOAR, learning and recovery. Start with
  [SOC lab guide](SOC_LAB_VI.md), then [analysis](SOC_ANALYSIS_VI.md),
  [SOAR](SOC_SOAR_VI.md), [learning](SOC_LEARNING_VI.md) or
  [recovery](SOC_RECOVERY_VI.md).
- [`src/saber/agents/`](../src/saber/agents/) and
  [`.claude/skills/`](../.claude/skills/): provider, role and skill contracts.
- [`src/saber/forensics/`](../src/saber/forensics/): parsers, vault, tools and CLI.
  See [forensic guide](FORENSICS_VI.md).
- [`src/saber/training/`](../src/saber/training/): practice catalog, lifecycle and
  review reports. See [HTB training guide](HTB_TRAINING.md).
- [`agent-office/`](../agent-office/): Node/Three.js viewer. Source changes require
  rebuilding the committed viewer output and running its tests.
- [`catalog/`](../catalog/), [`tasks/`](../tasks/), [`src/saber/`](../src/saber/):
  frozen benchmark and its separate `task`, `smoke`, `experiment`, `range` and
  `soc` workflows. See [readiness](READINESS.md); do not infer readiness from UI demos.

The SOC bundle has 13 service definitions: controller, client, red, blue, app,
collector, indexer, dashboards, office, network, network-sensor, analysis and
soar. This is not an installer for every commercial SOC product.

Preset resource values are **planning estimates**, not measured minimums or
performance guarantees:

| Preset | RAM / CPU / disk | Initial client / red / blue actors | Windows guests |
|---|---|---|---|
| `linux-small` | 32 GB / 6 CPU / 250 GB | 2 / 3 / 6 | None |
| `windows-ad` | 64 GB / 8 CPU / 500 GB | 4 / 3 / 6 | 1 DC, 2 workstations, 1 file server |
| `expanded` | 128 GB / 16 CPU / 1 TB | 12 / 3 / 6 | 1 DC, 6 workstations, 1 file server |

Do not claim current host capacity from old conversation measurements. Recheck
the deployment target and run acceptance there. The lightweight world has a
different footprint and does not require the full SOC stack.

## 4. Agents, skills and providers

The default world has **6 clients + 3 red + 6 blue = 15 actors**. `--clients`
changes client count; `--blue-specialists` includes all 12 blue specialties.
An initialized config describes a roster, not proof that those actors are
currently running. Inspect the actual world's status and configuration.

- Red roles: `recon`, `access`, `impact`.
- Blue roles: `lead`, `monitor`, `hunter`, `dfir`, `ir`, `content`, `malware`,
  `network`, `intel`, `platform`, `identity`, `recovery`.
- Latest skill audit: **18 definitions, 15 operational playbooks, 58 references**.
  Role count differs from skill count because roles can share a playbook.
  Coverage details: [skills](SKILLS_VI.md), [specialists](SOC_SPECIALISTS_VI.md),
  [all-skill coverage](ALL_SKILLS_COVERAGE_VI.md).

Skills have been expanded for client behavior, offensive lab workflows and blue
specialties, including deeper DFIR. They are not certified as exhaustive for
all real incidents. Structural checks prove loading, references and context
limits; they do not prove operational competence. Scripted policies also do not
start following Markdown instructions merely because a skill file changed.

`src/saber/agents/skills.py` and `skill_library.py` distinguish eager context from
on-demand references. `metadata.saber-library` paths are validated, pinned,
exported and available through bounded role/team reference tools. Case context
is capped at 64,000 characters; world/range core context at 18,000; individual
reference reads at 12,000; index at 5,000; library at 128,000. The latest DFIR
case context is **63,921 characters**: do not append large eager sections blindly.
Use on-demand resources and rerun the skill audit, including learning headroom.
Existing worlds pin skill versions; source edits do not silently replace an
active case's instructions. Start a fresh world or use the release workflow.

### Gemini and key pools

The world supports scripted planning or explicit Gemini calls. At this snapshot
the configured default is `gemini-3.5-flash-lite`; this is a code default, not a
promise of current provider availability. Model errors may produce
`scripted-fallback`; inspect source labels before claiming Gemini did the work.

The user's requested pool layout is implemented in `world/key_layout.py`:
**entries 1–200 for clients, 201–400 for red, 401 onward for blue**. The team
layout requires unique keys and at least one blue key. Quota state, pool cursors,
cooldowns and cumulative HTTP-call budgets control failover. Calls made for
retries/learning are accounted for; many keys do not guarantee available quota.

**Never manually open, print, paste or commit `keys_pool*`, `.env` or credentials.**
Use the configured runtime if an authorized provider smoke is needed, with a
finite call budget and sanitized evidence. This handoff task makes no API calls.
The latest HTB demo also made no Gemini calls. Historical authorization to test
Gemini is not evidence that all keys currently work.

`run.sh` / `scripts/run_autonomous.py` are a separate **development supervisor**.
Their Claude subscription billing rule and one-item receipt/exit protocol apply
to supervised development invocations; they do not disable the explicitly
configured Gemini world runtime. Do not enable paid upgrades automatically.

## 5. Recent additions that must survive continuation

### Imported logs and DFIR

The implementation borrows useful workflow ideas from the user's local `ir.py`,
without importing that script wholesale. `world forensics` and `lab forensics`
offer `import`, `sources`, `verify`, `sessions`, `inspect` and `evidence` commands.
Original files are copied privately, hashed and indexed without modifying the
input. Citations retain source provenance, byte offsets, lengths and record
hashes. Time conversion retains raw/unknown-zone information.

Supported importer formats are CSV, Apache, IIS and text. It is **not** a direct
EVTX, PCAP, memory-image, UTF-16 or archive parser. Use controlled conversion or
the separate analysis tools and preserve conversion provenance/raw evidence.
Imports and queries have size/time/page budgets; see the forensic guide rather
than removing those limits to fit an arbitrarily large input.

Blue tools include `forensic_sources`, `forensic_open`, `forensic_query`,
`forensic_record`, `forensic_status`, `forensic_finish` and selected roles'
`response_review`. Sessions enforce ownership and previously observed citations.
Historical record IDs are separate from live events/cases. Imported evidence
does not automatically authorize live containment. Response review identifies
documentation gaps; `REVIEWED` does not prove successful remediation.

Office shows bounded readable previews and evidence references. A preview of
100/200 records is not the database's total. Stored history also has configured
retention/admission limits: “forever” does not mean unlimited disk or that old
worlds can reconstruct OS telemetry that was never captured. Treat evidence
text as untrusted; heuristic masking is not a complete DLP boundary.

### HTB-informed external practice

Nine **SABER-authored** tracks exist: `red-web`, `red-enterprise`,
`red-agent-evaluation`, `blue-dfir`, `blue-soc`, `blue-hunt-detection`,
`blue-malware`, `blue-identity-cloud`, `purple-validation`.
They are not official HTB track identifiers.

- `training init` creates a pinned exercise manifest, learner brief and private
  review template. Origin, synthetic/assisted status and rubric are explicit.
- `training attach` registers operator-supplied evidence with rights/conversion
  notes and hash-bound receipts. Original inputs are not deleted.
- `training prepare-world` creates the matching **blue** roster/configuration,
  with learning disabled. It does not start the world or implement a red HTB agent.
- `training report` checks binding, integrity, citations and review structure.
  Reviewers are attributed, not authenticated; semantic judgments remain theirs.
- Reports distinguish `AWAITING_REVIEW`, `REVIEW_INCOMPLETE`, `REVIEW_RECORDED`
  and `INTEGRITY_FAILURE`. **`REVIEW_RECORDED` is not a pass.** Reports retain
  `semantic_verification=false`, `benchmark_ready=false`, `live_execution=false`.

No HTB login, VPN, target launch/reset, course scraping, live telemetry API or
live containment is connected. User-supplied course materials retain their own
terms. Keep answer keys/review templates out of agent-visible evidence.

The last implementation fix routes external-practice guides by role, including
shared-guide namespacing, and includes practice assets in SOC exports. When
adding tracks, use `Track.guidance_for(role)`; do not assume a single topic name
works for every role. See `tests/unit/test_training.py` and
`scripts/smoke_training.py` for the executable workflow.

## 5a. Red-team upgrade (branch `feat/mission-outcome-metrics`)

This branch extends the persistent world's **red** side. All of it is inert,
single-app, `DEV_SIMULATION_ONLY`, and promotes nothing to `READY_BENCHMARK`.

### Architecture and key files
- [`src/saber/population/active_client.py`](../src/saber/population/active_client.py):
  always-on benign client daemon (scripted by default; hybrid LLM profile opt-in).
- [`src/saber/world/mission.py`](../src/saber/world/mission.py): private
  mission-outcome score = protected client work × detection quality; justified
  containment of an offender is not charged. Provisional weights, evaluator-only.
- [`src/saber/world/red_planner.py`](../src/saber/world/red_planner.py):
  deterministic **rule-based adaptive** red planner (belief state from own
  observations; reacts to containment/ACL denial/outage/budget). Tracks per-document
  denials and tries an alternative document, re-enumerating once when every known
  document is denied (Phase 4.1B-1). Not learned, not strategic.
- [`src/saber/world/red_policies.py`](../src/saber/world/red_policies.py): three
  evaluation policies — `adaptive`, `naive_greedy`, `random_valid`.
- [`src/saber/world/red_metrics.py`](../src/saber/world/red_metrics.py):
  independent red-objective verification from server effects; the `report()`
  `red_objectives` block (intent/attempt/artifact/effect; completion, timing,
  attribution). Evaluator-only key spaces; never in any observation.
- [`src/saber/world/scenario.py`](../src/saber/world/scenario.py) +
  [`scenario_cli.py`](../src/saber/world/scenario_cli.py): `ScenarioSpec`
  (versioned, validated), ten single-path family templates plus six **multi-path**
  families (`MULTIPATH_FAMILIES`, Phase 4.1B-1), `materialize()`, and the independent
  `feasibility()` reference solver. The solver enforces two distinct limits — the
  **action budget** (`red_action_budget`, count of red actions) and the **tick budget**
  (`tick_budget`, episode length in ticks); `VALID_FEASIBLE` requires both. For
  exfiltration it enumerates one candidate path per client document
  (`exfil_candidate_paths`) and is feasible if any path is.
- Per-document controls in [`environment.py`](../src/saber/world/environment.py)
  `read_document` (Phase 4.1B-1): a work document may be `restricted` (per-asset access
  control) or `requires` another document be read first (prerequisite). Inert, private
  (only a `403 Access denied.` is observable), so one path can be blocked while another
  stays open. Spec fields `restricted_clients` / `gated_clients` /
  `staged_restriction_tick` carry this; none reaches an observation.
- [`src/saber/world/witness.py`](../src/saber/world/witness.py) (Phase 4.1A + 4.1B-1):
  **executable feasibility witness**. `run_witness` runs the solver's candidate path
  through the real `World.act()` pathway in a fresh isolated episode **with no blue**,
  respecting prerequisites/ACLs/outages/session/action-budget, and verifies the
  objective **only from `red_metrics` server effects**. `witness_multipath` executes
  each distinct path independently and runs a recovery episode (attempt a blocked path,
  take the 403, verify the alternative). CLI `scenario witness` / `witness-all` /
  `multipath` / `multipath-all`. Structural feasibility only, kept separate from the
  blue-active runtime outcome.
- [`src/saber/world/online_planner.py`](../src/saber/world/online_planner.py) +
  [`red_eval.py`](../src/saber/world/red_eval.py) (Phase 4.1B-2): a bounded
  **online-search** red policy (`POLICIES["online"]`) that discovers an epistemically
  unidentifiable prerequisite by exploration, and a controlled evaluation harness (4
  policies × seeds, Wilson CI, an 8-label failure diagnosis, budget sweep, the offline
  optimal-witness length as a clairvoyant upper bound). CLI `scenario evaluate` /
  `budget-sweep`. The policy reads only its own observation; the solver/witness are used
  only offline as a diagnostic reference.
- Inert `exfiltrate` tool (TA0010/T1041) in
  [`environment.py`](../src/saber/world/environment.py); `WorldConfig.red_action_budget`
  in [`models.py`](../src/saber/world/models.py); `Runner(red_policy=...)` hook in
  [`runtime.py`](../src/saber/world/runtime.py).

### What actually runs vs only designed
- **Runs:** scripted/adaptive red over the inert world tools; exfiltration chain
  with server-measured bytes; verified objective metrics; all ten scenarios
  materialise and run under three policies; the feasibility solver and
  `saber world scenario` CLI; the executable witness over all ten families
  (`witness-all`: 10/10 static-vs-witness agreement, 8 verified / 2 no-witness); six
  multi-path families with the multi-path witness (one scenario has two distinct
  executable paths and the witness verifies the alternative after the first is blocked);
  the adaptive planner recovering from a blocked path via re-enumeration; the mission score;
  the online-search policy discovering a hidden prerequisite that the rule-based planner
  cannot (4-policy evaluation with Wilson intervals, failure diagnosis and a budget sweep).
- **Designed/not run here:** the LLM red policy (menu-based, range-only — not
  exercised); any mid-chain ATT&CK (Execution / PrivEsc / Defense Evasion / Lateral
  Movement / C2) — **no runnable inert action**, infrastructure-blocked.

### Phase status
| Phase | Status |
|---|---|
| 1 — synthesis/gap analysis | COMPLETE (`docs/REDTEAM_SYNTHESIS.md`) |
| 2 — red skills | PARTIAL — existing skills need a capability-based review |
| 3 — adaptive red agent | CORE COMPLETE — deterministic rule-based adaptive planner |
| 4 — scenario spec & generation | COMPLETE for the initial single-app scope |
| 4.1A — executable feasibility witness | COMPLETE — solver validated at execution level for the tested scenarios (positive feasibility only; see issue A) |
| 4.1B-1 — genuine multi-path scenarios | COMPLETE — two distinct executable paths to one objective; witness verifies the alternative after the first is blocked (6 families) |
| 4.1B-2 — online planning & controlled evaluation | COMPLETE — online-search policy discovers a hidden prerequisite the rule-based planner cannot; 4-policy evaluation with Wilson CI, failure diagnosis, budget sweep |
| 5 — verified objective metrics | COMPLETE for the current verified objectives |
| 6 — integration tests | PARTIAL — tests exist (incl. 11 witness + 17 multi-path tests); broader validity/fidelity checks remain |
| 7 — docs & handoff | this update |

### Validity issues to carry forward
- **A. Feasibility oracle — PARTIALLY RESOLVED (`5e81c93`).** The executable witness
  (`witness.py`) now **execution-validates positive feasibility for the tested
  scenarios**: it walks the candidate path through real `World.act()` and verifies
  from server effects, so all eight declared-feasible families produce a verified
  end-to-end witness (`witness-all`: 10/10 static-vs-witness agreement). **Still
  open:** (i) failure to find a witness does **not** prove infeasibility; (ii) the
  solver and witness **share the same candidate-path generator**, so the witness
  validates that generator's output, not the solver in general; (iii) general solver
  completeness remains unproven; (iv) multi-path feasibility and generalization are
  not established (a single shortest path is validated, not the full walkable space).
- **B. Feasibility semantics.** The solver gives **structural feasibility without
  blue**; observed reachability under an active blue policy is a separate runtime
  outcome (e.g. `blue_containment` is WITNESS_VERIFIED with no blue, yet contained at
  run time). Do not conflate them. The witness measures the structural notion only.
- **C. Generalization.** Still not established, but broader than before. Phase 4.1B-1
  adds witness-validated multi-path families; Phase 4.1B-2 evaluates four policies over
  seed permutations (document-identity permutations) with Wilson intervals and two
  held-out structures, and the online policy generalizes to them (8/8). Evidence still
  covers only the tested configurations; no claim beyond them.
- **D. Scenario difficulty.** `alternative_path` is easy (one-step disrupt);
  `benign_lookalikes` has not yet produced a blue false-positive failure. Multi-path
  families now exercise harder path-selection (block-and-recover, budget-vs-length),
  but only without an active blue team.

### Known limitations / blockers
- Mid-chain ATT&CK needs a multi-machine lab + snapshots (CR-1 Docker daemon down,
  CR-3 no authorized lab network). No fabricated effects were added.
- `red_metrics` detection/containment timing is principal-specific for containment
  but coarse for a global ACL; `blocked_by_environment` is approximate. It does **not**
  yet attribute a per-document `restricted`/`requires` denial, so a blocked single-path
  run reads `IN_PROGRESS` rather than `VERIFIED_FAILURE`; objective *verification* is
  unaffected (the witness reads effects directly).
- The rule-based planner cannot satisfy a prerequisite-gated path (it does not discover
  the index read), so `gated_longer_alternative` fails for the planner though the witness
  verifies it. The online-search policy (Phase 4.1B-2) does solve it, by exploration.
- A gated prerequisite is **epistemically unidentifiable** from observations (the gated
  read returns the same opaque `403` as any other denial). The online policy discovers it
  by *empirical search*, not identification, and needs ≈2× the clairvoyant budget. A
  future environment-design increment could add an **observable** prerequisite signal
  (e.g. a distinct `423 Locked` carrying a prerequisite id).
- Red's observation window is the last 10 own events; larger scenarios could exceed it and
  the online policy then re-browses (extra cost). Evaluation is without an active blue team.
- `recon` has no server-verifiable objective and is excluded from scored objectives.

### Suggested next research increments
1. An **observable** prerequisite signal (e.g. `423 Locked` + prerequisite id) so online
   planning reflects reasoning over an identifiable dependency rather than blind search.
2. Online planning and the 4-policy evaluation **under an active blue team** (this phase
   is structural, no blue); and an independent path generator so the witness no longer
   shares the solver's generator.
3. Attribute per-document controls in `red_metrics` (so a blocked single-path run reads
   `VERIFIED_FAILURE` with `blocked_by_environment`).
4. A capability-based red **skill** review (Phase 2); harder benign lookalikes (issue D).
5. Only after the above: a separate evaluation of the existing menu LLM red policy.

### Commits on this branch
| Commit | Milestone |
|---|---|
| `b883cc7` | Hybrid always-on active client |
| `efa951b` | Inert exfiltration stage |
| `0961d95`,`a68ac11` | Mission outcome score (gated on protected client work) |
| `f34eb5b` | Red-team synthesis (Phase 1) |
| `06e7cce` | Adaptive red planner (Phase 3) |
| `5f3d00a`,`1203682` | Verified red-objective metrics + attribution fix (Phase 5) |
| `86c08a1` | Stateful scenario system + feasibility solver (Phase 4) |
| `5e81c93` | Executable feasibility witness (Phase 4.1A) |
| `1aaf5a5` | Genuine multi-path scenarios + multi-path witness (Phase 4.1B-1) |
| _this_ | Online-search red policy + controlled evaluation (Phase 4.1B-2) |

### Last verified checks (this snapshot, Phase 4.1B-2)
`ruff check src tests`, `mypy --platform linux`, `mypy --platform win32` clean;
`pytest tests/world tests/population tests/range` → **251 passed**. New tests:
`tests/world/test_red_planner.py`, `test_red_metrics.py`, `test_scenario.py`,
`test_witness.py` (11), `test_multipath.py` (17), `test_online_planner.py` (18).

## 6. Validation evidence and its limits

The following receipts were inspected on the development workspace when writing
this handoff. They are **local ignored artifacts**, not files a clone receives.

| Receipt | Observed result | What it establishes |
|---|---|---|
| `runs/htb-full-tests.xml` | 0 failures/errors; 1,497 tests passed, 7 subtests passed, 1 skipped (JUnit suite total: 1,505, including subtests) | Most recent full offline suite, before the final guide-routing/export fix |
| `runs/htb-final-focused-tests.xml` | 28 tests, 0 failures/errors/skips | Focused validation after that final fix |
| `runs/htb-skills-final-audit.json` | PASS; 18 / 15 / 58 | Skill structure, references, context limits and role wiring |
| `runs/htb-practice-demo-20261105/proof.json` | `passed=true`; `htb_contacted=false`; `gemini_called=false` | Synthetic fixture through real local HTTP tools and Office; forensic session remains `PARTIAL` |
| `runs/htb-practice-demo-20261105/ui/verification.json` | PASS | Actual headless Chrome checks of query filters, citation hash, response gaps, HTML escaping and browser errors |

The skipped full-suite test is
`test_real_chrome_browser_job_has_screenshot_and_process_receipt`; it requires
`SABER_TEST_CHROME`. The separate Office Chrome check above does not substitute
for that browser-worker integration test. Neither check is full Docker/AD acceptance.

Prior implementation checks also included Ruff, both mypy platforms, the frozen
55/175/40 catalog and Office checks. Do not present those as rerun by this
documentation-only change. On another machine, rerun appropriate commands and
record its commit, environment and receipts. Do not claim GitHub CI or
GitGuardian is green without inspecting the actual remote checks.

## 7. Reproduce the useful entry points

Use new output paths for new runs; do not overwrite an investigation or existing
world. Commands below run from the repository root. See [notes.md](../notes.md)
for the fuller command reference and subsystem guides for deployment details.

Fresh clone, Python 3.12+ and uv:

```powershell
git clone https://github.com/Guofu24/Saber-bench.git
cd Saber-bench
git switch feat/environment-profiles
uv sync --locked
```

In the existing workspace, preserve optional tools already installed in `.venv`;
use `uv run --no-sync` instead of resyncing it unnecessarily.
For a local native world with all blue specialties:

```powershell
uv run --no-sync saber world init --out runs/handoff-world --clients 2 --execution native --blue-specialists
uv run --no-sync saber world run --out runs/handoff-world --ticks 30
node agent-office/bin/agent-office.js watch --world runs/handoff-world --open
```

The last command opens a viewer and stays running. Use another terminal to run
the world continuously. Agent Office requires Node.js 18+:

```powershell
uv run --no-sync saber world run --out runs/handoff-world --forever
```

From another terminal, inspect or request a stop:

```powershell
uv run --no-sync saber world status --out runs/handoff-world
uv run --no-sync saber world stop --out runs/handoff-world
```

After a stop request, resume explicitly with `world run --resume` and the same
`--out`. Change the roster before first run or initialize another world.

Optional bounded Gemini run, only with the operator's configured private pool:

```powershell
uv run --no-sync saber world run --out runs/handoff-world --llm --key-pool .\keys_pool.txt --call-budget 60 --ticks 30
```

That command makes real provider calls; add `--resume` if this world was stopped.
Do not inspect the key file to prepare the command.

Offline practice demo, with real local HTTP and no HTB/Gemini calls:

```powershell
uv run --no-sync saber training catalog
uv run --no-sync python scripts/smoke_training.py --out runs/handoff-training
node agent-office/bin/agent-office.js watch --world runs/handoff-training/world --open
```

Prepare and validate a SOC bundle without starting infrastructure:

```powershell
uv run --no-sync saber lab list
uv run --no-sync saber lab init --preset linux-small --name soc-small --out runs/handoff-soc.json
uv run --no-sync saber lab render --config runs/handoff-soc.json --out runs/handoff-soc-bundle
uv run --no-sync saber lab validate --bundle runs/handoff-soc-bundle
```

Rendering/validation is not runtime acceptance. On the intended isolated host,
follow [SOC lab deployment](SOC_LAB_VI.md): doctor, prerequisites/credentials,
provisioning as applicable, `lab up --on-target`, then `lab verify`. Do not start
the full stack on the current host simply to make a handoff or screenshot.

Development checks, selected according to changed scope:

```powershell
uv run --no-sync python scripts/validate_catalog.py
uv run --no-sync python scripts/check_skills.py --out runs/handoff-skills/audit.json
uv run --no-sync ruff check src tests scripts
uv run --no-sync ruff format --check src tests scripts
uv run --no-sync mypy --platform linux
uv run --no-sync mypy --platform win32
uv run --no-sync pytest --junitxml=runs/handoff-tests.xml
npm --prefix agent-office test
```

For viewer changes, install its locked dependencies if needed with
`npm --prefix agent-office ci`, then `npm --prefix agent-office run build:viewer`.
Run required checks once after the relevant change; do not repeatedly run the
full suite for documentation edits.

## 8. The last research discussion — proposed, not implemented

Immediately before requesting this handoff, the user supplied papers on cyber
gyms, red/blue agents, purple teaming and scenario generation. The useful
direction is to connect **client mission outcomes, common execution contracts,
diverse scenarios and evidence-based evaluation** to the existing system.
The paper list is not a request to replace the entire codebase with an RL gym.

| Source to revisit | Candidate contribution to SABER |
|---|---|
| [CybORG](https://arxiv.org/abs/2108.09118) and [CAGE Challenge 4](https://github.com/cage-challenge/cage-challenge-4) | Simulation/emulation interfaces; multi-defender evaluation where legitimate user work and mission failures affect outcomes |
| [NASimEmu](https://arxiv.org/abs/2305.17246) | Shared simulator/emulator contracts and topology generalization; explicitly account for differences in real exploit success |
| [Cyberwheel](https://github.com/ORNL/cyberwheel) | Investigate simulation-to-emulation evaluation and multi-agent experiments through an isolated adapter |
| [FARLAND](https://arxiv.org/abs/2103.07583) | Generate environment distributions and evaluate defense outside a single fixed topology |
| [Automated Generation of Cybersecurity Exercise Scenarios](https://arxiv.org/abs/2604.01079) | Explicit environment/role/storyline definitions and feasibility checks |
| [MITRE CALDERA](https://www.mitre.org/our-impact/intellectual-property/caldera) | Evaluate a future authorized emulation adapter with evidence-based action outcomes |
| [Scalable and automated Evaluation of Blue Team cyber posture](https://arxiv.org/abs/2312.17221) | Compare reports and TTP coverage while retaining SABER's independent evidence checks |

Research notes to avoid carrying inaccurate descriptions forward: CybORG++ is
associated with CAGE2/MiniCAGE, not a replacement description of CAGE4; the
high-fidelity autonomous cyber-defense paper introduces Cyberwheel; the PurpleAI
vision/PoC is not evidence of a deployed complete autonomous SOC. The generic
“Red/Blue team virtual exercise paper” in the supplied list still needs an
identifiable title/author/DOI. Recheck primary sources before implementing or
quoting results; no external engines or datasets were installed for this discussion.

Recommended next engineering sequence, **after the user chooses that work**:

1. **Common scenario specification:** assets, identities, network, client
   workflows, red/blue objectives, allowed capabilities, observation policy,
   seed, budgets and stop conditions. Acceptance: validation rejects impossible
   scenarios and replay records exact configuration/backend provenance.
2. **Client and service outcome metrics:** legitimate task success, service
   availability, disruption from containment, detection/response timing and
   uncertainty. Extend existing metrics; keep frozen benchmark scores unchanged.
   Acceptance: an indiscriminate defender that stops all work is penalized.
3. **Simulation/backend interface:** use fast trials plus selected real execution
   checks. Acceptance: preserve origin/fidelity, map observations/actions explicitly
   and test mismatches instead of treating a simulated success as a real compromise.
4. **Scenario diversity and held-out evaluation:** vary topology, workloads,
   sensor availability and adversary behaviors. Acceptance: fixed seeds replay,
   held-out families stay separate from learning, infeasible cases are reported.
5. **Purple after-action comparison:** attempted action → independently observed
   effect → telemetry available to blue → blue decision → client impact.
   Acceptance: evidence-linked gaps and reviewed/replayed skill or detection
   proposals, without exposing hidden evaluator truth during a run.
6. **Optional learned policies:** only after baselines and evaluation contracts
   work. Current skill learning is not RL; do not relabel it as RL. Avoid spending
   provider calls on every routine client action when a deterministic policy suffices.

Separately, the existing deployment acceptance remains unfinished: full target
Docker/AD execution, isolation/egress checks, sensors, guest responses/rollback,
external tool/service integrations and backup/restore must be demonstrated on
a suitable host. Code coverage cannot stand in for those checks.

## 9. Working agreements and continuation checklist

- The user explicitly requested **small professional commits and regular pushes**
  to the working branch. Inspect status, stage only task-owned files, run relevant
  checks, commit coherent changes and verify the push. Do not assume this branch
  has been merged into `main` or rewrite history without authorization.
- User-owned untracked inputs at handoff: `ir.py` and
  `DFIR_Handbook_Chuyen_Sau_2026.docx`. Keep them untouched/uncommitted unless the
  user asks. They will not be present on another machine after a normal clone.
- Keep secrets and raw/private evidence out of commits, terminal output and
  public snapshots. Older GitGuardian findings concerned test fixtures in PR
  history; current ephemeral markers do not erase old commits. Do not recreate
  those strings, claim remote checks are resolved or force-push to hide a finding.
- Preserve runtime boundaries: fixed/allowlisted actions, authorized targets,
  role/tenant isolation, private truth and independently checked effects.
  Do not replay uncertain external effects blindly. Durable receipts, response
  TTL/rollback and recovery behavior matter as much as the happy path.
- README stays primarily English with the Vietnamese companion. Root original
  code/docs use **Apache-2.0** ([LICENSE](../LICENSE), [NOTICE](../NOTICE));
  Agent Office retains its [MIT license](../agent-office/LICENSE). External tools,
  dependencies, datasets and course materials retain their own terms.
- Prefer existing compatible infrastructure and the current virtualenv. No
  unnecessary reinstall, production mutation, new billing or unrelated rebuild.
- Record limitations plainly: implemented adapter ≠ installed tool; integrity
  check ≠ correct analysis; review recorded ≠ exercise passed; local smoke ≠
  full target acceptance; skill coverage ≠ proven model competence.

Useful recent checkpoints (inspect the actual diff before reverting):

| Commit | Milestone |
|---|---|
| `be68a27` | Document forensic workflows and preserve skill-learning headroom |
| `5dc0380` | English primary README and Vietnamese companion |
| `4c07fa5` | Apache-2.0 for SABER, preserving component notices |
| `5560885` | On-demand external-practice guides for red and blue |
| `b389aa1` | Offline HTB-informed practice and evidence review |
| `c633453` | Practice commands and explicit integration limits |
| `e9b0c46` | Correct role-guide routing and exported practice assets |

Use [rollback guidance](ROLLBACK_VI.md). Reverting code does not restore runtime
data; stop and back up affected state before changing versions.

For the next AI, the first actions are to read this handoff and repository
instructions, inspect `git status` / recent commits, identify the requested next
scope, and inspect its source/tests. Reuse what exists. Report what was changed,
what was actually exercised, what remains unverified, and the commit/push state.
Update this handoff when those facts change.
