# SABER gold-label adjudication package (Phase G4)

- Generated: 2026-10-20T09:49:58+00:00
- Status: **PENDING_EXPERT_REVIEW** — sign_off: None
- Independently validated gold labels: 0; READY_BENCHMARK subtasks: 0

These are PROPOSED automated-lab labels, NOT expert-approved. They are not auto-approved; a qualified independent reviewer must confirm them before any promotion.

## External review required
- Reviewer: a qualified SOC/IR lead independent of this project
- Scope: confirm, per family, the proposed malicious labels and the scoring convention; resolve the listed ambiguities; sign off or return corrections
- Promotion rule: only a signed, independent confirmation may move a subtask from AUTOMATED_LAB_GROUND_TRUTH toward INDEPENDENTLY_VERIFIED / READY_BENCHMARK

## Evidence bundles
### web_sqli_probe (seed 9001)
- Bound subtask: T1347.001 / T0020.001 (set_delta)
- Proposed malicious labels: 5 line(s); cross-check True
- Scoring convention: A request line is malicious iff its URL-decoded target contains a SQL token COMBINATION (e.g. UNION SELECT, ' OR, 1=1, SLEEP(); a lone SQL word is benign.
- Accepted alternatives: ['treat a benign request with a single SQL keyword as benign (current)', 'a stricter policy could flag any request from a scanner UA regardless of payload']
- Unresolved ambiguities: ["is an in-scope authorized pentest's probe a true positive or an exclusion?", 'should obfuscated/double-encoded payloads beyond the current token set count?']
- Reviewer decision: None (to be completed by the reviewer)

### auth_bruteforce (seed 9001)
- Bound subtask: none (workflow artifact; threshold convention needs a business owner)
- Proposed malicious labels: 11 line(s); cross-check True
- Scoring convention: A 401 is malicious iff its user exceeds 3 failed logins in the window (brute force is a volume phenomenon); a single benign typo is not an attack.
- Accepted alternatives: ['threshold could be 5 or time-windowed; low-and-slow distributed attempts are NOT captured']
- Unresolved ambiguities: ['the exact threshold is business-specific', 'credential stuffing (one attempt per account across many accounts) is not modeled']
- Reviewer decision: None (to be completed by the reviewer)

### fs_change (seed 9001)
- Bound subtask: none (workflow artifact; verified reversible IR action, not a scored contract)
- Proposed malicious labels: 2 line(s); cross-check True
- Scoring convention: A webroot file is unauthorized iff it is a server-side script (.php/.aspx/.jsp/.cgi) present on disk with the webshell marker.
- Accepted alternatives: ['an approved/signed script deployment could be legitimate; a change-management allowlist would reclassify it']
- Unresolved ambiguities: ['is ANY server-side script in the webroot unauthorized, or only unexpected ones?', 'who is the approving authority for a legitimate deployment?']
- Reviewer decision: None (to be completed by the reviewer)

