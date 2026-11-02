# ADR 0004 — Separate executable SOC labs from the application world

Status: accepted for implementation; external deployment acceptance remains pending.

The previous environment profiles relocate one application world. They do not create
a SIEM, Windows domain, independent sensors or external response execution. Retain that
lightweight runtime and introduce `saber lab` with versioned presets and source bundles.

Use OpenSearch for indexed evidence and SABER's authenticated raw-evidence/case/response
gateway. Product names in earlier inventory are not mandatory replacements. Operator
VM templates are reused for Hyper-V guests, with PowerShell Direct relaying telemetry;
no WinRM exposure or guest provider keys. Scoped AD responses use a durable queue,
receipt and scheduled rollback. Containers have separate team capabilities and internal
networks. Gemini requires an explicit controller-only egress overlay and call budget.

Evidence is from real fixed subprocesses, files, HTTP/browser actions, Zeek or guest
event logs. Executor polling is explicitly narrower than full kernel instrumentation.
An indeterminate dispatch pauses its actor; idempotency receipts allow reconciliation
without repeating a possibly completed write. Archive only acknowledged evidence and
verify compressed bytes before removing hot rows. Finite storage remains an operating
constraint, not an assertion of infinite retention.

Validation separates schema/static tests, loopback integration, browser integration and
full target acceptance. Existing benchmark adapters/gates and sealed truth are not
silently reclassified as production-ready. Expanded topology is capacity scaling,
not an OpenSearch HA claim. Dedicated Ghidra/IDA/malware infrastructure is not bundled.
