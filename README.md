# SABER — Client / Red Team / Blue Team Lab

**English** | [Tiếng Việt](README.vi.md)

SABER is a persistent multi-agent security lab: clients carry out ordinary work,
red-team agents test weaknesses in the lab, and blue-team agents investigate logs
and respond to incidents. Run scripted agents or enable Gemini planning through
team-specific provider and quota controls.

The repository also contains a separate SOC benchmark framework with a frozen
catalog of **175 subtasks across 55 NICE tasks**.

## What is available

- **Lightweight world:** real HTTP requests and durable application effects, with
  synthetic accounts and workloads. Native execution adds a fixed child process
  per action and measured process, command-line, file, DNS and TCP evidence.
- **Deployment choices:** local execution, a Docker sandbox, an operator-built VM,
  or a separate server. These profiles package the lightweight world.
- **SOC lab presets:** `linux-small`, `windows-ad` and `expanded`, with separate
  services, team workers, Chromium, a collector, OpenSearch, Zeek and Agent Office.
  Windows presets include provisioning, Sysmon collection and scoped AD responses
  with rollback.
- **Blue-team workflows:** twelve specialties, evidence-cited cases and findings,
  task assignment and handoff, private notebooks, detection-rule versions and
  recovery checks.
- **Analysis and response:** adapters for Ghidra, IDA, Volatility, YARA and PCAP
  tools; durable SOAR jobs; versioned learning with replay and rollback; backup
  and restore workflows.
- **Imported-log investigations:** preserve original files and hashes, query
  timelines/IPs/processes, checkpoint investigations and review response gaps.
- **Agent Office:** separate client/red/blue areas, per-agent activity, evidence,
  quota counters and supported browser screenshots.

**Validation status:** local HTTP, subprocess and Chromium execution have been
tested. Full Docker/Windows AD acceptance has not been completed on the development
machine; run the target acceptance checks before treating a deployment as verified.
Synthetic benchmark fixtures remain `DEV_SIMULATION_ONLY`, not `READY_BENCHMARK`.
See the [implementation status](docs/SOC_COMPLETION.md) and
[verification record](docs/END_TO_END_AUDIT_VI.md).

## Quick start

Run commands from the repository root with **Python 3.12+** and **uv**.
Docker is not required for the local world or offline tests. Node.js 18+ is required
for Agent Office.

```powershell
uv sync --locked
uv run saber --help
uv run saber world init --out runs/my-world --clients 2 --execution native
uv run saber world run --out runs/my-world --ticks 30
```

Open the viewer from another terminal, during or after the run:

```powershell
node agent-office/bin/agent-office.js watch --world runs/my-world --open
```

The committed viewer works without installing npm dependencies. Actors share the
world runtime; native mode does not create a desktop or VM for each agent, and its
sensors measure fixed workloads rather than the entire host OS.

To keep running, inspect status or request a stop:

```powershell
uv run saber world run --out runs/my-world --forever
uv run saber world status --out runs/my-world
uv run saber world stop --out runs/my-world
```

Use `--resume` after a STOP request. Edit the roster before the first run; an
existing world rejects a different configuration. Use a new output directory
for a different roster. `world supervise` can restart a failed process within a
bounded restart policy.

When reusing an environment with optional dependencies, use `uv run --no-sync ...`.
On Windows, the installed CLI is also available through
`.\.venv\Scripts\python.exe -m saber.cli.main`.

## Choose a deployment

The lightweight `saber world` / `saber env` runtime and the multi-service
`saber lab` deployment are separate options. Selecting `env --profile vm` does not
provision a SOC stack or an AD domain.

| Lightweight profile | Execution location | Requirements |
|---|---|---|
| `local` | Python process on the current machine | Python 3.12+ and uv |
| `sandbox` | One Linux container containing the world | Docker Linux engine and Compose |
| `vm` | Exported bundle inside a VM you build | Guest with Python 3.12+ and uv |
| `remote` | Exported bundle on a separate lab/server | Server with Python 3.12+ and uv |

VMs can be managed with Hyper-V, VMware, KVM or Proxmox. The `env` profiles do not
create VMs, connect over SSH or manage hypervisor snapshots. Their service
inventory and HTTP health checks do not automatically connect external SIEM/SOAR
telemetry or response actions.

