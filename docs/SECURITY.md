# SABER safety and security policy

The intended use is **authorized defensive security research in a purpose-built isolated lab**. This plan does not authorize scanning, intrusion, credential collection, data exfiltration or containment of any external system.

## Environment control

1. Distinguish `dev` (fixtures; no host actions) and `lab` (real machines) using explicit config with fail-closed defaults.
2. Place vulnerable/emulation machines on a dedicated deny-by-default Proxmox bridge/VLAN. No layer-3 routes to production/user networks. Host firewall rules must be tested; a config file alone is not proof of isolation.
3. Approved dependency downloads, if needed, occur during an operator-supervised provisioning window through a controlled proxy/mirror. Default test execution has no Internet egress.
4. Workloads use synthetic accounts, fake business data and throwaway credentials. No real enterprise/customer files or personal data.
5. Each episode starts from a known clean snapshot; track image hash and ensure prior artifacts/processes have been reset.
6. Explicit per-episode operator approval is required before initiating live attack emulation. Restrict target host list, time window and selected **pre-reviewed** scenario profile.
7. No user- or model-controlled raw command execution against range machines. Emulation drivers accept only allowlisted IDs and validated parameters, not arbitrary scripts or shell snippets.
8. Use test-only ATT&CK-aligned emulation and benign lookalikes; avoid malware payloads, live credential theft, stealth/persistence development and destructive actions.

## Separation of duties

| Role/service | May access | Must not access |
|---|---|---|
| `blue-agent` | As-of telemetry via gateway, cases, evidence, rule proposals | Ground truth, snapshots, emulation, direct host shell, IR approvals |
| `control-plane` | Snapshot, workload scheduling, approved emulator | Live grading answer leak into Blue prompts |
| `evaluator` | Sealed truth, agent output, tool audit | Unapproved emulation and containment |
| `operator` | Approve named lab targets/actions, review reporting | Must not bypass range segmentation checks |
| `response-adapter` | Strictly allowlisted, TTL-bound action on lab assets | Arbitrary OS command; unauthenticated execution |

Use distinct DB/database-role credentials and distinct object-storage buckets/policies for evaluator-only truth and agent-visible evidence. Separation must be tested by actual access denial, not merely relying on code convention.

## Incident-response safeguards

- Default is `dry_run`. IR proposes a structured action; policy evaluates target ownership, action kind, incident evidence, TTL and allowed impact.
- Operator approval attaches to the **exact** action ID, target, scope, environment, duration and run. Reusing approval for different parameters is rejected.
- Execution requires a separate executor token not held by any LLM provider or agent.
- Every executed action has postcondition verification and compensating rollback; automatically expire short-lived lab containment.
- Block dangerous mass actions and prohibit targets outside explicit `lab_asset_registry`.
- A denial, timeout or unknown result must be recorded; never treat attempted execution as success.

## Prompt injection and input integrity

- Logs, web requests, email text, command-line parameters and filenames collected from the range are **untrusted data**. They can contain instructions aimed at the defender LLM.
- Delimit tool outputs as evidence; system policies, tools and permissions come from trusted app code only.
- Tool schemas validate field/operator lists and reject attempted SQL, OpenSearch DSL, file paths, prompt-like tool commands and future time windows.
- Findings are accepted as claims but independently verified against indexed evidence IDs.
- Maintain fixtures that include deceptive messages in log fields: attempts to override instructions, invoke unauthorized tools, discover private labels and contaminate agent output.

## Credentials and audit

- Never hardcode `.env`, API keys, Proxmox tokens, provider keys or actual domain credentials; `.env.example` contains placeholders only.
- Least privilege to telemetry query, control plane, storage and worker queues. Require operator auth on sensitive endpoints.
- Structured audit logs with request IDs, action hashes, policy decisions, target inventory references, approvals, timestamps and outcome; redact secrets and sensitive payloads.
- Dependabot/lockfile vulnerability scanning and pinned deployment image versions in CI/release process.

## Human approval gates (must be explicitly confirmed)

- H1: Proxmox credentials and real infrastructure write (`plan` is not `apply`).
- H2: Network isolation verified on actual lab including route and firewall checks.
- H3: Approval of each emulation profile and concrete target/period.
- H4: Any real containment, even in lab; require rollback ready.
- H5: Publishing dataset or telemetry outside repository; inspect for real secrets and hidden answers.

## Non-permitted shortcuts

Do not use Claude Code permission bypass flags to overcome guardrails. Do not disable audits because they are noisy. Do not connect the range to a corporate VPN to install packages. Do not mark `SABER_ENV=lab` merely to make a smoke test pass. Do not silently convert a failed scenario to benign or to a detected attack.

## Security test suite requirements

- Agent → private ground truth request is rejected.
- Agent → future event query is rejected.
- Agent → direct arbitrary command is impossible at API/schema level.
- IR → nonlab host or unknown asset is rejected.
- Approval for action A cannot execute altered action B.
- Response on Track A is rejected even with a nominal approval.
- Prompt-injection event text cannot create a new tool or change permission policy.
- Secret fixture in log is redacted from operational logs and exported reports.
- Range isolation check failing prevents emulation transition.
