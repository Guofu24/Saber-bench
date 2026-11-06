# Historical handoff — Phase G at `28ff4c8`

> Archived on 2026-11-05. The text below describes an earlier project state.
> Its scope restrictions, setup assumptions, blockers and validation results are
> historical, not current instructions or current acceptance evidence. In
> particular, the subscription-only statement, population status and Ghidra gap
> have been superseded. Documentation and ignored local reports do not load or
> travel with a clone automatically. Start with the [current handoff](../HANDOFF.md).
> Paths in the preserved text are relative to the repository root.

# SABER — handoff for a Claude (or engineer) picking this up on another machine

Written for: a fresh Claude Code session / engineer cloning this repo on a different machine.
Everything in `CLAUDE.md`, `docs/`, and `.saber-autonomous/REPORT.md` travels with git and is loaded
automatically when the repo is opened. This file adds the *conversation-specific* context that is NOT
otherwise written down: the current decision state, what is blocked, and the directions under
discussion that have no code yet.

Last updated against commit `28ff4c8` (Phase G finalized). If `git log` shows a newer HEAD, trust the
code and `REPORT.md` over this file.

## 1. Get the code and set up

```bash
git clone https://github.com/Guofu24/Saber-bench.git
cd Saber-bench
uv sync --locked                                  # Python 3.12 env (uv; if uv not on PATH: python -m uv ...)
uv run python scripts/validate_catalog.py         # verify frozen 55/175/40 catalog + source hash
uv run pytest                                      # offline suite must be green on a clean checkout
```

Everything offline reproduces from a clean checkout. LLM runs use the **claude.ai subscription CLI**
(`claude -p` spawned in an isolated cwd), never a paid API key — see §5.

## 2. How to run it

```bash
# Offline / deterministic
uv run saber task list --implemented
uv run saber smoke --subtask T1112.001            # build -> oracle -> reference -> grade
uv run saber experiment --seeds 1,42

# Live lab (real loopback HTTP service, real telemetry, hashed evidence, clean reset)
uv run saber range scenarios                       # web_sqli_probe, auth_bruteforce, fs_change
uv run saber range run --scenario web_sqli_probe --seed 1 --out evidence
uv run saber range bench --no-llm --seeds 1,2,3    # T0020 contract on live telemetry

# Four-service SOC workflow + evaluation
uv run saber soc run --seeds 1,2 --detector conventional      # coverage matrix
uv run saber soc eval --llm --model haiku --seeds 1,2,3        # 6-config ablation (subscription)
uv run saber soc adjudicate                                    # gold-label package (PENDING_EXPERT_REVIEW)

# Strong-baseline comparison on the 12 file-mode gold pilots
uv run saber gold compare --llm --model haiku --seeds 1,2,3
```

Note: `saber range run --out evidence/` writes local run output. `evidence/` is a scratch output dir —
do not commit it.

## 3. Current state (as of 28ff4c8)

Five-tier readiness, **unchanged by any run so far**:

| Tier | Count |
|---|---|
| VERIFIED_OFFLINE | 175 |
| BLOCKED_INTEGRATION (real-lab dependency) | 65 (18 vm + 47 soc) |
| READY_BENCHMARK | **0** |

- Phases B–G are complete and committed on `main`. **Phase H** (scripted client/attacker/blue agent
  populations) is complete on branch `feat/agent-population-h1`, **not yet merged** — latest report
  `docs/PHASE_H_REPORT.md`, design `docs/AGENT_POPULATION_DESIGN_VI.md`. `docs/PHASE_G_REPORT.md`
  remains the latest report on `main`. The tier table below is unchanged by Phase H.
- **Phase G headline (honest, anti-hype):** the six-config evaluation is **ceiling-saturated** —
  `conventional == single == specialist == multi_agent == 1.0` on both live families; the reviewer's
  second call buys nothing (`multi_agent − single = 0.00`). **No support for "coordination beats more
  calls."** The only sub-1.0 cells are single-episode noise at n=3, and they move between runs.
- **Gold pilots (harder, non-ceiling):** oracle 1.00; a **conventional strong baseline 0.97 beats
  every LLM config**; single ≈ specialist ≈ multi_agent (~0.86–0.87, tied). Same conclusion.