### Docker sandbox

```powershell
uv run saber env init --profile sandbox --name sandbox-demo --clients 4 --out runs/env-sandbox.json
uv run saber env doctor --config runs/env-sandbox.json
uv run saber env render --config runs/env-sandbox.json --out runs/bundle-sandbox
uv run saber env up --bundle runs/bundle-sandbox
uv run saber env status --bundle runs/bundle-sandbox
uv run saber env report --bundle runs/bundle-sandbox --out runs/sandbox-report-1.json
uv run saber env down --bundle runs/bundle-sandbox
```

`init` writes the configuration; `render` exports the bundle; `up` builds and starts
the container. Use new output paths. `doctor` does not start Docker Desktop.

By default the container runs as a non-root user, has no external network or
published ports, and has RAM/CPU/PID limits. Data lives in a named volume;
`down` retains it. Resume with:

```powershell
uv run saber env up --bundle runs/bundle-sandbox --resume
```

The default 2 GiB sandbox limit covers the application runtime, not a Windows
desktop, SIEM, SOAR stack or malware-analysis environment.

### Operator-built VM or separate server

Build the VM using your hypervisor, then export a bundle:

```powershell
uv run saber env init --profile vm --name vm-demo --clients 8 --out runs/env-vm.json
uv run saber env render --config runs/env-vm.json --out runs/bundle-vm
```

Copy the bundle to the guest. Run the following **inside the guest**, from
`bundle-vm/source`:

```powershell
uv sync --frozen --no-dev
uv run --no-sync saber env run --config ../environment.json --out ../world --ticks 30 --on-target
uv run --no-sync saber env run --config ../environment.json --out ../world --forever --on-target
```

For a separate server, initialize with `--profile remote` and follow the same
export-and-run workflow. `--on-target` confirms where the command is being run;
it does not access another machine. You manage guest resources, networking and
snapshots. The control plane does not need to be exposed to the Internet/LAN.

### Local deployment profile

Use `env` when you want an explicit local deployment configuration:

```powershell
uv run saber env init --profile local --clients 4 --out runs/env-local.json
uv run saber env run --config runs/env-local.json --out runs/world-local --ticks 30
uv run saber env run --config runs/env-local.json --out runs/world-local --forever
```

See the [environment guide](docs/ENVIRONMENTS_VI.md) and
[example configurations](config/environments/).

## Multi-service SOC lab

These presets provide deployment code for a larger target machine:

| Preset | Initial target resource budget | Clients / red / blue | Windows guests |
|---|---|---|---|
| `linux-small` | 32 GB RAM, 6 CPUs, 250 GB free disk | 2 / 3 / 6 | None |
| `windows-ad` | 64 GB RAM, 8 CPUs, 500 GB free disk | 4 / 3 / 6 | 1 DC, 2 workstations, 1 file server |
| `expanded` | 128 GB RAM, 16 CPUs, 1 TB free disk | 12 / 3 / 6 | 1 DC, 6 workstations, 1 file server |

These are planning allocations, not measured capacity guarantees. Logical agents
share their team's workers; an agent is not a separate machine. `expanded`
increases worker/guest capacity rather than providing an HA SIEM cluster.

Prepare and validate a bundle without starting the lab:

```powershell
uv run saber lab list
uv run saber lab init --preset linux-small --name soc-small --out runs/soc-small.json
uv run saber lab render --config runs/soc-small.json --out runs/soc-small-bundle
uv run saber lab validate --bundle runs/soc-small-bundle
```

Edit the actor roster, workers, timing, storage and VM settings before rendering.
The bundle has 13 service definitions. Optional Ghidra/IDA installations and
symbols belong in `tools/`; IDA requires an appropriately licensed headless
installation. SOAR defaults to its built-in backend; the Shuffle adapter targets
an operator-managed lab instance.

