# SABER Cyber Range — environment inventory and readiness

Written for: the account operator and an independent reviewer deciding whether a real telemetry lab
can be stood up here. This is a **read-only** inventory taken at the start of Phase E; no networks
were enumerated, no auth was bypassed, no services were started or mutated.

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
