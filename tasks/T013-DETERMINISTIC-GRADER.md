# T013 — Deterministic benchmark grader

## Goal

Build efficacy scoring that does not need an LLM judge to decide if an event was detected, whether attack execution succeeded, or whether the response target was correct.

## Required behavior

- Grade only episodes with complete, independently verified truth and required telemetry coverage.
- `AttackVerifier.NOT_VERIFIED` or `INDETERMINATE` -> `INVALID`, not false negative.
- On malicious episode, correct evidence-backed positive finding is TP; wrong or unverified event IDs do not count as evidence.
- On benign episode, a positive finding is FP. Track cases per benign host-hour and episode FPR.
- Report detection delays relative to both attack start and first observable event; missing detection must be marked censored.
- Use explicit denominators, zero division policy and confidence caveats for small samples.
- Separate source-level quality (data available) from agent quality (correct use of data).
- Export grader version and input record hashes.

## Golden test matrix

| Input | Expected |
|---|---|
| Verified malicious + supported positive | TP |
| Verified malicious + no positive | FN |
| Verified benign + positive | FP |
| Verified benign + no positive | TN |
| Unverified attack execution | INVALID (excluded efficacy) |
| Unsupported evidence IDs | unsupported finding, no evidence credit |
| Event visible after case decision | invalid time-travel support |
| Positive with multiple hosts, one correct | measured host precision and recall, not binary full credit |

No provider/network/Proxmox required. Require exact values in unit tests and deterministic JSON output.
