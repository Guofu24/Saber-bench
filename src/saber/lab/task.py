"""Fixed child-process tools. Model output can select tools, never commands/URLs."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from saber.lab.transport import request

TOOLS = {
    "client": {"login", "browse", "read_document", "write_document"},
    "red": {"login", "browse", "read_document", "collect"},
    "blue": {"query_events", "query_siem", "investigate", "contain", "release", "patch", "unpatch"},
}


def execute(job: dict[str, Any]) -> dict[str, Any]:
    team, tool = job["team"], job["tool"]
    if tool not in TOOLS[team]:
        raise ValueError("Tool not available to this team")
    app, collector, token = job["app"], job["collector"], job["token"]
    args = job["args"]
    if tool == "login":
        status, result = request(app + "/login", token=token, body={})
    elif tool == "browse":
        if team == "client" and job.get("browser", True):
            import importlib

            sync_playwright = importlib.import_module("playwright.sync_api").sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
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
    elif tool in ("query_events", "query_siem"):
        status, result = request(
            collector + ("/search" if tool == "query_events" else "/siem/search"),
            token=job["read_token"],
            body={"limit": 100},
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
