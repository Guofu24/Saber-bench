# HTB-informed practice in SABER

SABER includes nine original competency tracks informed by Hack The Box's public
product documentation, optional red/blue skill guides, a local evidence importer
and an operator review report. It does **not** include HTB course text, challenge
answers, downloadable lab images, an HTB subscription or a live HTB executor.

The commands below are implemented and work offline. An exercise URL is recorded
as provenance; it is never fetched, scanned or used as an execution target.
These exercises are separate from the frozen 175-subtask SOC benchmark.

## Choose a track

```powershell
uv run --no-sync saber training catalog
uv run --no-sync saber training catalog --team blue
```

| Track | Intended practice | Roles |
|---|---|---|
| `red-web` | Web/API authorization, observed effects and access handoff | recon, access |
| `red-enterprise` | Windows/Linux identity, enterprise paths and closeout | recon, access, impact |
| `red-agent-evaluation` | Comparable attempts, tool/model failures and fresh replays | recon, access, impact |
| `blue-dfir` | Evidence lineage, timeline, incident scope and uncertainty | dfir, network, identity |
| `blue-soc` | Triage, escalation, response decisions and recovery | monitor, lead, ir, recovery, platform |
| `blue-hunt-detection` | Hypotheses, positive/benign controls and coverage | hunter, content, intel, platform |
| `blue-malware` | Sample/network analysis and affected-host evidence | malware, network, dfir |
| `blue-identity-cloud` | Identity/session scope, cloud activity and revocation | identity, dfir, hunter, ir |
| `purple-validation` | Post-run comparison of red effects, telemetry and blue decisions | operator-led debrief |

These are SABER track IDs, not HTB challenge IDs. Each track has six review
criteria: scope, provenance, uncertainty and three role-specific deliverables.
Record the actual exercise URL/slug and assistance separately. Reusing the same
incident with renamed files does not produce an unseen evaluation sample.

## Run a complete local demo

No Docker, HTB account, API key or LLM is needed:

```powershell
uv run --no-sync python scripts/smoke_training.py --out runs/training-demo
node agent-office/bin/agent-office.js watch --world runs/training-demo/world --open
```

Use a new output directory for each run. In Office, open **Blue Team → blue-dfir**
and select `consult_skill`, `forensic_query` or `response_review` in its activity.
The demo uses scripted decisions through real local HTTP tools. It preserves two
synthetic HTTP records, selects the new skill guide and deliberately finishes
`PARTIAL`: a successful web request does not establish compromise or recovery.

`proof.json` describes the check, `report.json` contains the review result, and
`world/office.json` contains the activity snapshot. The demo's review is explicitly
scripted test data. It measures integration, not model judgment or HTB performance.

## Prepare a real investigation from evidence you may use

Download permitted evidence through the appropriate HTB account yourself. Keep
raw packages, samples and answer keys outside the repository. Read the exercise's
handling instructions: Sherlocks packages can contain malware. This integration
does not extract archives or execute samples.

```powershell
uv run --no-sync saber training init --track blue-dfir --exercise my-investigation --out runs/my-investigation
uv run --no-sync saber training attach --run runs/my-investigation --file .\data\external\investigation\events.csv --format csv --label "Investigation event export" --rights-note "Authorized private practice under my content access" --conversion-note "Original UTF-8 CSV bytes; no conversion"
uv run --no-sync saber training prepare-world --run runs/my-investigation
uv run --no-sync saber world forensics sources --out runs/my-investigation/world
```

Use `init --source-url PUBLIC_HTB_CONTENT_URL` to identify the actual exercise;
otherwise the manifest references the track's official overview page. URLs must
be HTTPS on `hackthebox.com` or a subdomain, without credentials/query/fragment.
Use `--synthetic` for locally authored fixtures and `--assisted` when answers or
walkthroughs were consulted. A rights note records your basis for use; it does
not grant rights or prove that a provider's terms permit a particular use.

`prepare-world` creates only the blue roles appropriate to the selected track,
with investigation goals, in the local application runtime. It does not start
agents. Automatic learning is disabled in this practice config to help keep
exercise-specific answers out of the skill release process. Existing configs or
world databases are not overwritten. Red and purple tracks deliberately have no
automatic practice-world preparation; use their rubric with separately approved
local lab execution or operator-supplied external execution evidence.

For model planning, use the existing Gemini configuration and team budget:

```powershell
uv run --no-sync saber world run --out runs/my-investigation/world --ticks 30 --llm --key-pool .\keys_pool.txt --call-budget 60
node agent-office/bin/agent-office.js watch --world runs/my-investigation/world --open
```

This command calls Gemini and may send bounded, masked evidence excerpts to the
configured provider. Use evidence permitted for that processing. The ordinary
scripted fallback does not perform an arbitrary external investigation; the
demo above has its own explicit scripted investigation. Provider failures and
quota exhaustion retain the runtime's existing fallback/source labels.

### Supported evidence and conversion

The importer reuses `saber.forensics.Vault`: UTF-8 CSV, Apache, IIS and text;
128 MiB per source, at most 100 sources, and the existing bounded vault/index.
It copies original input bytes, records SHA-256 and exposes source IDs to blue
through the existing forensic tools. It never deletes the supplied file.

