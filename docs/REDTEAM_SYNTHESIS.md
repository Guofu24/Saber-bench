# SABER red-team synthesis

**Snapshot:** 2026-11-06. **Branch:** `feat/mission-outcome-metrics`.
**Audience:** engineers/AI continuing SABER's red (adversary-emulation) component.
**Status:** research synthesis, not a readiness claim. Nothing here promotes any
subtask to `READY_BENCHMARK`.

This document collects, in one place, everything the repository and the external
literature currently say about SABER's **red team**: the skills, the code/tools,
the governing docs and rules, and the outside papers/tools worth learning from.
It was assembled from a read-only sweep of the repo plus web research.

> **Framing (do not lose this).** In SABER the red team is an **inert
> adversary-emulation activity generator** confined to an isolated lab. Its only
> job is to produce realistic attack *signal* for the scored **blue** team to
> detect. Red never grades blue, never talks to blue, and never decides what
> "happened": **ground truth is always derived from real server-side effects,
> never from an agent's claim.** Everything below — including techniques borrowed
> from external tooling — stays at the level of *methodology, environment design
> and ATT&CK coverage of inert traces*, never operational exploitation.

---

## 0. The one rule and the shape of the system

- **blue = scored contestant; client + red = environment generators.** The label
  is always derived from real observed effect, never the agent's narrative.
  (`docs/AGENT_POPULATION_DESIGN_VI.md`, `docs/PHASE_H_REPORT.md`)
- Red has **two inert surfaces**:
  - **A. Continuous world** (`src/saber/world/`): in-process actors over a strict
    tool allowlist; truth is the server-computed `effect` dict.
  - **B. Live range** (`src/saber/range/live/`): seeded attacker *scenarios* send
    inert HTTP strings at a real loopback subprocess; truth is derived from the
    service's own access log + resulting filesystem/cron state, scored by an
    independent verifier.
- `population/` wraps the range with an LLM menu; `lab/` has **no red worker of
  its own** (it runs the world in `range` mode); `vm` is a **defensive** subtask
  environment, not a red execution mode.
- The frozen benchmark (55 NICE tasks / 175 subtasks) is **entirely defensive**.
  Red covers **zero** catalog subtasks; attack terms appear only as *targets of
  blue investigation*.

---

## 1. Red-team skills

Two skills under `.claude/skills/`, each with a `SKILL.md` + `reference/` folder.
Prose is Vietnamese except the shared `external-practice.md` (English). Red frames
itself as an inert emulation generator; it does not evaluate or contact blue.

### 1.1 `redteam-initial-access`
Initial-access phase playbook. Six non-negotiables: allowlist-only actions; inert
effects; range-only targets; never self-report results; log every action for
replay; no `sudo`/self-provisioning. "Authorized pentest is red's job **only when
the scenario grants a license**, recorded by the scenario, not self-declared."

**Initial-access technique menu (verbatim):**

| Kỹ thuật | Cách mô phỏng (trơ) | Đối thủ thật làm thế nào cho giống |
|---|---|---|
| Dò quét cổng | gửi kết nối thăm dò tới dải host/cổng của lab | ngang (một cổng nhiều host), dọc (nhiều cổng một host) hoặc khối; có nhịp, có thể ngoài giờ |
| Thăm dò/khai thác ứng dụng web | request mang chuỗi probe SQLi/XSS/LFI trơ tới dịch vụ web của lab | trộn probe với request trông bình thường; thử nhiều tham số; dừng khi có phản hồi khác thường |
| Upload webshell | tải lên webroot sandbox một script mang **marker webshell trơ** | đặt tên dễ lẫn, đặt cạnh các script hợp lệ |
| Tấn công đăng nhập | chuỗi đăng nhập sai tới endpoint đăng nhập của lab (brute force), hoặc ít lần trên nhiều tài khoản (spray) | có thể kết thúc bằng một lần đăng nhập đúng với tài khoản "bị lộ" mà kịch bản cấp |
| Phishing | gửi email mô phỏng tới hộp thư lab, kèm link/tệp trơ | khi range có dịch vụ mail/IdP mô phỏng |
| Khai thác dịch vụ phơi ra ngoài | gửi payload probe trơ tới dịch vụ có phiên bản dễ tổn thương trong lab | khi range có dịch vụ đích tương ứng |

