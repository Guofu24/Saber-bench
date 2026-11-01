# ADR 0002 — persistent local application world

Date: 2026-11-01. Status: implemented for the local application backend.

The operator requested a persistent population of ordinary clients, offensive teams
and specialized SOC teams acting on the same environment. Episode reset semantics
cannot model users continuing work while an incident evolves. Add `saber world` as
a separate experimental runtime; retain the frozen catalog and existing episode
protocol unchanged.

Use SQLite/WAL and role-bound loopback HTTP capabilities with synthetic business
data. Agents consume observations, not database handles. Application effects and
ground-truth accounting run independently of the agent policies. Blue case closure
requires a verified response whose postcondition still holds. Clients learn about
incidents only through observed failures and explicitly delivered notifications.

Schedule actors cooperatively with a rotating start order. Use bounded background
inference workers for LLM plans, retaining an explicitly labeled scripted fallback.
Project quotas and attempt reservations live in durable control-plane state. API
keys stay outside lab tools and observations. A default run performs no LLM calls.

Retain evidence across restarts. Compact old event/effect pairs into hashed private
archives, retain case evidence snapshots, and stop when disk limits are reached.
The file lock prevents two workers writing the same world; a supervisor can restart
failed workers with bounded backoff, without clearing STOP or resetting budgets.

This backend executes local HTTP and application-state changes. It does not claim
OS-level exploitation, per-agent VM isolation, real packet-flood denial of service,
or independently validated benchmark results. Extending to real OS/range backends
requires dedicated adapters and the established infrastructure authorization gates.
