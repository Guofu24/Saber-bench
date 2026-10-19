# Implementation evidence template

**Task:** T### / Title  
**Branch / commit:** actual reference or "not created"  
**Status:** DONE | BLOCKED | PARTIAL

## Scope actually implemented

- Changed files (paths):
- Features and contract changes:
- Deliberately NOT included:

## Validation evidence

| Command/test | Result | Exit code | Note |
|---|---|---|---|
| `make lint` | actual output summary | | |
| `make typecheck` | actual output summary | | |
| `make test` | actual output summary | | |
| task-specific negative test | actual output summary | | |

## Safety and benchmark check

- [ ] No hidden truth leaked to Blue tool surface.
- [ ] No future-event or cross-episode query path introduced.
- [ ] No unauthorized external/lab actions executed.
- [ ] No credentials or private fixtures committed.
- [ ] Claims reflect observed evidence; unrun checks marked NOT RUN.

## Remaining issues

List blockers, assumptions, failed tests, unreviewed dependencies and suggested *next task* (do not implement it in this PR).
