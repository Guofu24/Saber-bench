"""Evidence-producing analyst workflows over real collector records."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.lab.query import Search, normalized
from saber.lab.transport import request

ANALYSIS_TOOLS = {
    "review_cases",
    "triage_cases",
    "hunt",
    "export_case",
    "timeline",
    "evaluate_rule",
    "network_hunt",
    "identity_hunt",
    "correlate_indicator",
    "sensor_health",
    "verify_recovery",
    "analyze_evidence",
}


def write_artifact(name: str, value: Any) -> dict[str, Any]:
    path = Path(name)
    if path.is_symlink():
        raise ValueError("Artifact links are forbidden")
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2).encode()
    if len(raw) > 2_000_000:
        raise ValueError("Analysis export exceeds budget; narrow the query")
    path.write_bytes(raw)
    return {"name": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def execute(job: dict[str, Any]) -> dict[str, Any]:
    tool, args = job["tool"], job["args"]
    collector, token = job["collector"], job["read_token"]

    def get(path: str, body: Any = None) -> dict[str, Any]:
        status, value = request(collector + path, token=token, body=body)
        if status != 200 or not isinstance(value, dict):
            raise ConnectionError("Evidence service unavailable; no analysis result produced")
        return value

    def query(value: dict[str, Any]) -> dict[str, Any]:
        return get("/search", Search.model_validate(value).model_dump(exclude_none=True))

    if tool == "sensor_health":
        status = get("/status")
        sources = [
            {
                "host": host,
                "last_seen": stamp,
                "age_seconds": max(
                    0, round((datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds())
                ),
                "meaning": "last acknowledged event; silence alone does not prove sensor failure",
            }
            for host, stamp in status["sources"].items()
        ]
        analysis = {
            "sources": sources,
            "raw_events": status["raw_events"],
            "indexed_events": status["indexed_events"],
            "pending_indexing": status["raw_events"] - status["indexed_events"],
        }
    elif tool in ("triage_cases", "review_cases"):
        cases = get("/cases")["cases"]
        analysis = {
            "cases": [
                {
                    k: c[k]
                    for k in (
                        "id",
                        "status",
                        "rule",
                        "principal",
                        "evidence_ids",
                        "responses",
                        "assignee",
                    )
                    if k in c
                }
                for c in cases[:100]
            ],
            "total_in_window": len(cases),
            "unassigned": sum(not c.get("assignee") for c in cases),
            "unresponded": sum(not c.get("responses") for c in cases),
        }
    elif tool in ("export_case", "timeline", "analyze_evidence"):
        case_id = args.get("case_id")
        case = next((c for c in get("/cases")["cases"] if c["id"] == case_id), None)
        if case is None:
            raise ValueError("An observed case_id is required")
        evidence_ids = list(
            dict.fromkeys(
                [
                    *case["evidence_ids"],
                    *[r["event_id"] for r in case.get("responses", []) if r.get("event_id")],
                ]
            )
        )
        if len(evidence_ids) > 50:
            raise ValueError("Case exceeds single-export budget")
        records = []
        for eid in evidence_ids:
            proof = get("/evidence/" + eid)
            raw = json.dumps(
                proof["event"], sort_keys=True, ensure_ascii=True, separators=(",", ":")
            ).encode()
            if hashlib.sha256(raw).hexdigest() != proof["sha256"]:
                raise ValueError("Raw evidence integrity check failed")
            records.append(proof)
        records.sort(key=lambda r: (r["event"]["ts"], r["event"]["id"]))
        timeline = [
            {
                "id": r["event"]["id"],
                "ts": r["event"]["ts"],
                "host": r["event"]["host"],
                "kind": r["event"]["kind"],
                "sha256": r["sha256"],
                "fields": normalized(r["event"]),
            }
            for r in records
        ]
        package = write_artifact(
            "case-evidence.json", {"schema_version": 1, "case": case, "records": records}
        )
        ordered = write_artifact("case-timeline.json", timeline)
        analysis = {
            "case_id": case_id,
            "verified_records": len(records),
            "timeline": timeline,
            "exports": [package, ordered],
            "scope": "collector evidence and recorded responses; not a disk or memory image",
        }
    elif tool == "verify_recovery":
        cases = get("/cases")["cases"]
        case = next((c for c in cases if c["id"] == args.get("case_id")), None)
        if not case or not case.get("responses"):
            raise ValueError("Responded case required")
        after = max(r["at"] for r in case["responses"])
        denial = query(
            {
                "after": after,
                "filters": [{"field": "principal", "value": case["principal"]}],
                "limit": 100,
            }
        )
        work = query({"after": after, "kind": "file.write", "limit": 100})
        denied = [
            e["id"] for e in denial["events"] if e["kind"] in ("auth.denied", "file.access_denied")
        ]
        productive = [e["id"] for e in work["events"] if e["data"].get("status") == 200]
        analysis = {
            "case_id": case["id"],
            "after": after,
            "blocked_access_evidence": denied,
            "client_work_evidence": productive,
            "verified": bool(denied and productive),
            "scope": "post-response application observations; no inference from response status alone",
        }
    else:
        search = dict(args.get("query", {}))
        if tool == "network_hunt":
            search.setdefault("host", "network")
        if tool == "identity_hunt":
            search.setdefault("kind", "windows.event")
        if tool == "correlate_indicator":
            kind = args.get("type")
            field = {"ip": "destination_ip", "domain": "domain", "sha256": "sha256"}.get(kind)
            if not field:
                raise ValueError("Indicator type must be ip, domain or sha256")
            search["filters"] = [{"field": field, "value": str(args.get("value", ""))}]
        if tool in ("hunt", "evaluate_rule") and not any(
            search.get(k) for k in ("filters", "kind", "host")
        ):
            raise ValueError("A hypothesis requires a host, kind or field predicate")
        page = query(search)
        events = page["events"]
        fields = [normalized(e) for e in events]
        analysis = {
            "query": search,
            "as_of": page["as_of"],
            "matches": len(events),
            "evidence_ids": [e["id"] for e in events],
            "next_cursor": page["next_cursor"],
            "complete_window": page["next_cursor"] is None,
            "findings": {
                "kinds": dict(Counter(e["kind"] for e in events)),
                "destinations": dict(
                    Counter(f["destination_ip"] for f in fields if f.get("destination_ip"))
                ),
                "domains": dict(Counter(f["domain"] for f in fields if f.get("domain"))),
                "principals": dict(Counter(f["principal"] for f in fields if f.get("principal"))),
                "event_codes": dict(
                    Counter(f["event_code"] for f in fields if f.get("event_code"))
                ),
            },
            "scope": "observed matches; no maliciousness label or external reputation inferred",
        }
        if tool == "evaluate_rule":
            analysis["evaluation_artifact"] = write_artifact("rule-evaluation.json", analysis)
    artifact = write_artifact("analysis.json", {"tool": tool, **analysis})
    return {"status": 200, "analysis": analysis, "artifact": artifact}
