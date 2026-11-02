"""Fail-closed checks of running services and observed evidence, never generated files alone."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from saber.lab.deployment import verify_bundle
from saber.lab.ledger import now
from saber.lab.transport import request


def verify_live(bundle: Path, endpoint: str = "http://127.0.0.1:7789") -> dict[str, Any]:
    spec = verify_bundle(bundle)
    credentials = json.loads((bundle / ".secrets" / "controller.json").read_text())
    token = credentials["read_token"]
    checks: dict[str, bool] = {}
    code, status = request(endpoint + "/status", token=token)
    checks["collector_authenticated"] = code == 200
    code, raw = request(endpoint + "/search", token=token, body={"limit": 1000})
    events = raw.get("events", []) if code == 200 else []
    recent = datetime.now(UTC) - timedelta(minutes=5)
    events = [e for e in events if datetime.fromisoformat(e["ts"]) >= recent]
    checks["fresh_raw_evidence"] = bool(events)
    for team in ("client", "red", "blue"):
        checks[f"{team}_real_processes"] = any(
            e["host"].startswith(team + "-")
            and e["kind"] == "process.exit"
            and e["data"].get("exit_code") == 0
            for e in events
        )
    checks["client_browser_artifact"] = any(
        e["host"].startswith("client-")
        and any(
            a.get("name") == "browser.png" and a.get("bytes", 0) > 0
            for a in e["data"].get("artifacts", [])
        )
        for e in events
    )
    code, cases = request(endpoint + "/cases", token=token)
    checks["evidence_linked_response"] = code == 200 and any(
        c.get("responses") for c in cases.get("cases", [])
    )
    checks["enforced_denial_observed"] = any(
        e["kind"] in ("file.access_denied", "auth.denied") for e in events
    )
    checks["client_work_continues"] = any(
        e["kind"] == "file.write" and e["data"].get("status") == 200 for e in events
    )
    code, indexed = request(endpoint + "/siem/search", token=token, body={"limit": 100})
    checks["opensearch_query"] = (
        code == 200 and indexed.get("source") == "opensearch" and bool(indexed.get("events"))
    )
    raw_ids = {e["id"] for e in events}
    checks["indexed_raw_match"] = any(e["id"] in raw_ids for e in indexed.get("events", []))
    for node in spec.windows:
        code, data = request(
            endpoint + "/search", token=token, body={"host": node.name, "limit": 1000}
        )
        guest = (
            [e for e in data.get("events", []) if datetime.fromisoformat(e["ts"]) >= recent]
            if code == 200
            else []
        )
        checks[f"{node.name}_domain"] = any(
            e["kind"] == "windows.identity"
            and e["data"].get("domain", "").lower() == spec.domain
            and e["data"].get("part_of_domain") is True
            for e in guest
        )
        checks[f"{node.name}_sysmon"] = any(
            e["kind"] == "windows.event"
            and e["data"].get("channel") == "Microsoft-Windows-Sysmon/Operational"
            for e in guest
        )
        checks[f"{node.name}_security"] = any(
            e["kind"] == "windows.event" and e["data"].get("channel") == "Security" for e in guest
        )
    result = {
        "schema_version": 1,
        "preset": spec.preset,
        "checked_at": now(),
        "passed": all(checks.values()),
        "runtime_verified": all(checks.values()),
        "checks": checks,
        "raw_events": status.get("raw_events", 0),
        "indexed_events": status.get("indexed_events", 0),
        "scope": "observed lab workflow and telemetry; not a certification of all SOC capabilities",
    }
    (bundle / "verification.receipt.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result
