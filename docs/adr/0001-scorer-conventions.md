# ADR 0001 — Scorer conventions v1 for source formulas

Status: ACCEPTED for DEV (`score_v1`). Each convention below resolves an ambiguity in the
source formula text. They are implemented in `src/saber/grading/` and covered by golden
tests. Changing any convention bumps `SCORER_VERSION` and requires regrading all baselines.
Items marked **ADJUDICATE** still need sign-off from the business owner before
`READY_BENCHMARK`; until then results are `DEV_SIMULATION_ONLY`.

## Sets — `set/*`, `setF2/*`, `max(0, M′/M − N′/(N′+M′))`, `F1`, `F2`

| Case | Convention | Rationale |
|---|---|---|
| Duplicates in prediction | Collapsed after canonicalisation; one element counts once | Prevents padding |
| Truth empty, prediction empty | score 1.0 | Correct benign negative must be scoreable |
| Truth empty, prediction non-empty | score 0.0 | Pure false positives |
| Truth non-empty, prediction empty | score 0.0 | Nothing found |
| `M′/M − N′/(N′+M′)` with `N′+M′=0` | second term 0 → score 0 when M>0 | prediction empty |
| Abstain (`answer` field null/absent) | treated as empty prediction, `abstained=true` in trace | explicit |
| Fβ with partial credit "sai X = 0.5 phần tử" | element matched on key with wrong attribute counts 0.5 toward TP in both precision and recall | source text |
| Canonicalisation | per subtype (host lower-case, strip trailing dot/domain; IP normalised; sha256 lower hex; process basename lower; account `DOMAIN\user`→`user` lower; technique `T1059.001` upper; IOC defanged→refanged lower; email lower; paths `\`→`/` lower on Windows kinds) | avoid ambiguous string joins |

**ADJUDICATE:** whether `set/host` should treat `host01` and `host01.corp.local` as equal
(currently: yes, FQDN suffix stripped).

## Order — `Kendall tau`, `ρ`, `order`, `order+recall`

| Case | Convention |
|---|---|
| τ | Kendall τ-b over elements present in both lists, ranks from list position |
| Mapping to [0,1] | `score = max(0, τ)` — negative correlation gives 0 (source writes `max(0, ρ)` for ρ) |
| Missing elements | excluded from τ; reported as `missing`/`extra` counts; `recall` = |common|/|truth| |
| Fewer than 2 common elements | τ undefined → score 0, trace `tau_undefined` |
| `order+recall` / `0.5·τ + 0.5·recall mốc` | `0.5*max(0,τ) + 0.5*recall` |
| Ties | ranks are list positions (no ties on prediction side); truth ties, if any, use τ-b |

**ADJUDICATE:** tie policy for truth lists that contain simultaneous events.

## Numeric — `num/±X`

| Tolerance token | Meaning |
|---|---|
| `±0`, `±0′` | exact (integers) / same minute for timestamps |
| `±5′` | within 5 minutes (timestamps compared in UTC) |
| `±0.5pp` | absolute difference ≤ 0.5 percentage points |
| `±20%` | relative difference ≤ 20% of truth (truth 0 → exact) |
| `IoU≥0.8` | interval intersection-over-union ≥ 0.8 |

Non-parseable / wrong-type prediction → 0, trace `type_error`.

## Enum — `enum`, `enum/alias`

Case-insensitive, whitespace-trimmed; alias tables are explicit per subtask (e.g. APT41 =
Winnti = Barium). Unknown label → 0, `invalid_label=true`. Abstain label where the source
defines one (`khong_du_can_cu_quy_ket`, `khong_du_du_kien`) is a first-class enum value.

## Citations — `cite`, `× CITE`

A reference resolves only if it names an evidence ID present in the agent-visible inputs of
the episode (grep-able). `CITE` gate = 1 iff at least one reference is supplied and **no**
reference is unresolved (hallucinated refs fail the gate). `gate/phần tử` (per element):
elements lacking a resolvable reference are removed from the numerator only.

## Gates — `gate`, `× [gate]`, `cap`, `Π[...]`

| Mode | Effect when failed |
|---|---|
| `zero` (default for `× [x]` and `gate`) | total score 0 |
| `factor k` (`gate 0.5`) | total score × k |
| `cap k` (`cap 0.5 nếu ...`) | total score = min(score, k) |
| `invalid` | episode INVALID (not a 0; excluded from denominators) — used only for infrastructure preconditions (snapshot contaminated, isolation unverified) |

Gates are evaluated **after** components; the trace lists every gate outcome.

## Exec — `exec/corpus`, `exec/replay`, `exec/pcap`, `exec/samples`

Rules run in a subprocess sandbox (`python -I`, stdin JSON, no filesystem/network, wall-clock
timeout, pattern length cap). Timeout or parse error → `parse_ok=false` → score 0 (source:
"Rule không parse hoặc timeout → 0"). Supported DEV engines: Python `re` (regex rules),
`saber-yara-subset` (strings + any/all/N-of condition), structured filter DSL for replay.
Real YARA / Suricata / vendor SIEM engines are `BLOCKED_INTEGRATION` adapters.

## State — `state/*`

Verifier compares sealed before/after snapshots taken **outside** the guest:
`machine_unchanged` = identical file hash/size set and identical service/cron/systemd/user
inventories; `clean_intact` = every protected file byte-identical (hash + size); removal
gates use content-hash scans of the whole tree so relocation does not count as removal.
DEV uses `LocalDirMachine` (directory tree = guest) and is labelled `DEV_SIMULATION_ONLY`;
real hypervisor snapshots are `BLOCKED_INTEGRATION`.

## Invalidity vs zero

Missing required evidence, unhealthy data source, contaminated snapshot or unverified
isolation → episode `INVALID` and excluded from efficacy denominators. Wrong answers → 0.

## Review-driven refinements (pre-freeze, still `score_v1`)

These were finalized during independent review, before any blind-test freeze, so no regrade is
owed yet. Once `score_v1` is frozen for a hidden split, any further change bumps `SCORER_VERSION`.

- **Order / Kendall τ completeness.** `order` items may use `tau*recall` so that ordering a
  correct *subset* cannot earn full credit (score = `max(0,τ) · recall`). T0173.001 uses this; a
  correct 2-of-30 subset scores about `0.067`, a reversed-but-complete list scores `0`, and a
  complete correct list scores `1.0`. This matches the source warning that τ must be paired with
  coverage (`docs/GRADER_CONTRACT.md`).
- **VM state verification is evaluator-derived.** For `vm` subtasks the agent declares the actions
  it took (`read`/`remove`/`move`/`modify`); the evaluator applies them to the sealed
  before-snapshot and runs the state gates on the derived after-snapshot. The agent never supplies
  an after-snapshot, so it cannot fabricate hashes or echo the before-state. Real execution with an
  independent out-of-guest capture remains `BLOCKED_INTEGRATION`.
- **No label bleed into agent inputs.** A decision label (verdict, classification) must be
  *inferable* from agent-visible evidence but never byte-present in the inputs, and the two classes
  of a fixture must differ in their evidence, not in a hidden flag. Enforced by
  `tests/security/test_truth_isolation.py` (value-level check + per-class discriminability).
- **B0 abstention vs failure.** Where a subtask has no rules oracle, B0 abstains; those subtasks
  are excluded from B0's aggregate rather than scored `0`, and listed under `abstentions` in the
  experiment report. Bootstrap CIs over fewer than three subtasks are flagged `reliable_ci=false`.
