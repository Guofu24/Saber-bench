# SABER infrastructure (plan-only)

**None of this is applied automatically.** These files describe the *lab* deployment profile.
Real provisioning happens only under explicit operator control after the human gates in
`docs/SECURITY.md` (H1 infra write, H2 verified network isolation, H3 approved emulation profile,
H4 real containment). Until then every real adapter in `src/saber` is `BLOCKED_INTEGRATION`.

- `compose/` — local dev services (PostgreSQL, MinIO, OpenSearch). `docker compose` is **not**
  required for the offline benchmark; the default telemetry backend is the in-memory
  `FakeEventStore` and tests run with no services at all.
- `proxmox/` — isolated-lab topology **specification**. Validate a plan statically with
  `saber.infra.validate_lab_plan`; it rejects routes to production/Internet, NAT to production,
  VMs off the lab bridge, and non-deny-by-default networks. A passing plan is not proof of
  isolation — that requires on-host route/firewall tests at gate H2.
- `ansible/` — benign baseline provisioning scaffolding (lab hosts only; no secrets in repo).

Dev defaults are chosen so the benchmark core runs fully offline. The compose file exists for the
M2 lab profile and for adapter integration work, both of which stay BLOCKED_INTEGRATION here.
