# SABER Cyber Range — environment inventory and readiness

Written for: the account operator and an independent reviewer deciding whether a real telemetry lab
can be stood up here. This is a **read-only** inventory taken at the start of Phase E; no networks
were enumerated, no auth was bypassed, no services were started or mutated.

## Operational live lab (Phase F) — what executes today

A **genuinely executable** minimal SOC lab now runs, with two backends sharing one control plane:

- **process-local (runs here, verified):** a real HTTP service runs as a subprocess bound to
  `127.0.0.1` only; the control plane drives real benign + inert-probe traffic at it, collects the
  service's REAL JSON access log, derives ground truth from server-side observations (independently
  of the agent and of the generation labels, cross-checked), kills the service (clean reset
  verified: process dead + port closed), and stores SHA256-hashed, timestamped evidence. Nothing is
  fabricated; all traffic is loopback with inert payloads; no external system is contacted.
- **container / CI (authorized Linux runner):** the same lab runs on a GitHub-hosted Ubuntu runner
  via the opt-in `cyber-range` workflow (manual `workflow_dispatch` only, `contents: read`, 10-min
  timeout, loopback-only, no exposed ports, no secrets), which uploads the hashed evidence as an
  artifact. No Claude credentials are used in CI.

**Reproducible deployment and execution:**

```bash
uv run saber range scenarios                     # list scenarios
uv run saber range run --scenario web_sqli_probe --seed 1 --out evidence   # one genuine episode
uv run saber range bench --no-llm --seeds 1,2,3  # exercise the T0020 contract on live telemetry
uv run saber range bench --llm --model haiku --seeds 1,2,3   # + single & multi-agent (subscription)
```

On an authorized Linux runner: Actions → `cyber-range` → Run workflow, then download the
`live-lab-evidence` artifact (access logs + receipts, all hashed).

The hardened docker-compose lab (`lab/`) remains the stronger-isolation container option and still
needs the Docker daemon (CR-1); its plan validates offline. Verified runtime logs, telemetry
samples, and the live end-to-end benchmark are reported in `docs/PHASE_F_REPORT.md`.

## Environment inventory (read-only, observed)

| Capability | Observed | Usable now? |
|---|---|---|
| OS / shell | Windows 11 (build 26200), MINGW64 + PowerShell | yes |
| Compute | 28 logical CPUs; 194 GB free on the project volume | ample |
| Python | 3.13 on PATH; project venv is 3.12.12 via `uv` 0.9.13 | yes (venv) |
| Git / Node | git (mingw), node present | yes |
| Containers | Docker Desktop **installed**; daemon **NOT running** (Linux engine pipe absent); `docker-compose` CLI present; `kubectl` present | **no — daemon down** |
| Hypervisor | VirtualBox / qemu / Vagrant | **absent** |
| WSL | not installed | **absent** |
| SIEM / IR tooling | elasticsearch, splunk, wazuh, osquery, zeek, suricata, tshark, yara, sigma CLIs | **none present** |
| Databases | psql, mysql, redis, mongo CLIs | **none present** |
| Network egress | HTTPS to github reachable (HTTP 301, ~0.4 s) | yes |
| Python security libs (venv) | `yaml` present; `scapy`, `dpkt`, `python-evtx`, `pyshark`, `pandas` absent | partial |

## Cyber Range readiness assessment

- **Compute and isolation substrate exist** (28 CPU, 194 GB, Docker Desktop installed), so a small
  reproducible Linux lab is *architecturally* feasible on this host.
- **It cannot be launched right now** without operator action, which the agent will not take:
  1. the Docker Linux daemon is stopped (starting Docker Desktop is a GUI/elevation action), and
  2. there is no fallback runtime (no WSL, no VirtualBox/qemu/Vagrant).
- There is **no existing SIEM, indexer, or database service** to reuse, and no forensic tooling
  installed, so `soc`/`vm` modes have nothing to bind to on this host today.

## What Phase E builds against this reality

- **Adapters, not fake integration.** The `soc`/`vm` capabilities get adapters with a clear
  `DEV_SIMULATION_ONLY` stub path and a real path that stays `BLOCKED_INTEGRATION` until exercised
  against authorized infrastructure. No adapter claims real integration until it runs against a
  real service.
- **Lab plan (ready to run when the daemon is up).** A docker-compose Linux lab with benign
  workloads, host/network telemetry capture, and a snapshot/reset mechanism is specified and its
  compose/config files are validated offline (plan-only), so it can be brought up by the operator
  with one command once Docker (or WSL) is available.

## External prerequisites (precise blockers)

| # | Blocker | Needed to unblock |
|---|---|---|
| CR-1 | Docker Linux daemon is stopped | operator starts Docker Desktop (or installs WSL2), then `docker info` succeeds |
| CR-2 | No SIEM/indexer service | bring up a compatible service (e.g., an OpenSearch/Elastic container in the lab) OR point an adapter at an authorized existing SIEM |
| CR-3 | No authorized lab network for `vm` stateful actions | an isolated, authorized lab with snapshots + an independent state verifier |
| CR-4 | Binary-telemetry parsing libs absent | add `python-evtx`/`dpkt` to the project venv only if binary ingestion is required (JSON interchange avoids this) |

Nothing here is purchased, provisioned externally, or security-tested outside an authorized lab.
Updated as adapters and the lab plan land in later Phase E milestones.
