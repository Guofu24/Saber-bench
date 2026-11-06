# External practice: blue-team investigation and SOC assessment

Use when the operator assigns an external investigation or SOC exercise, including
HTB Sherlocks-inspired practice. These are SABER-authored methods, not official
answers. The runtime menu remains authoritative. A historical artifact does not
grant access to its original host or authority to contain a live system.

## Establish evidence and task boundaries

Identify the question, scenario revision, source package, asset/tenant scope,
time window, available telemetry and what a completed answer must demonstrate.
Keep answer keys, walkthroughs and evaluator notes outside the agent-visible
vault. Separate learning runs from held-out assessments: record assistance and
prior exposure; changing a filename does not make the same incident unseen.

Preserve original bytes and hashes; document each conversion's input hash,
tool/version/options, output hash, timezone interpretation and lost fields.
SABER's forensic vault currently indexes UTF-8 CSV, Apache, IIS and text. EVTX,
PCAP and memory artifacts need appropriate conversion or a separately available
analysis adapter. Parsing failure, partial indexing and unknown timestamps must
survive into the report. A successful import does not mean complete coverage.
Do not execute extracted samples to discover their format. Sherlocks can include
malware; sample execution belongs only in the separately provisioned analysis lab.

## Assign the work by role

| Role | Deliverable | Evidence needed before accepting it |
|---|---|---|
| MON | Prioritized alert decision and next owner | Source event, asset importance, benign alternative, coverage and reason for escalation/closure |
| HUNT | Testable hypothesis and scoped results | Reproducible query, time/asset bounds, result pagination and evidence against the hypothesis |
| DFIR | Timeline and incident scope | Original/derived lineage, scoped entity joins, clock uncertainty and record-level citations |
| IR | Response proposal and effect assessment | Exact target, authorized action, impact/rollback and independent postcondition observation |
| CNT | Detection change and validation | Positive and benign controls, expected telemetry, missed/false detections and version/rollback |
| Malware | Sample behavior assessment | Sample hash, tool/version, static/dynamic findings and sandbox limitations; a string is not execution |
| Network | Protocol/session reconstruction | Sensor placement, endpoints, flow/packet references, capture gaps and encryption limitations |
| Intel | Relevant, qualified enrichment | Source age, context, confidence, sightings and observable matching; reputation is not incident proof |
| Identity | Account/session/token scope | Tenant/domain and principal IDs, audit coverage, effective permissions and revocation verification |
| Platform | Telemetry readiness | Collection/ingest lag, schema, dropped events, parser health and source retention |
| Recovery | Return-to-service evidence | Service/data checks, client workflow results, restored controls and remaining risk/owner |
| Lead | Coordinated case and defensible closure | Accepted handoffs, disagreement resolution, uncompleted work and evidence supporting each conclusion |

## Investigation loop

1. Inspect the source inventory and quality before selecting tools. Establish a
   benign baseline and record what the supplied package cannot answer.
2. Ask one discriminating question at a time. Pivot using host/account/session/
   process identity with timestamps; avoid joining unrelated hosts by PID or IP.
3. Record observation separately from interpretation. For each assertion, cite
   the exact record and explain its relevance, alternatives and uncertainty.
4. Reconstruct only supported causal links. DNS is not connection, connection is
   not execution, archive creation is not exfiltration. Use unknown where needed.
5. Hand off a reproducible query, evidence IDs and unresolved question. A second
   copy of the same event is not independent corroboration.
6. Close the assigned question with findings and limits; request missing sources
   for unresolved claims. Solving retrospective questions does not verify live
   containment, eradication or recovery.

In world/range, use forensic_sources, forensic_open, forensic_query and
forensic_record when actually offered. Existing sessions retain the query trail.
response_review assesses documentation gaps, not the truth of conclusions;
forensic_finish reviewed is not a verified-remediation result. Never create
fictional containment evidence to satisfy a response checklist for an offline lab.

## SOC workflow and balanced evaluation

For a SOC shift, retain alert arrival, assignment, first evidence-backed decision,
escalation, response request, applied response and verified recovery timestamps
separately. Report queue coverage and the denominator behind any rate. A missing
alert is measurable only with independent incident truth and source coverage.
Include benign lookalikes and incomplete-evidence cases; reward justified
abstention rather than forcing every task into a malicious/benign answer.

An evaluator checks correctness, citation relevance, scope, uncertainty and
handoff quality against independently controlled evidence. A valid hash or a
populated checklist establishes integrity/completeness only. Human review is an
attributed judgment, not cryptographically authenticated ground truth. Keep
training review results separate from the frozen 175-subtask benchmark.

During a joint exercise, blue sees telemetry collected through its own tools;
the lead does not import red plans or private answers. After the run, the operator
can compare expected effects, measured effects, available telemetry and response.
Missing sensors, missing tools and reasoning errors lead to different fixes.
Publish a general lesson only after the existing review and fresh replay gates.

## Sources and limits

Reviewed 2026-11-05; do not infer subscription rights or direct API integration.

- [Sherlocks](https://help.hackthebox.com/en/articles/8570249-how-to-play-sherlocks): investigative categories, packages and sample-handling requirements.
- [Enterprise SOC Range](https://enterprise-help.hackthebox.com/en/articles/15654060-soc-range): alert backlog, investigations and tools/endpoints; access requires a licensed seat.
- [Enterprise API](https://enterprise-help.hackthebox.com/en/articles/13375637-introduction-to-enterprise-public-api): metadata/framework integration does not establish access to raw endpoint telemetry or containment APIs.
