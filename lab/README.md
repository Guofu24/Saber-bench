# SABER reproducible Linux lab (Phase E3)

A small, isolated, reproducible Linux lab that produces **genuine** host telemetry from a **benign**
workload. It is the real-telemetry substrate for the `soc`/`vm` modes, and it is intentionally
minimal and safe: no attack tooling ships here.

## Status

- **Plan validated offline** (`saber.range.validate_lab_plan`): isolation and hardening checks pass.
- **Not launched here**: the Docker Linux daemon is stopped on this host (blocker CR-1), so no
  container has run. The agent never starts Docker. Bring-up is an operator action.

## Isolation and safety

- Network `labnet` is `internal: true` — **no outbound egress**.
- The workload container runs `read_only` rootfs + `tmpfs:/tmp`, `cap_drop: ALL`,
  `no-new-privileges`, and mounts its script read-only.
- The workload only writes benign Sysmon-like JSON events; it performs no network calls, no
  privilege changes, and no persistence.

## Bring up / reset (operator, once Docker or WSL2 is available)

```bash
docker compose -f lab/docker-compose.yml up -d        # start
docker compose -f lab/docker-compose.yml logs -f      # watch
docker compose -f lab/docker-compose.yml down -v      # reset (wipes the telemetry volume)
```

## Telemetry → ingestion

The workload appends `events.jsonl` (Sysmon-like) to the `telemetry` volume. Copy it out and ingest
it with the Phase E1 importer, which validates and attaches provenance:

```python
from saber.evaldata import import_dataset, DataSource, LabelTier
src = DataSource(name="saber-lab", kind="event_log", url="local://lab",
                 license="internal", usage_permitted=True)
res = import_dataset("events.jsonl", source=src, label_tier=LabelTier.SYNTHETIC)
```

Because the workload is benign, these events are a **benign baseline** (`SYNTHETIC` tier here, as the
lab authored them). Malicious/attack telemetry requires an **authorized** lab with reviewed,
allowlisted emulation and the independent state verifier — still `BLOCKED_INTEGRATION`.

## Adapter

`saber.range.DockerLabController` implements the `RangeController` port against this lab. It fails
closed (`IntegrationBlocked`, CR-1) while the daemon is down; stateful snapshot/restore stay blocked
until an authorized lab with an independent state verifier and per-run approval exists
(SECURITY.md H-gates). No real integration is claimed until it is exercised there.
