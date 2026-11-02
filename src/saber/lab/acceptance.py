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
    code, network = request(
        endpoint + "/search", token=token, body={"host": "network", "limit": 100}
    )
    checks["zeek_network_evidence"] = code == 200 and any(
        e["sensor"] == "zeek-log-v1"
        and e["kind"] in ("network.conn", "network.http")
        and datetime.fromisoformat(e["ts"]) >= recent
        for e in network.get("events", [])
    )
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
    if spec.windows:
        checks["domain_response_verified_with_rollback"] = code == 200 and any(
            c.get("rule") == "lab-domain-failed-logon"
            and any(
                r.get("action") == "contain_domain_user" and r.get("verified") is True
                for r in c.get("responses", [])
            )
            for c in cases.get("cases", [])
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
    if spec.soar.enabled:
        code, playbooks = request(
            endpoint + "/search", token=token, body={"kind": "soar.completed", "limit": 100}
        )
        checks["verified_soar_playbook"] = code == 200 and any(
            e["host"].startswith("soar-")
            and e["data"].get("verified") is True
            and e["data"].get("playbook") in ("contain_session", "enforce_acl")
            for e in playbooks.get("events", [])
        )
    if spec.analysis.enabled:
        checks["native_analysis_controls"] = False
        try:
            from saber.lab.soar import checked_proof

            control = json.loads((bundle / "analysis-self-test.receipt.json").read_text())
            verified = []
            for job in control["jobs"]:
                event = checked_proof(endpoint, token, job["evidence_id"])["event"]
                verified.append(
                    event["kind"] == "analysis.completed"
                    and event["host"].startswith("analysis-")
                    and event["data"].get("state") == "SUCCEEDED"
                    and event["data"].get("job_id") == job["id"]
                    and event["data"].get("report_sha256") == job["report_sha256"]
                )
            checks["native_analysis_controls"] = (
                control["passed"] is True and len(verified) == 3 and all(verified)
            )
        except (OSError, ValueError, KeyError, ConnectionError):
            pass
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
