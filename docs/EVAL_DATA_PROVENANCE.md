# SABER independent-label provenance report (Phase E1)

Written for: an independent reviewer judging whether SABER's labels can support a credible,
independently testable benchmark. It records where every label comes from, how trustworthy it is,
and what is still missing. Nothing here is `READY_BENCHMARK`.

## Four label tiers

Every evaluation label is tagged with one of (`saber.evaldata.LabelTier`):

| Tier | Meaning | Benchmark weight |
|---|---|---|
| `SOURCE_PROVIDED` | the dataset authors' own label/semantics (e.g. a Sigma rule's detection logic) | evidence, not gold for our subtasks |
| `INDEPENDENTLY_VERIFIED` | re-derived by a route distinct from the source and agreeing | strong, still not human-signed |
| `SYNTHETIC` | labels we constructed (the gold pilots) | design artifact, cross-checked, not external truth |
| `EXPERT_ADJUDICATION_REQUIRED` | needs a human SOC/IR lead | pending |

## Current label inventory

| Source | Tier | Count | Notes |
|---|---|---|---|
| Gold Evaluation Pilot v1 | `SYNTHETIC` | 12 subtasks | two-route automated cross-check; not human-signed (`docs/PHASE_D_REPORT.md`) |
| SigmaHQ detection rules | `SOURCE_PROVIDED` | 4 ingested (pilot of the importer) | genuine external rules; DRL-1.1; see evidence below |
| Externally validated gold | `INDEPENDENTLY_VERIFIED` | **0** | no external corpus re-verified against expert truth yet |
| Queued conventions | `EXPERT_ADJUDICATION_REQUIRED` | 6 | `gold/ADJUDICATION_QUEUE.md` |

**Independently validated gold labels remain 0.** External detection rules carry the *rules'* own
semantics (`SOURCE_PROVIDED`); they are not gold labels for SABER's subtasks, so they do not
promote anything toward `READY_BENCHMARK`.

## Real-data ingestion evidence

The importer (`saber.evaldata.import_dataset`) was exercised on **genuine** external content with
verifiable provenance, not synthetic stand-ins:

- **Source:** SigmaHQ/sigma, `rules/windows/process_creation`, pinned commit
  `4d47b8ff8a8b4f85ea099a79313158badea1feed`.
- **License:** Detection Rule License (DRL) 1.1 — use and redistribution permitted (verified from
  the repo's `LICENSE` at that commit).
- **Result:** 4 rules ingested and validated; real ATT&CK techniques extracted (`T1218`,
  `T1560.001`); per-file SHA256 recorded. Full manifest: `gold/evaldata/sigmahq_ingestion.json`
  (reproducible — re-fetch at the pinned commit and the SHA256s must match).
- The raw files live under `data/external/` (gitignored as untrusted downloads); only the
  reproducible provenance manifest is committed.

Importers and validators also exist for **event logs** (Windows/Sysmon JSON or JSON-lines),
**network captures** (Zeek `conn.log` TSV / JSON flows; raw pcap reports the missing dpkt/scapy
dependency rather than silently skipping), and **host artifacts** (autoruns/registry CSV/JSON),
each tested on realistic fixtures (`tests/evaldata/`).

## Scenario-lineage contamination control

`saber.evaldata.lineage_key` fingerprints a scenario by its underlying attack — the sorted set of
ATT&CK techniques, the sorted IOC set, and a hash of any detection logic — **excluding identifier
fields** (task/subtask/NICE/rule IDs). So the same attack appearing under two different task IDs
maps to the same lineage key, and `assert_no_lineage_crosses_split` refuses to let one lineage land
in more than one of train/dev/test. This augments the existing family-based split; it does not
replace it.

## Candidate public sources (reviewed, not auto-downloaded)

`saber.evaldata.CANDIDATE_SOURCES` documents reusable public datasets with license and feasibility:

| Source | Kind | License | Feasible here |
|---|---|---|---|
| SigmaHQ/sigma | detection_test | DRL-1.1 | yes (ingested) |
| redcanaryco/atomic-red-team | detection_test | MIT | yes (small YAML) |
| OTRF/Security-Datasets | event_log | GPL-3.0 (data) | gated: sizeable download + operator license confirmation |
| CIC-IDS-2017 (UNB) | network_capture | UNB academic terms | gated: registration + license acceptance |
| malware-traffic-analysis.net | network_capture | per-post terms | gated: operator reviews each post |

## Remaining external prerequisites (precise blockers)

| # | Blocker | Needed to unblock |
|---|---|---|
| ED-1 | No independently validated gold labels | a labeled real corpus plus an independent re-derivation route, or expert adjudication of the 6 queued conventions |
| ED-2 | Large labeled real logs/pcaps not present | operator accepts each dataset's license and downloads it (OTRF, CIC-IDS); then re-run the importers |
| ED-3 | Raw pcap parsing | add `dpkt`/`scapy` to the project venv only if binary pcap ingestion is needed (JSON/Zeek interchange avoids it) |

No subtask is promoted. The pilot importer proves genuine data *can* be ingested with provenance and
kept uncontaminated; it does not manufacture gold.
