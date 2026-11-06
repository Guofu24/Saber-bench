# External practice: red-team evidence and transferable skills

Use for operator-assigned practice inspired by HTB Machines, Pro Labs or AI Range.
This is SABER-authored methodology, not an HTB solution, executable connector or
permission to contact a target. Keep the current runtime menu and target scope.
An HTB exercise URL is a content reference, never an attack destination. If the
required executor is absent, record the missing capability instead of translating
instructions into an ungranted shell call.

## Plan the exercise

Record the exercise/version, environment/session ID, reset boundary, assigned
targets, exclusions, starting principal, tools, action/time budgets and objective.
Separate the learner's brief from flags, solutions, evaluator truth and blue-team
private observations. A walkthrough-assisted attempt is practice; do not compare
it with an unseen evaluation. Reset instances between comparable attempts and
record model, skill version, tool versions and failures as well as successes.

Build a small hypothesis ledger: observation, interpretation, competing
explanation, next discriminating check and expected evidence. Follow the most
informative supported check; neither run every technique nor repeat identical
failed attempts until quota runs out. Infrastructure/authentication/rate-limit
failure is not a demonstrated skill failure. Pause on expired scope or budget.

## Initial-access capabilities

| Capability | Evidence to seek | Common incorrect conclusion |
|---|---|---|
| Asset/service enumeration | Assigned address, service observation, timestamp and source; unresolved hosts remain unknown | A version banner proves exploitability |
| Web/API access boundaries | Same operation/resource compared under the relevant principals, expected policy and actual result | HTTP 200, a redirect or verbose error proves unauthorized access |
| Authentication/session handling | Starting identity, granted role, session expiry and server-side result | A login form submission proves a valid session |
| Input/data boundary testing | Controlled input, resulting data/behavior, repeatable comparison and affected scope | An echoed marker proves code execution |
| Windows/Linux access | Host identity, observed principal and allowed operation after access | A tool's success message proves a foothold on the intended host |

Use inert actions supported by the SABER lab to practise these decisions. The
guide does not install scanners, supply payloads, change egress, or convert native
execution into an arbitrary terminal. For external practice, the operator must
provide the separately authorized executor and actual execution receipts.

## Enterprise paths and post-access validation

Represent a path as evidence-backed transitions between assets, principals and
privileges. For each edge, record prerequisites, attempted action, resulting
identity/capability and verification. Distinguish:

- An exposed service, a valid account, a usable session and a privileged session.
- A candidate AD relationship and an actually traversed trust/authorization edge.
- A reachable destination and a verified lateral session on that destination.
- A readable file, an acquired copy and a transfer observed at the lab sink.
- A registered job and an executed job; a response request and effective state.

Re-check capability after a reset or expiry. Never carry a previous attempt's
foothold or target addresses into a new run without verification. Share the
current principal, target, receipt IDs, limitations and next objective with the
red teammate receiving the work. Missing routes or tools are blockers, not an
instruction to invent a pivot or broaden the target list.

## Closeout and learning

Produce an action timeline including unsuccessful attempts, confirmed access
boundaries, unsupported claims, remaining objectives and cleanup receipts.
Keep target response latency, provider usage and failed tool calls separate.
For an operator's debrief, compare red effects with independently collected
telemetry and blue decisions. Do not expose the red plan to blue during the run.
An accepted flag can establish an exercise objective under that exercise's rules;
it does not establish stealth, business impact or blue-team failure.

Turn failures into conditional lessons: symptom, evidence, mistaken assumption,
corrected decision and a fresh replay that can falsify it. Remove task-specific
answers, flags and target credentials before proposing a skill update. The
existing review/replay process publishes lessons; the agent cannot self-certify
an improvement or claim an HTB certification.

## Sources and limits

Reviewed 2026-11-05. Official descriptions inform capability selection; execution
rights and available features depend on the assigned product/session.

- [Pro Labs](https://help.hackthebox.com/en/articles/5185470-how-to-play-pro-labs): enterprise-network practice.
- [Agent competence](https://www.hackthebox.com/ai/agent-competence): AI Range's initial role focus is penetration testing.
- [Enterprise API](https://enterprise-help.hackthebox.com/en/articles/13375637-introduction-to-enterprise-public-api): Enterprise accounts and role-scoped API; catalog access does not prove runtime control.