| Task | Guide |
|---|---|
| Provision, start and verify the target; configure agents and Office | [SOC deployment](docs/SOC_LAB_VI.md) |
| Analyze binaries, memory images and PCAPs | [Analysis](docs/SOC_ANALYSIS_VI.md) |
| Run playbooks or connect Shuffle/webhooks | [SOAR](docs/SOC_SOAR_VI.md) |
| Replay, publish or roll back skill lessons | [Learning](docs/SOC_LEARNING_VI.md) |
| Back up, move and restore the lab | [Recovery](docs/SOC_RECOVERY_VI.md) |

These detailed operating guides are currently in Vietnamese.

## Blue-team specialties and skills

The default world has six blue roles. Create a new world with all twelve:

```powershell
uv run saber world init --out runs/soc-specialists --clients 4 --blue-specialists
uv run saber world run --out runs/soc-specialists --ticks 30
```

| Area | Specialties |
|---|---|
| Coordination and detection | Lead, monitoring, threat hunting |
| Investigation | DFIR, malware/reverse engineering, network, threat intelligence, identity |
| Response and operations | Incident response, detection engineering, SOC platform, recovery |

Configure multiple actors with the same role, or add `specialties` to an actor.
Tools include paginated log queries, evidence-cited cases/findings, task acceptance
and handoff, hashed artifacts, rule testing/versioning/rollback and client recovery
checks. `wait` and `finish` stop the actor's actions as specified by the runtime;
Office displays those states.

The repository has **18 skill definitions, 15 operational playbooks and 56 reference
documents**. World/range planners load core guidance and the execution contract,
then use `consult_skill` for specialist references. Case workflows load their
declared references. DFIR includes thirteen reference topics, twelve incident
playbooks and twelve artifact groups.

Skills describe how to use available capabilities; mentioning a product does not
make it an executable tool. Structural checks do not establish model reasoning
quality. See [skill usage](docs/SKILLS_VI.md),
[coverage and sources](docs/ALL_SKILLS_COVERAGE_VI.md),
[DFIR coverage](docs/DFIR_CAPABILITY_COVERAGE_VI.md), the
[handbook review](docs/DFIR_HANDBOOK_REVIEW_VI.md),
[skill review](docs/SKILLS_REVIEW_VI.md) and
[specialist tool contracts](docs/SOC_SPECIALISTS_VI.md).

## Enable Gemini

All profiles default to scripted execution with no model API calls. The current
configured default model is `gemini-3.5-flash-lite`; use `--model` to select another
supported model. The program loads the key pool from a file excluded from Git and
deployment bundles.

| Team | Key positions in the file |
|---|---|
| Clients | 1–200 |
| Red | 201–400 |
| Blue | 401 onward |

Rotation stays within the team's pool. Cursors, usage and cooldowns survive
restarts. API failures or an exhausted call budget can lead to scripted fallback;
this is a hybrid runtime. Inspect `llm.successes`, per-team usage, pool state and
the action source (`llm`, `scripted`, `scripted-fallback`).

For a local world:

```powershell
uv run saber world run --out runs/my-world --llm --key-pool keys_pool.txt --call-budget 200 --ticks 60
```

For local/VM/server profiles, add `--llm --key-pool PATH --call-budget 200` to
`env run`. For a sandbox:

```powershell
uv run saber env up --bundle runs/bundle-sandbox --llm --key-pool keys_pool.txt --call-budget 200 --resume
```

The Gemini sandbox manifest enables outbound connectivity for the controller and
mounts the key file read-only. Egress is not restricted by domain. The call budget
is cumulative across the world's lifetime, including retries and restarts; it is
not a per-key allowance and does not change the provider's billing tier.

The [learning pipeline](docs/AGENT_LEARNING_VI.md) records outcomes, proposes
lessons, evaluates replays and publishes gated local skill versions. It shares
the team's provider budget. Reflection needs a model; evaluation/publication
needs an operator-provided suite. An existing case keeps its pinned skill version.
This is not proof of autonomous improvement in end-to-end SOC performance.
See the [world/Gemini guide](docs/CONTINUOUS_WORLD_VI.md) and
[development replay example](config/learning/client-session.json).

## Inspect activity in Agent Office

Click an agent, desk, monitor or roster card to inspect executed actions, targets,
HTTP results and linked case responses. The viewer separates clients, red and
blue into their own areas, with 12 or 24 seats per team and roster pagination up
to 200 agents. Adding seats does not create agents.

