# Portable SABER SOC lab

This bundle contains the application, team executors, controller, collector,
OpenSearch, Dashboards, Zeek and read-only Agent Office. Windows presets include
Hyper-V/domain provisioning, Sysmon collection and bounded AD containment/rollback.

Full instructions: `SOC_LAB_VI.md` beside this file. At the target, open `source/`:

```text
uv sync --frozen --no-dev
uv run --no-sync saber lab doctor --config ../lab.json --storage ..
uv run --no-sync saber lab credentials --bundle ..
uv run --no-sync saber lab up --bundle .. --on-target
uv run --no-sync saber lab status --bundle ..
uv run --no-sync saber lab verify --bundle ..
```

Office: localhost:7788. Dashboards: localhost:5601. Credentials are generated only
on the target and never printed. Keep `.secrets/` private; do not commit it.
`down` preserves volumes. Windows VHDX images/licenses and Microsoft-signed Sysmon
are supplied by the operator. Rendering this bundle does not verify runtime health.