## 4. Decisions made in the last session

- **Kept `28ff4c8` as canonical.** A later re-run of `soc eval`/`gold compare` was executed; it only
  moved the noise to a different cell and produced timestamp/hash/keyed-id churn plus one new
  artifact. We **reverted the working tree** to `28ff4c8` and removed the scratch outputs, because
  `docs/PHASE_G_REPORT.md` already cites `28ff4c8`'s numbers and the verdict did not change.
- Do **not** infer improvement from ceiling-saturated results. Do **not** start "Phase H" / expand the
  framework without an explicit request.

## 5. Hard rules any continuation must obey (from CLAUDE.md / docs/SECURITY.md)

- **Billing: subscription only.** The `./run.sh` supervisor uses claude.ai subscription mode. Never
  enable paid API credits or switch billing. The agent cannot authorize paid usage.
- **No automatic host mutation.** No `sudo`, no `terraform apply`, no starting an attack, no mutating a
  real host. No auto `docker pull` / `docker run` — the operator does that by hand.
- **Fail closed.** Any adapter without real access returns `BLOCKED_INTEGRATION` or is labeled
  `DEV_SIMULATION_ONLY`. Never fabricate telemetry or manufacture private gold labels.
- **0 READY_BENCHMARK** stands until an authorized lab + an independent expert sign-off exist. Automated
  lab ground truth is a lower tier than independently-validated gold (still 0).

## 6. Open blockers

| # | Blocker | Who unblocks it |
|---|---|---|
| CR-1 | local Docker daemon is **down**; no `gh` CLI on this host | operator starts Docker/WSL2 for a local container run, or triggers the opt-in `cyber-range` GitHub workflow |
| ED-1 | 0 independently-validated gold labels | a qualified SOC/IR lead signs off `docs/adjudication/` |
| G-1 | 3 seeds, few families — underpowered for any agent-config claim | run many seeds × multiple families, separating reliability from capability |

## 7. Directions discussed but NOT built (no code yet — need explicit go-ahead)

- **Ghidra headless adapter (reverse-engineering family).** The `blacktop/ghidra` Docker image is a
  viable choice: it ships `analyzeHeadless` (CLI, no GUI). Plan if pursued: run it **standalone**
  (local throwaway project, `-import`, `-readOnly`, decompile script), NOT the image's client/server
  example. We must enforce isolation ourselves (`--network none`, `--read-only` + tmpfs, `--cap-drop
  ALL`, memory/cpu limits, non-root, sample bind-mounted `:ro`) because the image does not guarantee
  it. Pin by `@sha256:` digest (untrusted image). Analyze **benign, self-built binaries only** — never
  auto-pull malware. Blocked by CR-1 (Docker down) → would land as `BLOCKED_INTEGRATION` here until the
  operator starts Docker and pulls the image.
- **Self-operating red/blue agent population** (agents self-simulate attack/defense/log-tracing).
  **PARTIALLY BUILT in Phase H** — see `docs/AGENT_POPULATION_DESIGN_VI.md` and
  `docs/PHASE_H_REPORT.md`. The operator greenlit it; the *scripted* (non-LLM) version is implemented
  with the non-negotiable preserved: blue is the scored contestant, client + attacker are environment
  generators, and every label is derived from a real server-side effect, never an agent's claim.
  Built: H1 client-noise driver, H2 `persistence` attack family, H3 attacker allowlist registry +
  Track-A detection benchmark + Track-B response benchmark (conventional vs naive discriminate; not
  ceiling-saturated). **Still future (H4):** an LLM attacker/client sequencer, and the `process` /
  `lateral` families (need container internals / a second lab host). Any LLM sequencer must keep
  ground truth independent of the agents, as the scripted version does.

## 8. Where the full reasoning lives

The raw transcript of the originating session (if ever needed verbatim) is a local Claude Code log on
the authoring machine only — it does **not** travel with git:
`~/.claude/projects/e--Saber-bench/<session-id>.jsonl`. This HANDOFF file plus `docs/` is the portable
record; prefer it.
