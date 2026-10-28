# SABER Phase H report — client / attacker / blue agent populations

Written for: the account operator and an independent reviewer. All results reproduce from a clean
checkout under the offline suite (no LLM, no network, no quota). Nothing here is `READY_BENCHMARK`;
the frozen 175-subtask catalog, contracts, splits, grading invariants and Phases B–G are unchanged.

## One-paragraph summary

Phase H turns the live lab's three implicit roles into explicit, scripted agent populations and
runs them together as a scored detection benchmark. A **client** population overlays benign
background traffic; the **attacker** population is an allowlist of scenario families — the three
Phase F/G families plus a new `persistence` family — each with a server-side-derived, agent-
independent label; the **blue** population is the detectors under test. The design's non-negotiable
is enforced in code: blue is the scored contestant, client + attacker are environment generators,
and every label is derived from a real server-side effect (access log / filesystem / autostart
store), never from an agent's claim. The headline result is the opposite of Phase G's ceiling
saturation: with benign client noise and hard negatives applying genuine false-positive pressure, a
precise conventional rule scores recall 1.0 / precision 1.0 / 0 FP while a naive floor collapses to
precision 0.385 with 73 false positives over 12 episodes — the benchmark **discriminates**. This is
automated-lab ground truth, scripted and non-LLM; it is not expert-validated gold and promotes no
subtask to `READY_BENCHMARK`.

## H1 — Client population (benign background-noise driver)

`saber.range.live.client_driver.client_noise(rng, clients, tricky)` models ordinary users (browse /
search / successful login) as a seeded, jittered **scenario generator**, not a scored contestant. It
is benign *by construction* — no SQL token combination, every `/login` uses the valid password (so
never a 401), and no server-side-script upload — so composed into any family it adds only benign log
lines and leaves the server-side attack truth unchanged. `run_episode(noise_clients=N)` overlays it
through a separate rng stream (the attack portion is byte-identical to the no-noise run); default 0
preserves prior behaviour. CLI: `saber range noise`, `saber range run --noise-clients N`. Tests pin
determinism, the benign-by-construction invariant, and an end-to-end non-perturbation check across
all four families (noise keeps the SAME malicious targets, only adds benign lines).

## H2 — New attacker family: `persistence` (autostart / scheduled task)

A new family parallel to `fs_change`, with the same independent-truth contract. The service exposes
`/cron/add`; content is decided server-side — a job whose name carries a persistence-abuse token
gets an **inert** `LAB_AUTORUN_MARKER` (nothing scheduled or executed), an authorized job
(backup/logrotate/...) gets benign content and is a hard negative. Truth is derived from the real
stored file on disk (`_derive_truth` `persistence` branch), cross-checked `derived == generated`,
with hashed `cron_state` evidence. A precise conventional detector (abuse-token regex) matches truth
exactly; a naive "any `/cron/add`" rule over-flags the authorized jobs. IR is propose-only for this
family (no reversible lab action claimed). All markers are inert (no live malware signature).

## H3 — Allowlist registry + Track-A detection benchmark

**Allowlist registry** (`saber.range.live.attack_registry`): every runnable family is bound to its
independent truth basis, inert marker, and benign hard negative. A test asserts the allowlist
*exactly* covers the runnable scenarios, so a new family cannot reach the lab without declaring, in
code, how its label is independently verified — the design's non-negotiable #2 made testable.

**Track-A detection benchmark** (`saber.soc.detect_bench`, `saber soc detect-bench`): each detector
runs over families × seeds with client noise; per episode it scores TP/FP/FN/TN against the sealed
truth (passed only to the scorer, never the detector), aggregated per detector with cluster-
bootstrap 95% CIs (the cluster is the family). Live result, seeds 1–3, `noise_clients=3`, 4 families
× 3 seeds = 12 episodes (all cross-checks and resets OK; evidence in
`range_evidence/soc/detect_bench_seeds1-2-3_noise3.json`):

| Detector | Recall (95% CI) | Precision (95% CI) | FP total | FN total | Episodes with FP |
|---|---|---|---|---|---|
| conventional | 1.000 [1.00, 1.00] | **1.000** [1.00, 1.00] | **0** | 0 | 0 / 12 |
| naive (floor) | 0.908 [0.73, 1.00] | **0.385** [0.17, 0.73] | **73** | 6 | 12 / 12 |

Per-family, the naive floor's false positives come from the authorized hard negatives and the benign
client noise it cannot distinguish; its recall dips below 1.0 because its word-level SQL rule misses
probes like `admin'--` that carry no flagged keyword. The gap between the two detectors is the point:
the client-noise + hard-negative design produces **genuine false-positive pressure**, so this
benchmark is not ceiling-saturated and separates detector quality cleanly.

## H3 (Track B) — response benchmark: detection quality → containment outcome

Detection is only half of what blue does; the other half is containing the incident. Track B
(`saber.soc.response_bench`, `saber soc response-bench`) runs the full case workflow on `fs_change`
— the one family with a verified, reversible IR action — so Incident Response EXECUTES an approved,
allowlisted, operator-bound quarantine and the effect is verified from the real post-action
filesystem. Containment targets come from the detector's confirmed findings, so the response outcome
is driven by detection quality. Live result, seeds 1–3, evidence in
`range_evidence/soc/response_bench_seeds1-2-3.json`:

| Detector | Containment recall | False containment (benign files quarantined) | Verified rate |
|---|---|---|---|
| conventional | 1.00 | **0** | 1.00 |
| naive (floor) | 1.00 | **17** | 1.00 |

Both detectors contain the webshell (recall 1.0, each quarantine verified from real fs state), but
the naive floor also quarantines **17** authorized/benign files across three episodes — real benign
operational impact that a detection-only score never surfaces. This is the operational lesson the
benchmark is built to show: a high recall bought with heavy false containment is not a good outcome.
The action stays reversible, allowlisted, operator-approved and lab-only; no real host is touched.

## What this is and is not

- **Is:** a genuinely executed, reproducible, scripted three-population loop with agent-independent
  labels, a discriminating Track-A detection score, and a Track-B response score that measures real,
  verified containment and its benign impact. It makes the client/attacker/blue idea concrete and
  measurable while preserving every isolation and leakage invariant.
- **Is not:** an agent-coordination result. The separation here is conventional-vs-naive detector
  quality, not "multi-agent beats single" (Phase G already showed no support for that on these
  families). Client and attacker are scripted (no LLM); an LLM sequencer and the `process`/`lateral`
  families remain future work (H4).
- **Is not:** expert-validated gold. Automated-lab ground truth remains a distinct, lower tier than
  independently signed labels (blocker ED-1). No `DEV_SIMULATION_ONLY` label was removed.

## Tier impact — none

| Readiness tier | Subtasks |
|---|---|
| VERIFIED_OFFLINE | 175 |
| BLOCKED_INTEGRATION (real-lab dependency) | 65 (18 vm + 47 soc) |
| READY_BENCHMARK | **0** |

Phase H adds capabilities and a discriminating detection benchmark; it changes no tier. The lab is
network-isolated (`internal: true`), launched only by the operator, uses inert markers throughout,
and mutates no real host. See `docs/AGENT_POPULATION_DESIGN_VI.md` for the design and the H4 backlog.