References: `campaign-planning.md` (scope/evidence discipline; objectives are
observable states, not "HTTP 200"; lock versions; keep failed attempts; NIST
SP 800-115 + MITRE emulation plans) and `access-validation.md` (bounded test loop;
outcome taxonomy `not attempted / attempted / blocked by control / executed
without objective / objective observed / unknown`; hand off only *verified*
capability, never passwords/tokens).

### 1.2 `redteam-post-exploitation`
Post-exploitation phase playbook (assumes a foothold). Inherits all initial-access
rules and adds: **nothing is actually scheduled or executed** (persistence =
inert markers; processes = lab-only menu processes; connections reach only an
**internal lab sink**); "anti-forensics" is a simulated marker action only.

**Post-exploitation technique menu (verbatim):**

| Kỹ thuật | Cách mô phỏng (trơ) | Đối thủ thật làm thế nào cho giống |
|---|---|---|
| Persistence | ghi mục autostart/cron/service/task mang marker trơ vào kho của lab | đặt tên giống tác vụ cập nhật hợp lệ; nhiều kênh dự phòng (cron + systemd + profile) |
| Thực thi & nguỵ trang | chạy tiến trình lab-only có tên giả tiến trình hệ thống, tham số mã hoá | tên sai một ký tự (`svch0st.exe`), chạy từ thư mục tạm, cha bất thường |
| Tài khoản giả | tạo tài khoản lab mới | tên trông như tài khoản dịch vụ |
| Di chuyển ngang | đăng nhập/kết nối từ máy đã chiếm sang host khác **trong lab** bằng tài khoản đã chiếm | dùng công cụ quản trị từ xa, ngoài jump host, ngoài lịch quản trị |
| C2 / tunneling | hành vi tới sink/domain nội bộ qua menu lab | nhịp/kích thước theo scenario; periodicity/cổng không phải đặc tính bắt buộc của C2 |
| Chống điều tra | hành động mô phỏng: đánh dấu xoá log bảo mật, dừng service EDR lab, lùi timestamp tệp lab | làm ngay sau hành vi chính để che dấu |
| Exfiltration | trong world: `collect` tài liệu đã đọc rồi `exfiltrate` tới sink trơ nội bộ (không có kênh ra ngoài) | chia nhỏ, giờ thấp điểm |

**Operator note (critical):** most of this table needs a **multi-machine lab with
an isolated internal network + snapshot VMs**. When the range lacks them, the
technique is **unusable** and the agent must not simulate the effect. References:
`impact-validation.md` (per-objective prerequisite/evidence table; "do not perform
a technique that exists only in the table") and `campaign-closeout.md` (inventory +
clean up only own artifacts; blue learns results only via operator-run review).

### 1.3 External-practice hook (`reference/external-practice.md`, shared)
HTB-inspired, SABER-authored methodology. Adds **guidance only, not execution
rights**. An HTB URL is a content reference, never an attack destination. If the
required executor is absent, record the missing capability — do not translate
instructions into an ungranted shell call. Routed via `consult_skill` topics
`external-practice` / `redteam-initial-access--external-practice`.

### 1.4 Cross-population boundaries
- `soc-orchestrator/SKILL.md`: never share red's plan with blue; never pass
  red/client info to blue — blue works only with monitored data.
- `client-user/.../benign-lookalikes.md`: authorized pentest / payloads at a
  patched host are **red's job with a scenario license**, not the client's.

---

## 2. Red-team code & tools

Ground truth is the server-computed `effect` dict, initialised fresh per action
([environment.py](../src/saber/world/environment.py)) and converted to
metrics/incidents; an incident is any `INCIDENT_EFFECTS`, never an agent claim.

### 2.1 Capability table