EVTX, PCAP, memory dumps, UTF-16 exports and archives are not directly parsed by
this importer. Use an appropriate converter or separately provisioned analysis
adapter. Retain the original binary externally and record input/output hashes,
converter/version/options and losses in `--conversion-note`. For naive dates,
`--assume-offset +07:00` supplies an explicit interpretation; otherwise the
timestamp remains unknown. A CSV file is not equivalent to a full forensic image.

Reports retain parser warnings, unknown timestamps and partial indexing. A valid
source hash does not prove that all records were parsed or the source was honest.
Labels, notes and console previews receive best-effort masking; raw originals and
local metadata still require appropriate storage access controls.

## Review without leaking the answers

Each new exercise contains:

| Path | Purpose |
|---|---|
| `practice.json` | Pinned rubric, exercise provenance, origin, assistance and run ID |
| `brief.md` | Learner-facing deliverables; no answer key |
| `attachments/` | Receipts bound to the manifest and imported source hashes |
| `review-template.json` | Empty operator review template |
| `world/forensics/` | Original copies, index and blue investigation sessions |
| `world/office.json` | Generated when the world runs |

The blue roster receives an investigation goal and can consult its pinned guide;
the CLI does not inject the entire brief as a new system prompt. The operator can
use the brief when assigning more specific work. Never import a solution or
completed operator review into the agent-visible evidence vault. Agent tools have
no arbitrary filesystem access to the sibling review files. File separation is
not protection against an operator with filesystem access.

Inspect the investigation and record-level evidence:

```powershell
uv run --no-sync saber world forensics sessions --out runs/my-investigation/world
uv run --no-sync saber world forensics inspect --out runs/my-investigation/world --session SESSION_ID
uv run --no-sync saber world forensics evidence --out runs/my-investigation/world --id RECORD_ID
uv run --no-sync saber training report --run runs/my-investigation
```

Copy `review-template.json` to a private `review.json`, fill `reviewer`, and review
each criterion using `supported`, `contradicted` or `inconclusive`. Leave
`unreviewed` for unfinished work. Nontrivial judgments require a rationale;
`supported`/`contradicted` additionally require record IDs from this exercise.
Keep the run ID and manifest hash unchanged.

```powershell
uv run --no-sync saber training report --run runs/my-investigation --review runs/my-investigation/review.json --out runs/my-investigation/report.json
```

The command rejects foreign/duplicate criteria and verifies cited records against
registered sources and original bytes. It reports `AWAITING_REVIEW`,
`REVIEW_INCOMPLETE`, `REVIEW_RECORDED` or `INTEGRITY_FAILURE`. Integrity failures
also give a nonzero CLI exit code. Existing report files are not overwritten.
Interrupted/failed attachment receipts remain visible and cause an integrity
failure; inspect them and preserve the failed run, then use a fresh run for retry.

**`REVIEW_RECORDED` does not mean passed.** It can contain contradicted or
inconclusive criteria. Reviewer identity is supplied by the operator, not
authenticated; citations are checked structurally, not for semantic relevance.
The result always retains `semantic_verification: false` and
`benchmark_ready: false`. No automatic grading, certification, skill promotion
or frozen benchmark score is produced.

## Skills and live integration boundaries

The red guide is `external-practice` for recon/access and
`redteam-initial-access--external-practice` for impact. Blue uses
`soc-orchestrator--external-practice`; the lead's own topic is `external-practice`.
All twelve blue specialties can select the guide. Clients keep their benign
workflows and cannot consult the red/blue guides.

The new guides use skill frontmatter `metadata.saber-library`. They are validated,
hashed, pinned, exported and available through `consult_skill`; they are not
eagerly appended to the already large case prompt. Existing case references
remain unchanged. Existing running worlds retain their pinned version; use a
fresh world to try these additions.

| Capability | Current status |
|---|---|
| Local track/manifest/rubric and source registration | Implemented |
| Historical evidence investigation in SABER/Office | Implemented through existing world tools |
| Evidence integrity and attributed operator review | Implemented; not semantic auto-grading |
| HTB content download, account login, VPN, lab start/reset | Not implemented |
| Agent-controlled HTB attacks, telemetry export or containment | Not implemented |
| Concurrent client/red/blue activity on HTB | Not established; keep SABER's own controlled range |

A future connector needs the specific product/account entitlement, documented
endpoints, assigned targets and execution window, authenticated tool adapter,
measured results and verified telemetry access. Public API catalog/framework
access alone does not establish those capabilities. Do not treat this work as
an HTB sandbox replacement or a promise of perpetual lab availability.

## Official references

Reviewed 2026-11-05. These links describe products; SABER's tracks are independently
authored and carry no HTB endorsement. Third-party evidence retains its own terms.

- [Pro Labs](https://help.hackthebox.com/en/articles/5185470-how-to-play-pro-labs): enterprise network practice.
- [Sherlocks](https://help.hackthebox.com/en/articles/8570249-how-to-play-sherlocks): investigation packages and categories.
- [SOC Range](https://enterprise-help.hackthebox.com/en/articles/15654060-soc-range): licensed Enterprise investigation workflow.
- [Agent competence](https://www.hackthebox.com/ai/agent-competence): AI Range assessment, initially focused on pentesting agents.
- [Enterprise API](https://enterprise-help.hackthebox.com/en/articles/13375637-introduction-to-enterprise-public-api): Enterprise accounts, role permissions, metadata/framework endpoints and account-wide rate limits.