World snapshots show bounded event windows. Supported SOC jobs also expose
verified evidence and Chromium screenshots. Successful HTTP responses alone do
not prove compromise or effective defense.

```powershell
node agent-office/bin/agent-office.js watch --world runs/my-world --open
node agent-office/bin/agent-office.js watch --bundle runs/bundle-sandbox --open
```

Use your actual output/bundle path. On a VM/server, run the viewer on the target
and forward its loopback port. See [Agent Office](agent-office/README.md) and the
[native telemetry guide](docs/NATIVE_TELEMETRY_VI.md).

### Imported-log investigations

Blue agents can investigate EDR CSV, Apache/IIS access logs and generic text logs.
The vault preserves original bytes and hashes; queries return bounded previews
and evidence IDs. Investigations persist across restart. Response review identifies
documentation/coverage gaps; `REVIEWED` does not mean mitigation was independently
verified and does not close a live case.

Run a small demo without Docker or provider keys, using a new output directory:

```powershell
uv run --no-sync python scripts/smoke_forensics.py --out runs/forensics-demo
node agent-office/bin/agent-office.js watch --world runs/forensics-demo --open
```

Select **Blue Team → blue-dfir → forensic_query / response_review**.
See the [import, query, export and Gemini workflow](docs/FORENSICS_VI.md).

## Runtime data

The world data directory is the `--out` path; the sandbox uses `/data` in its named
volume. Agents receive filtered observations, not the database or sealed ground truth.

| File/directory | Contents |
|---|---|
| `config.json` | Configuration fixed for this world |
| `report.json` | Tick, results, usage and pool state |
| `office.json` | Public viewer snapshot: roster, activity, counters and quota indices |
| `learning.json` | Learning status, version IDs and epoch; no notebook/lesson bodies |
| `access.jsonl` | Rotating application activity log |
| `world.sqlite3` | State, cases, journals and evaluator ledger |
| `forensics/` | Imported originals, index and investigation checkpoints |
| `STOP` | Stop request; explicit resume is required |

## Validation and rollback

```powershell
uv run pytest --junitxml=runs/quality-tests.xml
uv run python scripts/check_skills.py --out runs/skills-check/audit.json
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy --platform linux
uv run mypy --platform win32
uv run python scripts/validate_catalog.py
npm --prefix agent-office test
git log --oneline --decorate -15
```

Offline tests do not use real provider keys. Live Gemini checks are an explicit
opt-in through `scripts/smoke_world_gemini.py`. Office CI runs on Linux and Windows
and rebuilds the viewer to detect stale committed output. When editing the viewer,
install its locked build dependencies with `npm --prefix agent-office ci`, then
run `npm --prefix agent-office run build:viewer`.

Changes are committed by feature. [Rollback instructions](docs/ROLLBACK_VI.md)
cover checkpoints, `git revert` and worktrees. A code revert does not restore runtime
data: stop the runtime and back up the data/volume before changing versions.
`env down` preserves its volume; VM snapshots belong to the hypervisor.

## Documentation and other workflows

- [Vietnamese README](README.vi.md) and [command notes](notes.md).
- [Environment guide](docs/ENVIRONMENTS_VI.md) and
  [environment design decision](docs/adr/0003-environment-profiles.md).
- [Benchmark readiness](docs/READINESS.md): data, scorers and integrations.
  `saber task`, `smoke` and `experiment` are separate from deployment profiles.
- [Development supervisor](docs/DEVELOPMENT_SUPERVISOR.md): `run.sh` coordinates
  development through Claude Code; it does not start the client/red/blue world.
- [Environment-first policy](docs/ENVIRONMENT_FIRST.md): reuse compatible infrastructure.
- [Security boundaries](docs/SECURITY.md): lab scope and execution permissions.

## License

SABER retains its existing **proprietary** licensing status. See [LICENSE](LICENSE)
for the notice and licensing contact. This repository is not offered under an
open-source license as a whole.

The separately licensed [agent-office component](agent-office/LICENSE) retains
its MIT license, as declared in its package metadata. Third-party dependencies,
datasets, detection rules and external tools retain their own terms; see the
[dataset provenance report](docs/EVAL_DATA_PROVENANCE.md) where applicable.
