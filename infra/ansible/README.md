# Ansible baseline (scaffolding)

Idempotent benign provisioning for lab hosts only (Windows workstation, Linux web/db, workload
runner, log collector). Inventories target allowlisted lab hosts; no passwords are committed.
Playbooks run only during an operator-supervised provisioning window (SECURITY.md). Left as a
scaffold until the lab gate (M2) is opened; not exercised by the offline benchmark.
