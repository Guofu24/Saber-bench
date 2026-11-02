"""Fixed child-process tools. Model output can select tools, never commands/URLs."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from saber.lab.analysis_tools import ANALYSIS_TOOLS
from saber.lab.analysis_tools import execute as analyze
from saber.lab.capabilities import TOOLS
from saber.lab.guest_work import WORK_TEAMS
from saber.lab.query import Search
from saber.lab.transport import request


def execute(job: dict[str, Any]) -> dict[str, Any]:
    team, tool = job["team"], job["tool"]
    if tool not in TOOLS[team]:
        raise ValueError("Tool not available to this team")
    app, collector, token = job["app"], job["collector"], job["token"]
    args = job["args"]
    if tool in ("run_playbook", "soar_status"):
        import re

        from saber.lab.soar import PlaybookJob

        endpoint = job.get("soar", "")
        if not endpoint:
            return {"status": 503, "error": "SOAR service not configured"}
        if tool == "run_playbook":
            payload = PlaybookJob(id=job["job_id"], **args)
            status, result = request(
                endpoint + "/jobs", token=job["actor_token"], body=payload.model_dump()
            )
        else:
            job_id = str(args.get("job_id", ""))
            if not re.fullmatch(r"[a-f0-9-]{32,36}", job_id):
                raise ValueError("Invalid SOAR job ID")
            status, result = request(endpoint + "/jobs/" + job_id, token=job["actor_token"])
        if status == 200:
            return {
                "status": 200
                if result["state"] in ("SUCCEEDED", "FAILED", "INDETERMINATE")
                else 202,
                "soar_job": result,
                "evidence_id": result.get("evidence_id"),
            }
        return {"status": status, **result}
    if tool in ("list_samples", "tool_status", "analyze_sample", "analysis_status"):
        import re

        endpoint = job.get("analysis", "")
        if not endpoint:
            return {"status": 503, "error": "Analysis service not configured"}
        if tool == "analyze_sample":
            from saber.lab.analyzers import AnalysisJob

            analysis_payload = AnalysisJob(id=job["job_id"], **args)
            status, result = request(
                endpoint + "/jobs", token=job["actor_token"], body=analysis_payload.model_dump()
            )
        elif tool == "analysis_status":
            job_id = str(args.get("job_id", ""))
            if not re.fullmatch(r"[a-f0-9-]{32,36}", job_id):
                raise ValueError("Invalid analysis job ID")
            status, result = request(endpoint + "/jobs/" + job_id, token=job["actor_token"])
        else:
            status, result = request(
                endpoint + ("/samples" if tool == "list_samples" else "/tools"),
                token=job["actor_token"],
            )
        if tool in ("analyze_sample", "analysis_status") and status == 200:
            return {
                "status": 202 if result["state"] in ("QUEUED", "RUNNING") else 200,
                "analysis_job": result,
                "evidence_id": result.get("evidence_id"),
            }
        return {"status": status, **result}
    if tool in WORK_TEAMS:
        status, result = request(
            collector + "/guest/work",
            token=job["actor_token"],
            body={"id": job["job_id"], "tool": tool, "node": args.get("node", "")},
        )
        if status == 200:
            return {
                "status": 202 if result["state"] in ("QUEUED", "DISPATCHED") else 200,
                "guest_work": result,
            }
        return {"status": status, **result}
    if tool == "windows_job_status":
        import re

        job_id = str(args.get("job_id", ""))
        if not re.fullmatch(r"[a-f0-9-]{32,36}", job_id):
            raise ValueError("Invalid guest job ID")
        status, result = request(collector + "/guest/work/" + job_id, token=job["actor_token"])
        return {
            "status": 202
            if status == 200 and result["state"] in ("QUEUED", "DISPATCHED")
            else status,
            "guest_work": result,
        }
    if tool in ANALYSIS_TOOLS:
        return analyze(job)
    if tool == "share":
        status, result = request(collector + "/team/messages", token=job["actor_token"], body=args)
    elif tool == "read_messages":
        status, result = request(collector + "/team/messages", token=job["actor_token"])
    elif tool in ("assign_case", "publish_rule"):
        status, result = request(
            collector + ("/cases/assign" if tool == "assign_case" else "/rules"),
            token=job["actor_token"],
            body=args,
        )
    elif tool == "login":
        status, result = request(app + "/login", token=token, body={})
    elif tool == "browse":
        if team == "client" and job.get("browser", True):
            import importlib

            sync_playwright = importlib.import_module("playwright.sync_api").sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    **(
                        {"executable_path": job["browser_executable"]}
                        if job.get("browser_executable")
                        else {}
                    ),
                )
                context = browser.new_context(
                    extra_http_headers={"Authorization": "Bearer " + token}
                )
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(app + "/")
                        else route.abort()
                    ),
                )
                page = context.new_page()
                page.goto(app + "/", wait_until="domcontentloaded", timeout=15000)
                page.locator("#documents").click()
                page.wait_for_function(
                    "document.querySelector('#output').textContent.includes('documents')"
                )
                result = json.loads(page.locator("#output").inner_text())
                page.screenshot(path="browser.png")
                context.close()
                browser.close()
                status = result["status"]
        else:
            status, result = request(app + "/documents", token=token)
    elif tool == "read_document":
        # Observed document IDs, not paths or external URLs.
        import re

        document = str(args.get("document", ""))
        if not re.fullmatch(r"acct-[a-f0-9]{12}", document):
            raise ValueError("Invalid document ID")
        status, result = request(app + "/documents/" + document, token=token)
        if result.get("status") == 200:
            Path("read-document.txt").write_text(result["text"], encoding="utf-8")
            result["sha256"] = hashlib.sha256(Path("read-document.txt").read_bytes()).hexdigest()
            result.pop("text", None)
    elif tool == "write_document":
        status, result = request(
            app + "/documents",
            method="PUT",
            token=token,
            body={"text": str(args.get("text", "Synthetic work revision"))[:2000]},
        )
    elif tool == "collect":
        source = Path("read-document.txt")
        if not source.is_file() or source.is_symlink():
            raise ValueError("No previously read document to collect")
        Path("collected.txt").write_bytes(source.read_bytes())
        status, result = (
            200,
            {
                "status": 200,
                "bytes": source.stat().st_size,
                "sha256": hashlib.sha256(Path("collected.txt").read_bytes()).hexdigest(),
            },
        )
    elif tool == "contain_domain_user":
        status, result = request(
            collector + "/guest/actions",
            token=job["response_token"],
            body={"case_id": args.get("case_id", ""), "action": tool},
        )
        if status == 200 and result.get("state") in ("QUEUED", "DISPATCHED"):
            status = 202
    elif tool in ("query_events", "query_siem"):
        status, result = request(
            collector + ("/search" if tool == "query_events" else "/siem/search"),
            token=job["read_token"],
            body=Search.model_validate(args).model_dump(exclude_none=True),
        )
    elif tool == "investigate":
        _, cases = request(collector + "/cases", token=job["read_token"])
        evidence = []
        for case in cases.get("cases", [])[-10:]:
            for eid in case["evidence_ids"][:5]:
                code, record = request(collector + "/evidence/" + eid, token=job["read_token"])
                if code == 200:
                    raw = json.dumps(
                        record["event"], sort_keys=True, ensure_ascii=True, separators=(",", ":")
                    )
                    if hashlib.sha256(raw.encode()).hexdigest() != record["sha256"]:
                        raise ValueError("Evidence hash mismatch")
                    evidence.append(record)
        Path("evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        status, result = (
            200,
            {
                "status": 200,
                "cases": cases.get("cases", []),
                "artifacts": len(evidence),
                "sha256": hashlib.sha256(Path("evidence.json").read_bytes()).hexdigest(),
            },
        )
    else:
        _, data = request(collector + "/cases", token=job["read_token"])
        case = next((c for c in data.get("cases", []) if c["id"] == args.get("case_id")), None)
        if case is None:
            raise ValueError("Existing evidence-backed case required")
        status, result = request(
            app + "/respond",
            token=token,
            body={
                "action": tool,
                "principal": case["principal"],
                "evidence_id": case["evidence_ids"][0],
                "ttl_seconds": 60,
            },
        )
    return {"status": status, **result}


def main() -> None:
    try:
        job = json.loads(sys.stdin.buffer.readline(65537))
        print(json.dumps(execute(job)))
    except Exception as exc:
        print(json.dumps({"status": 502, "error": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