| Action/Capability | Location | Server effect / evidence | ATT&CK | Inert guarantee |
|---|---|---|---|---|
| `RED_TOOLS` allowlist | [models.py:124](../src/saber/world/models.py#L124), granted :167 | Defines the only callable tools; `act()` rejects others with 403 | — | Frozenset; no shell/file/net tool exists |
| Roles recon/access/impact | [models.py:18](../src/saber/world/models.py#L18) | — | — | Validator rejects any other red role |
| `browse` | environment.py:364 | 200 + doc link list | Discovery T1083/T1087 | In-store list only |
| `search` | environment.py:377 | 200; own/public docs only | Discovery T1083 | Owner-filtered |
| `login` (`typo`→failed auth) | environment.py:385 | 200 session / 401 | Initial Access T1078; T1110 | Dict session flag |
| `read_document` | environment.py:406 | `unauthorized_access` → `unauthorized_reads` | Collection T1005 | Synthetic store; ACL gate |
| `collect` | environment.py:442 | `collected_bytes` (0 if authorized) | Collection T1074 | Copies previously-read synthetic bytes; requires prior read |
| `exfiltrate` | environment.py:464 | `exfiltrated_bytes`; writes `exfil` record | Exfiltration T1041 | **No socket/URL/endpoint**; local sink marker; requires prior collect |
| `register_job` | environment.py:482 | `unauthorized_job` → `unauthorized_jobs` | Persistence T1053 | "Inert lab automation; no OS execution" |
| `disrupt` | environment.py:499 | `disruption`; sets `down_until` | Impact T1489 | Flips in-store service flag for `incident_ttl_ticks` |
| `share` | environment.py:358 | 200; own-team bus only | — (not C2) | Team-internal messages |
| scripted `_red` policy | [agents.py:66](../src/saber/world/agents.py#L66) | Emits above; off-surface tools dropped by `parse_plan` | per-action | Deterministic |
| `ATTACK_MAP` | environment.py:67, report :852 | Labels only | all 8 world tools | Report `DEV_SIMULATION_ONLY` |
| Range **web_sqli_probe** | range/live/scenarios.py:44; truth controlplane.py:39,:225 | Malicious iff access-log target carries SQL token combo (server-side) | web probe ≈T1190 | Inert probe strings to loopback |
| Range **auth_bruteforce** | range/live/scenarios.py:67; truth controlplane.py:229 | Malicious iff per-user 401 volume ≥ threshold | Credential Access T1110 | Bounded failed logins; password redacted |
| Range **fs_change** (webshell) | range/live/scenarios.py:99; service_main.py:58 | Malicious iff script exists on disk with inert `<?php` marker | ≈T1505.003 | Non-executable marker; sandboxed `--fsroot`; reversible IR |
| Range **persistence** (autostart) | range/live/scenarios.py:130; service_main.py:87 | Malicious iff autostart entry on disk with `LAB_AUTORUN_MARKER` | Persistence T1053 | "inert; not scheduled, not executed"; sandboxed `--cronroot` |
| Range allowlist ↔ verifier binding | range/live/attack_registry.py:31 | Each family pinned to server-side `truth_basis` + benign `hard_negative` | — | A test asserts allowlist == runnable scenarios |
| Population `RedAgent` (LLM) | population/agents.py:63; menus.py:195 | Chooses menu action IDs only; validated before dispatch | per-family | Off-menu dropped; volume clamped; loopback `/`-paths only |

### 2.2 By execution mode
- **application (world default):** actions execute directly in the store.
- **native:** the same red action is carried over a **real loopback-only**
  DNS→TCP→HTTP exchange + bounded file write by a `python -I` worker, producing
  genuine process/file/DNS/network telemetry. **Adds no new red capability** — a
  measurement wrapper; the private DNS responder only ever returns `127.0.0.1`.
  Native telemetry is shown to **blue only**.
- **range:** four allowlisted families send a seeded `{target,intent}` plan at the
  real service subprocess; non-`/` targets are **refused** to guarantee loopback;
  truth is `_derive_truth` from the access log + real fs/cron state, with an
  independent SQLi detector and a `derived == generated` cross-check; service is
  killed and reset-confirmed each episode. Red cannot achieve code execution —
  webshell/autostart payloads are non-executable markers. `world run` **forbids**
  range mode (range uses `saber lab`).
- **lab:** no independent red; reuses the world in range mode. `lab/application.py`:
  "No OS exploits or arbitrary commands. Red exercises only lab document authorization."
- **vm:** a **defensive** subtask environment; verifies defensive stateful actions
  against a sealed before-snapshot. **No runnable red capability.** The only live
  containment is reversible, approval-bound, token-separated webroot quarantine.

### 2.3 Mission scoring interaction
The private mission outcome ([mission.py](../src/saber/world/mission.py)) scores the
defender on protected client work × detection quality. Red's effect is felt only as
client-denied-outage/collateral and verified incidents; **exfil volume is not a
direct score** today (it contributes only via incident recall).

---

## 3. Governing docs & rules

- **`docs/SECURITY.md`** — authoritative policy. `dev` vs `lab` split, fail-closed;
  deny-by-default isolated network (config ≠ proof of isolation); synthetic
  accounts/throwaway creds only; every episode from a clean snapshot; **explicit
  per-episode operator approval before any live emulation (gate H3)**; emulation
  drivers accept only allowlisted IDs/validated params — **no arbitrary shell**;
  avoid malware payloads, live credential theft, stealth/persistence development,
  destructive actions. Separation of duties: blue never sees ground truth/snapshots/
  emulation; evaluator does no unapproved emulation. Gates H1–H5.
- **`docs/BENCHMARK_PROTOCOL.md`** — Track A DETECTION_ONLY (no containment) vs
  Track B RESPONSE_ENABLED (fixed pre-approved lab-only actions, TTL/rollback).
  Ground-truth schema with verification method + ATT&CK-pinned labels; `INVALID`
  episodes excluded from denominators (never a false negative); agents get opaque
  `episode_id` only; `as_of` gateway blocks future-event queries; gate G6 →
  `DEV_SIMULATION_ONLY` unless a real-telemetry isolated-lab pilot exists.
- **`docs/AGENT_POPULATION_DESIGN_VI.md`** (design) — the three-population design
  and five invariant laws: (1) label independent of agent; (2) attacker picks only
  from the allowlist, each family needs an inert executor **and** an independent
  state verifier; (3) absolute isolation (`network none`/`internal:true`, snapshot+
  rollback, no `sudo`, no self `docker pull`); (4) fail-closed + `DEV_SIMULATION_ONLY`
  (lab truth is `AUTOMATED_LAB_GROUND_TRUTH`, below expert gold); (5) no label
  leakage. Attacker reproducibility: run once, record trace + hashed evidence, seal
  truth at record time, score blue on the sealed episode.
- **`docs/AGENT_POPULATION_H4_DESIGN_VI.md`** (design) — LLM-ify the generator
  (still a generator, hard-validated against the allowlist, subscription-billing
  cap, no silent scripted fallback); VM/multi-machine to enable `process`/`lateral`
  (blocked on Docker/hypervisor); reverse engineering of **self-built benign
  binaries only** (never auto-pull malware; Ghidra pinned+sandboxed; IDA default blocked).
- **`docs/PHASE_H_REPORT.md`** (implemented, offline, scripted, non-LLM) — client
  benign-noise driver, `persistence` family, allowlist registry with a test
  asserting it covers runnable scenarios. 175 VERIFIED_OFFLINE, 65 BLOCKED_INTEGRATION
  (18 vm + 47 soc), **0 READY_BENCHMARK**.
- **`docs/CYBER_RANGE.md`** — what runs today (loopback, inert, server-side truth,
  hashed evidence) and precise blockers: CR-1 Docker daemon down (operator-only),
  no WSL/VirtualBox/qemu; CR-2 no SIEM/indexer; CR-3 no authorized lab net for `vm`;
  CR-4 binary-telemetry libs absent. No forensic tooling installed.
- **`docs/HTB_TRAINING.md`** — nine SABER-authored offline tracks incl. `red-web`,
  `red-enterprise`, `red-agent-evaluation`, `purple-validation`. **No HTB login/VPN/
  lab start/course download/live executor.** URLs are provenance only. Red/purple
  tracks have no auto practice-world; `prepare-world` creates blue roles only.
  `REVIEW_RECORDED` is not a pass.
- **`docs/ENVIRONMENT_FIRST.md`** — for a new host/VM/net change/attack emulation/
  destructive response: require operator-scoped authorization + isolated lab, else
  implement a safe adapter with tests but mark integration **BLOCKED**, never READY.
- **`lab/README.md` / `infra/README.md`** — isolated substrate (`internal:true`,
  read-only rootfs, cap-drop); "no attack tooling ships here"; provisioning only
  under operator control after H-gates; a passing `validate_lab_plan` is **not**
  proof of isolation.

---

## 4. External references (papers, environments, tools)

These inform **methodology and environment design only**. Two boundaries hold for
every item: (a) a simulator's internal "success" is **never** SABER ground truth —
SABER measures real server-side effects; (b) any real-execution emulation tool is
operator-gated, isolated-lab-only, and reduced to an **inert allowlist** in SABER.
The handoff already rules out installing any of these backends; none is present.

### 4.1 Gyms / simulation environments (RL research)
- **CybORG + CAGE Challenge 4** — the closest fit. Has **green agents** (ordinary
  users doing local work / reaching services) whose inability to work **penalizes
  the blue team**, with larger penalties for mission-critical zones while the
  mission is active; green agents can even hand red a foothold via a chance
  "phishing" event and generate occasional false alerts. Five blue agents each see
  only their own segment. **Borrow:** the mission-phase penalty structure and the
  green-agent → mission-outcome link (directly validates `mission.py`). *Caveat
  (handoff):* CybORG++ relates to CAGE2/MiniCAGE, not a description of CAGE4.
- **NASim / NASimEmu** — RL attack simulator + shared simulator/emulator contracts
  and topology generalization. **Borrow:** account explicitly for sim↔real exploit-
  success differences.
- **CyberBattleSim** (Microsoft) — Gym modelling a vulnerable network for red/lateral
  movement, with community blue-agent extensions. **Borrow:** abstract network/credential
  graph modelling; nothing executable.
- **FARLAND** (MITRE) — generative programs produce *distributions* of network
  environments for defender training/eval. **Borrow:** scenario diversity + held-out
  evaluation (roadmap step 4).
- **Cyberwheel** (ORNL, MIT license) — RL env with networkx topology; v2.0 added a
  **FIREWHEEL** emulator (sim↔emulation). Example trains a blue agent to deploy
  deception/decoys. *Critique:* heavy per-scenario configuration; results tied to
  detector assumptions. **Borrow:** sim-to-emulation evaluation discipline.
- **CyGIL** (DRDC) — stateless, ATT&CK-based gym with a unified emulator (CyGIL-E)
  and simulator (CyGIL-S); train fast in sim, transfer to emulation; studies red-
  agent generalization to network variation. **Borrow:** the unified sim/emulator
  contract idea; real execution stays operator-gated.
- **MAL Simulator** — attack/defense-graph based simulation. Reference only.

### 4.2 Adversary emulation (real execution — operator-gated only)
- **MITRE CALDERA** — automated adversary emulation on ATT&CK: *abilities* (per-
  technique implementations), *adversary profiles*, *operations*, agents/implants,
  async C2, ~1000 abilities (many from **Atomic Red Team**). In SABER this is a
  **future candidate adapter, not installed**; if ever adopted it runs only in an
  authorized VM/`windows-ad` profile, under H-gates, reduced to an inert allowlist —
  never on the local world. Defender will quarantine non-inert payloads.
- **MITRE ATT&CK / Atomic Red Team** — the technique taxonomy SABER already uses
  for `ATTACK_MAP`, labels and the technique menus. Pure reference data.

### 4.3 Scenario generation
- **Automated Generation of Cybersecurity Exercise Scenarios** (Skandylas & Asplund,
  arXiv 2604.01079) — two-phase generator (execution-environment + storyline) with a
  simulation backend (NASim/CybORG-like) **and** a libvirt emulation backend; releases
  a dataset of 100k sample scenarios. Notes the realism↔traceability trade-off and
  that storyline time scales quadratically. **Borrow:** the explicit environment/role/
  storyline spec + feasibility checks (roadmap step 1).

### 4.4 Red/blue/purple agent research
- **A Red Teaming Framework for AI-enabled SOAR** (arXiv 2605.17075) — LLM planner
  (sets intent every 20 steps, frozen) + PPO RL controller, evaluated in CybORG
  CAGE 4 vs an H-MARL blue team. Finding: standalone LLMs can't sustain multi-stage
  attacks; hybrid LLM+RL is stronger. A later paper reports RL+RL beats LLM+LLM in
  CAGE-4 (78.5% vs 18.0% disruption). **Borrow:** the idea of red deliberately
  stressing blue's automation — SABER already measures this via `false_containments`;
  add hard-negative scenarios rather than an RL attacker.
- **LLMs are Autonomous Cyber Defenders** (arXiv 2505.04843) — LLM blue agents in a
  CAGE-style setting. Reference for blue-side comparison, not red.
- **Scalable and automated Evaluation of Blue Team cyber posture** (arXiv 2312.17221)
  — compares red/blue reports against known-TTP databases. **Borrow:** after-action
  TTP-coverage comparison while keeping SABER's independent evidence checks (step 5).

### 4.5 Accuracy caveats carried from the handoff
- PurpleAI and "Purple Team Playbook" are a **vision/PoC and a thesis framework**,
  not deployable software.
- The generic "Red/Blue team virtual exercise paper" in the source list still lacks
  an identifiable title/author/DOI — do not cite it as evidence.
- Never treat an IOC match or a group name in a report as a conclusion of intrusion.

---

## 5. Consolidated ATT&CK coverage & gaps

**Covered by a runnable inert action:**

| Tactic | Action(s) | Surface |
|---|---|---|
| TA0007 Discovery | browse, search | world |
| TA0001 Initial Access | login/T1078; web_sqli_probe ≈T1190 | world, range |
| TA0006 Credential Access | auth_bruteforce/T1110 (volume); world login(typo) single-401 | range, world |
| TA0009 Collection | read_document/T1005, collect/T1074 | world |
| TA0010 Exfiltration | exfiltrate/T1041 (local marker, no channel) | world |
| TA0003 Persistence | register_job/T1053; persistence autostart; fs_change webshell ≈T1505.003 | world, range |
| TA0040 Impact | disrupt/T1489 | world |

**Gaps — described in the red skills but with no runnable inert action:**

| Tactic | Status |
|---|---|
| TA0002 Execution | none (native worker runs a fixed *benign* workload, not attacker-chosen) |
| TA0004 Privilege Escalation | none |
| TA0005 Defense Evasion | none (skill describes log-clear/timestomp; no action) |
| TA0008 Lateral Movement | none (single-app world; no pivot) |
| TA0011 Command & Control | none (`share` is team-internal, explicitly not C2) |

Net kill-chain: **Discovery → Initial Access → Credential Access → Collection →
Exfiltration → Persistence → Impact** are covered; the **mid-chain** (Execution /
PrivEsc / Defense Evasion / Lateral Movement / C2) is uncovered. Per the design
docs, the mid-chain needs a **multi-machine lab + snapshots** (blocked: CR-1/CR-3)
and, for each new family, an inert bounded executor **plus** an independent state
verifier **plus** a benign hard negative **plus** the `derived == generated`
cross-check before it may run.

---

## 6. Hard boundaries for red (non-negotiable)

1. **Allowlist only** — menu `action_id` + validated params; no shell, no real
   exploits/CVE weaponization, no downloading tools, no self-authored payloads.
2. **All effects inert** — simulated traces/markers only; no real malware; payloads
   must not be live AV signatures (Defender will quarantine the repo otherwise).
3. **Isolated lab / authorized targets only** — range services and lab machines
   only; no internet; connections reach only internal lab sinks; drop out-of-scope.
4. **No host mutation / no self-provisioning** — no `sudo`, no self `docker pull`/
   `run`, no `terraform apply`; operator does bring-up.
5. **Nothing actually scheduled or executed** — persistence/C2/process are inert
   markers; registered job ≠ ran; disrupt request ≠ service down.
6. **Never self-report/self-label** — truth is server-derived; red never labels a
   "compromised host"; an anomalous response is a lead, not proof.
7. **blue = contestant; client + red = generators** — the labeling line never crossed.
8. **No label leakage / separation of duties** — red never reads blue cases,
   evaluator truth, sealed truth, DB or `office.json`; prompts carry no label;
   `as_of` blocks future events; agents get an opaque `episode_id` only.
9. **Per-episode operator approval before live emulation** — restricted targets,
   time window, pre-reviewed profile (H3); isolation-check failure blocks emulation.
10. **No arbitrary command execution** against range machines — allowlisted IDs only.
11. **No malware/live credential theft/stealth development/destructive actions** —
    test-only ATT&CK-aligned emulation + benign lookalikes; anti-forensics is a
    marker action only.
12. **Containment constrained** — Track A: none; Track B: fixed pre-approved lab-only
    actions with TTL, rollback, separate executor token, post-action verification.
13. **RE targets are self-built benign binaries only** — never auto-pull malware;
    Ghidra pinned+sandboxed; IDA default blocked.
14. **Fail-closed to DEV_SIMULATION_ONLY / BLOCKED_INTEGRATION** — missing lab/auth/
    sensors → blocked; lab truth is below expert gold, never READY_BENCHMARK.
15. **Record / reproducibility** — log every action; seal truth at record time; lock
    versions; never delete failed attempts.
16. **No out-of-band red↔blue channel** — blue learns red's results only via an
    operator-run after-action review, never during blind detection.

---

## 7. What this means for building red further

1. **Highest-value, lowest-risk next step stays in the world:** add mid-chain inert
   actions that produce new *detectable* traces without needing multi-machine infra,
   mapped to ATT&CK, each with a server-measured effect and an independent check —
   the same pattern as the new `exfiltrate` stage. Candidates that fit a single-app
   world: a **defense-evasion marker** (e.g. a logged "log-clear" request that is
   itself detectable, never actual evasion), and **privilege misuse** (red using an
   admin-only tool). Each must be *detectable*, never aid real evasion.
2. **Lateral movement, real C2 and execution need the multi-machine lab** (CR-1/CR-3
   blockers). Treat as design-gated; do not simulate the effect without the machine +
   observer.
3. **Borrow CAGE 4's mission-phase weighting** to extend `mission.py` (phases where
   client work matters more), and **scenario specs** from the Automated-Generation
   paper for diversity + feasibility checks.
4. **Do not install CALDERA/CybORG/Cyberwheel backends** or treat their internal
   success as truth. If an emulation adapter is ever wanted, it is operator-gated,
   isolated-lab-only, inert-allowlisted, with the independent verifier intact.
5. **Keep every addition fail-closed and `DEV_SIMULATION_ONLY`.** 0 subtasks are
   READY_BENCHMARK and nothing here changes that.

---

*Sources (web, reviewed 2026-11-06):*
[CAGE 4](https://cage-challenge.github.io/cage-challenge-4) ·
[Red Teaming SOAR (2605.17075)](https://arxiv.org/pdf/2605.17075) ·
[Cyberwheel (ORNL)](https://www.ornl.gov/publication/towards-high-fidelity-training-environment-autonomous-cyber-defense-agents) ·
[Automated Scenario Generation (2604.01079)](https://arxiv.org/pdf/2604.01079) ·
[CALDERA](https://github.com/mitre/caldera) ·
[CyGIL (2304.01366)](https://arxiv.org/pdf/2304.01366) ·
[LLMs as Autonomous Cyber Defenders (2505.04843)](https://arxiv.org/pdf/2505.04843) ·
[Scalable Blue Team Evaluation (2312.17221)](https://arxiv.org/abs/2312.17221)
