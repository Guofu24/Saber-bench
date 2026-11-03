# SOC implementation and acceptance ledger

The portable, bounded SOC lab now includes the previously missing range learning,
native analysis adapters, SOAR orchestration and cold recovery tooling. The three
presets share this implementation; Windows presets add actual Hyper-V/AD guests.
Target acceptance is a separate evidence requirement, not a substitute for code.

The [latest end-to-end audit](END_TO_END_AUDIT_VI.md) records subsequent skill,
capability, Office and CI fixes with their validation. Counts below identify the
earlier completion checkpoint rather than the latest test inventory.

| Requirement | Implemented behavior | Acceptance boundary |
|---|---|---|
| Three deployment sizes | Manifest-bound source/skills/viewer/Compose/guest bundles; 13 service definitions, scaled workers | Build and boot each selected size on a sufficiently sized host |
| Client/red/blue execution | Durable jobs, real HTTP/file/browser/child processes, role capabilities and synthetic AD work | Scripted local execution tested; model quality and target isolation need separate evaluation |
| OS/network visibility | Process/file polling, Zeek capture of application namespace, optional Linux audit, Windows Sysmon/Security relay | Does not claim capture of every process or packet on the host |
| Twelve blue specialties | Role tools for monitoring, hunting, IR, content, DFIR, malware, network, intel, platform, identity, recovery and lead | Default presets instantiate six blue agents; add the other roles to the roster before render |
| Team coordination | Private team messages, evidence references, lead assignments and actor-private observations | Model-driven cooperation quality is not implied by API tests |
| Evidence and Office | Hash-checked evidence, raw/indexed field queries and pagination, case timelines/exports, actor job inspector and Chromium screenshots | Last 12 jobs/actor are a UI window; full guest desktop streaming is outside this implementation |
| Range learning | Private episodes, team-budget reflection/replay, operator suites, immutable publication, safe activation, case pinning and rollback | Local fixture proves lifecycle; Gemini quality requires a real provider run |
| Analysis | Hash-addressed vault, durable bounded jobs, builtin/Ghidra/IDA/Volatility/YARA/tshark/Suricata adapters, receipts | Native YARA positive/negative and invalid-memory rejection tested locally; licensed tools/symbols and valid samples need target verification |
| SOAR | Builtin playbooks, authenticated Shuffle/webhook adapters, exact job/case binding, independent event/state verification | Real local application effects tested; external protocol fixtures do not certify a deployed Shuffle instance |
| Restart and uncertainty | Persistent receipts/outbox, no blind replay of uncertain effects, guest/SOAR operator reconciliation | Reconciliation releases a hold; it never rewrites an unknown outcome as success |
| Storage and recovery | ACK-aware hot retention, verified raw archives, coordinated cold Docker backups, strict restore into fresh volumes, complete stopped Hyper-V exports/imports | Actual file/SQLite restore tested; Docker/OpenSearch/AD recovery and prolonged capacity tests belong on target |

## Operator entry points

- [Deployment and all three sizes](SOC_LAB_VI.md)
- [Binary, memory and PCAP analysis](SOC_ANALYSIS_VI.md)
- [Builtin and external SOAR](SOC_SOAR_VI.md)
- [Range learning, suite installation and rollback](SOC_LEARNING_VI.md)
- [Backup, migration and recovery](SOC_RECOVERY_VI.md)
- [Implementation checklist](SOC_BUILD_CHECKLIST.md)

`lab verify` requires real process/browser evidence, detected cases and defense,
continued client work, raw/indexed correspondence, Zeek, successful SOAR effects,
and the analyzer self-test evidence. Windows presets additionally require domain,
Sysmon/Security and scoped AD response receipts. Run `lab analysis self-test`
before verification; it executes benign positive and negative controls.

The manual `soc-lab-target` workflow runs only on a dedicated labelled runner.
Offline CI does not provision infrastructure or use provider credentials. Local
validation artifacts are recorded in the implementation commits and the final
handover; they must not be presented as successful Docker or Windows deployment.

## Local validation recorded on 2026-11-02

- Full pytest report: 1,430 test/check records, zero failures/errors/skips
  (`runs/soc-final-tests.xml`). Follow-up regression runs cover final analysis,
  resource sizing, recovery and Windows/Linux portability fixes.
- Ruff passes; mypy passes for both Windows and Linux over 200 source modules.
- 18 skill definitions and the frozen 175-subtask catalog pass offline checks.
- 15 Node tests and headless Chrome Office checks pass: all three teams, job
  filtering, process evidence, exact verified browser image and no page errors.
- A separate six-agent, 12-tick loopback run executed 65 scripted actions and
  verified actual SOAR enforcement, native YARA controls and browser artifacts.
  Proof: `runs/soc-final-proof-20261102-v2/proof.json`; screenshots and browser
  checks: `runs/soc-final-proof-20261102-v2/ui-final/`.
- Eleven PowerShell scripts and Sysmon XML parse successfully. No Hyper-V
  provisioning, Docker engine start, Gemini call or real key-pool read occurred.

Reproduce the bounded local proof with installed Playwright/analysis dependencies:

```powershell
python scripts/smoke_soc_loopback.py --out runs/new-proof --chrome PATH_TO_CHROME --ticks 12
```

## Explicit scope

This is a reproducible lab with bounded actions, not every commercial SOC product
or every offensive technique. Red executes synthetic application authorization/
collection and fixed Windows emulation. The analysis container performs static
analysis; it is not a malware detonation service. Ghidra/IDA installations, IDA
entitlements, memory symbols and Windows images are operator inputs. The default
SOAR works without an external product; Shuffle is an optional private integration.

Continuous operation requires capacity monitoring and retention/backup management.
Disk budgets and API quota can pause work; no finite host can promise infinite
storage or provider availability. The 175-task benchmark, sealed truth and readiness
gates remain unchanged. Lab acceptance does not promote benchmark tasks to READY.
