# SOC implementation completion ledger

This ledger separates implemented behavior from target-host acceptance. A preset,
healthy process, passing fixture, or descriptive skill does not complete an operation.

| Requirement from the original request | Current implementation | Required completion evidence |
|---|---|---|
| Three portable deployment sizes | Implemented; target acceptance pending | Render/build/start and independent acceptance per size |
| Client, red and blue agents execute tools | Basic HTTP/file/browser chain implemented | Role-specific tools and persisted outcomes, not prompt-only descriptions |
| Detailed OS/network visibility | Collectors implemented; limited capture scope | Real Sysmon/Zeek/audit events on each target |
| Threat hunting and DFIR | Field/time queries, raw/indexed pagination, canonical hash checks, case export and timelines implemented | Local query/export tests pass; actual OpenSearch acceptance pending |
| Twelve blue specialties | Shared capability registry and distinct bounded workflows implemented; malware role currently examines telemetry only | Specialized binary/memory analysis remains unimplemented in range |
| Agent-directed Windows work | Durable actor queue, fixed guest tools, node/role checks, measured receipt validation, uncertainty pause and operator reconciliation implemented | Queue/restart/auth tests pass; actual guest dispatch acceptance pending |
| Team coordination | Private team messages, evidence references and lead case assignment implemented | Local isolation/handoff tests pass; model-driven collaboration quality not established |
| Inspector evidence and screenshots | Per-actor 12-job exports, process/app evidence, redacted results and SHA-256 checked browser images implemented | Local real-executor/Chrome tests; no full guest desktop streaming |
| Specialist external tools | Not integrated into the new lab | Real optional tool adapters, availability reporting, no fake result when absent |
| Learning from failures | Journals retained; range learning promotion not integrated | Reproducible lesson proposals and reviewed/tested publication path |
| Continuous operations | Checkpoint/outbox/retention, integrity-checked archived evidence lookup, bounded viewer refresh and uncertain-job pause implemented | Full storage-loss restore, long-duration capacity testing and target-host recovery acceptance remain pending |

The earlier `f16fd1d` implementation was a deployment foundation, not completion of this table.
Target-only verification must remain pending until actual target receipts exist. Missing
implementation must be completed in code rather than described as a hardware limitation.

## Changes after the review

- `387e2e8`: scoped hunts/DFIR, role capabilities, private handoffs and Windows work queues.
- `c20094c`: Office evidence/screenshots, pagination fixes, stronger guest receipts and reconciliation.
- Archived evidence remains addressable after hot-store retention; conflicting re-ingestion is rejected.

The range controller does **not** yet implement the existing world learning publication
pipeline, a Ghidra/IDA/memory-forensics adapter, or external SOAR playbooks. These are code
gaps, not merely tests waiting for a larger computer. The presets implement a bounded lab,
not every operation of a production SOC. Passing `lab verify` does not remove these gaps.

## Local validation on 2026-11-02

- Full pytest JUnit report: 1,413 test/check records, zero failures, errors or skips
  (`runs/soc-completion-tests.xml`), with the existing Chrome executable enabled.
- 15 Node protocol/view tests; Ruff and mypy over 190 Python source modules.
- Nine Windows PowerShell scripts parsed; no VM provisioning was performed here.
- A separate 12-tick loopback run used six agents, actual child processes and Chromium.
  Headless Office checks opened client/red/blue evidence, checked job filtering and
  rendered the exact hash-verified client image (`runs/soc-office-proof-20261102/ui/`).
- These checks used scripted agents. No Gemini calls or real key-pool reads were made
  in this review, and no Docker/AD/Zeek/Sysmon runtime acceptance is claimed.
