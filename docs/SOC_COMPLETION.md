# SOC implementation completion ledger

This ledger separates implemented behavior from target-host acceptance. A preset,
healthy process, passing fixture, or descriptive skill does not complete an operation.

| Requirement from the original request | State at `f16fd1d` | Required completion evidence |
|---|---|---|
| Three portable deployment sizes | Implemented; target acceptance pending | Render/build/start and independent acceptance per size |
| Client, red and blue agents execute tools | Basic HTTP/file/browser chain implemented | Role-specific tools and persisted outcomes, not prompt-only descriptions |
| Detailed OS/network visibility | Collectors implemented; limited capture scope | Real Sysmon/Zeek/audit events on each target |
| Threat hunting and DFIR | Incomplete: queries ignored supplied filters; no investigation timeline | Scoped field queries, verified case export and provenance |
| Twelve blue specialties | Incomplete: skills exceeded the executable tool surface | Explicit capability registry and distinct tested workflows |
| Agent-directed Windows work | Incomplete: fixed scheduled workloads; only containment queued | Durable actor jobs, scoped targets, verified receipts and restart handling |
| Team coordination | Incomplete in the new range controller | Private team communication and evidence-backed handoffs |
| Inspector evidence and screenshots | Receipt metadata only | Read-only bounded exports, visible evidence, verified artifact hashes |
| Specialist external tools | Not integrated into the new lab | Real optional tool adapters, availability reporting, no fake result when absent |
| Learning from failures | Journals retained; range learning promotion not integrated | Reproducible lesson proposals and reviewed/tested publication path |
| Continuous operations | Basic checkpoint/outbox/retention implemented | Restore/resume and storage failure recovery, including target-host checks |

The earlier implementation was a deployment foundation, not completion of this table.
Target-only verification must remain pending until actual target receipts exist. Missing
implementation must be completed in code rather than described as a hardware limitation.
