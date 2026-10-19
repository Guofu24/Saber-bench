#!/usr/bin/env python3
"""One-command, checkpointed Claude Code orchestrator for the SABER planning kit.

This is a *development supervisor*, not an automatic certification authority.
It never executes agent-supplied shell commands. Development status is gated by
fresh, independent test runs; real-world READY certification is separate.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".saber-autonomous"
STATE_FILE = STATE_DIR / "state.json"
RUN_LOGS = STATE_DIR / "logs"
RECEIPTS = STATE_DIR / "receipts"
MAX_COST_DEFAULT = 100.0  # relevant ONLY for explicit API billing mode


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def work_items() -> list[dict[str, str]]:
    data = json.loads((ROOT / "catalog/subtasks.json").read_text(encoding="utf8"))
    assert len(data) == 175, "source catalog must contain exactly 175 subtasks"
    by_id = {x["id"]: x for x in data}
    assert len(by_id) == 175

    items: list[dict[str, str]] = []

    def add(ids: list[str], phase: str, kind: str) -> None:
        for item_id in ids:
            if kind == "domain":
                item = by_id[item_id]
                spec = f"tasks/subtasks/{item_id}.md"
                environment = item["environment"]
            elif kind == "bridge":
                spec = "docs/IMPLEMENTATION_SEQUENCE.md"
                environment = "development"
            else:
                spec = f"tasks/T{item_id[1:]}-BOOTSTRAP.md" if item_id == "T001" else "tasks/BACKLOG.md"
                environment = "development"
            items.append({"id": item_id, "phase": phase, "kind": kind,
                          "spec": spec, "environment": environment})

    add([f"T{i:03d}" for i in range(1, 6)], "foundation", "engineering")
    add([f"B{i:03d}" for i in range(1, 6)], "bridge", "bridge")
    add([f"T{i:03d}" for i in range(6, 15)], "offline_engine", "engineering")
    pilot = ["T1112.001", "T1348.001", "T2012.001", "T0020.001", "T0173.001"]
    add(pilot, "pilot_file", "domain")
    add([f"T{i:03d}" for i in range(15, 25)], "range_adapters", "engineering")
    add([f"T{i:03d}" for i in range(25, 33)], "agents", "engineering")
    for env in ("file", "soc", "vm"):
        remaining = sorted(
            (row["id"] for row in data if row["environment"] == env and row["id"] not in pilot),
            key=lambda sid: (sid.split(".")[0], int(sid.split(".")[1])),
        )
        add(remaining, f"subtasks_{env}", "domain")
    add([f"T{i:03d}" for i in range(33, 39)], "evaluation_release", "engineering")
    assert len({i["id"] for i in items}) == len(items) == 218
    assert sum(i["kind"] == "domain" for i in items) == 175
    return items


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    tmp.replace(path)


def environment_snapshot() -> dict[str, Any]:
    """Local, read-only discovery only. No port scans or secrets read."""
    names = ("claude", "python3", "python", "uv", "git", "node", "npm", "docker",
             "podman", "virsh", "pvesh", "tofu", "terraform", "ansible",
             "pytest", "wazuh-control", "psql", "curl", "bwrap", "socat")
    executables = {key: shutil.which(key) for key in names}
    modules = {key: importlib.util.find_spec(key) is not None for key in
               ("pytest", "pydantic", "fastapi", "sqlalchemy", "httpx")}
    provisioned = ROOT / "config/existing-environment.json"
    inventory: Any = {"services": [], "approved_lab_hosts": [], "notes": "No user inventory supplied"}
    if provisioned.exists():
        inventory = json.loads(provisioned.read_text(encoding="utf8"))
        if not isinstance(inventory, dict):
            raise ValueError("existing-environment.json must be an object")
    # Non-invasive read-only inspection of services already running locally.
    # Never inspect container env, filesystem secrets, other tenants, or ports.
    local_services: dict[str, Any] = {}
    commands = {
        "docker_running": ["docker", "ps", "--format", "{{.Names}} | {{.Image}} | {{.Status}}"],
        "podman_running": ["podman", "ps", "--format", "{{.Names}} | {{.Image}} | {{.Status}}"],
        "virsh_vms": ["virsh", "list", "--all", "--name"],
        "process_names": ["ps", "-eo", "comm="],
    }
    for label, command in commands.items():
        if shutil.which(command[0]) is None:
            local_services[label] = {"available": False}
            continue
        try:
            probe = subprocess.run(command, cwd=ROOT, capture_output=True,
                                   text=True, timeout=7, check=False)
            lines = probe.stdout.splitlines()
            if label == "process_names":
                terms = ("wazuh", "elastic", "opensearch", "postgres", "minio",
                         "redis", "grafana", "suricata", "zeek", "mysql", "mongod")
                lines = [value.strip() for value in lines if any(t in value.lower() for t in terms)]
            local_services[label] = {"available": probe.returncode == 0,
                                     "observed": lines[:60]}
        except (OSError, subprocess.TimeoutExpired):
            local_services[label] = {"available": False, "reason": "unavailable/timeout"}
    snapshot = {"generated_at": utcnow(), "host_platform": sys.platform,
                "python_version": sys.version.split()[0],
                "executables": executables, "python_modules": modules,
                "local_services": local_services, "inventory": inventory,
                "policy": "reuse_first; no remote scanning; local project-only install when needed; no privileged auto-provision"}
    write_json(STATE_DIR / "environment.json", snapshot)
    return snapshot


def preflight(strict_sandbox: bool, billing_mode: str = "subscription") -> None:
    if shutil.which("claude") is None:
        raise RuntimeError("Claude Code CLI not found; install/sign in to Claude Code first")
    if strict_sandbox and sys.platform.startswith("linux"):
        missing = [tool for tool in ("bwrap", "socat") if shutil.which(tool) is None]
        if missing:
            raise RuntimeError("strict sandbox unavailable: missing " + ", ".join(missing) +
                               "; install the missing sandbox dependencies before the one-shot run")
    cmd = subprocess.run(["claude", "auth", "status"], cwd=ROOT,
                         capture_output=True, text=True, timeout=25, check=False)
    if cmd.returncode:
        raise RuntimeError("Claude Code is not authenticated (`claude auth status` failed)")
    if billing_mode == "subscription":
        # In print mode (-p), API environment credentials take precedence over
        # a Claude.ai subscription. Fail closed instead of risking pay-as-you-go.
        override_keys = (
            "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
            "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_FOUNDRY_API_KEY",
            "ANTHROPIC_VERTEX_PROJECT_ID", "AWS_BEARER_TOKEN_BEDROCK",
        )
        present = [name for name in override_keys if os.environ.get(name)]
        if present:
            raise RuntimeError(
                "Subscription-only mode refuses potentially billable API/backend "
                "configuration: " + ", ".join(present) + ". Unset these and sign "
                "in to a Claude Pro/Max/eligible organization account.")
        try:
            auth = json.loads(cmd.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Cannot verify subscription authentication from `claude auth status` JSON") from exc
        if not isinstance(auth, dict) or auth.get("authMethod") != "claude.ai":
            raise RuntimeError(
                "Expected Claude.ai subscription login (authMethod=claude.ai); "
                "actual authMethod=" + str(auth.get("authMethod") if isinstance(auth, dict) else None)
                + ". Run `claude auth login` with your subscription, not Console/API.")
    check = subprocess.run([sys.executable, "scripts/validate_catalog.py"], cwd=ROOT,
                           capture_output=True, text=True, timeout=40, check=False)
    if check.returncode:
        raise RuntimeError("Catalog failed validation: " + (check.stdout + check.stderr)[-1500:])


def initial_state(items: list[dict[str, str]]) -> dict[str, Any]:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf8"))
        if set(state["items"]) != {i["id"] for i in items}:
            raise RuntimeError("Existing checkpoint incompatible with catalog; do not discard it silently")
        return state
    result: dict[str, Any] = {"created_at": utcnow(), "updated_at": utcnow(),
        "estimated_api_cost_usd": 0.0, "invocations": 0, "quota_rechecks": 0,
        "items": {item["id"]: {"status": "PENDING", "attempts": 0,
                               "reason": "", "last_update": ""} for item in items}}
    write_json(STATE_FILE, result)
    return result


def record(state: dict[str, Any], item_id: str, status: str, reason: str = "") -> None:
    state["items"][item_id].update(status=status, reason=reason[:1000], last_update=utcnow())
    state["updated_at"] = utcnow()
    write_json(STATE_FILE, state)


def build_prompt(item: dict[str, str], attempt: int) -> str:
    receipt = f".saber-autonomous/receipts/{item['id']}.json"
    return f"""Execute ONE work item as part of the unattended SABER build supervisor.

WORK_ITEM: {item['id']}
KIND: {item['kind']}
PHASE: {item['phase']}
SOURCE_SPEC: {item['spec']}
ATTEMPT: {attempt}

Read CLAUDE.md, docs/AUTONOMOUS_EXECUTION.md, docs/ENVIRONMENT_FIRST.md,
.saber-autonomous/environment.json (discovered local tools/services),
config/existing-environment.json (if present), and SOURCE_SPEC. For domain items,
read catalog/subtasks.json and tasks/subtasks/{item['id']}.md. Do not modify the
frozen catalog or silently change benchmark semantics.

FIRST examine existing infrastructure, code, packages, VM/SIEM/SOAR services, and
available APIs. REUSE anything compatible. Do not reinstall, duplicate, or
replace healthy services. If a package is missing, first confirm absence; then
install only into a scoped project-local environment if allowed and truly needed.
Do not run sudo, modify production, run an attack, delete existing services,
change production credentials, or execute live response without a narrow,
pre-existing, verifiable authorization in an isolated lab.

Implement the work item end-to-end where possible. Add typed code, independent
scorer, DEV fixture (clearly labelled), negative/golden tests and working CLI
smoke paths as appropriate. For domain subtasks, provide the exact file
`tests/subtasks/test_{item['id'].lower().replace('.', '_')}.py`, and ensure
`python -m pytest -q` can run it. Genuine user-provided evidence and hidden
truth must not be invented. Isolated synthetic DEV data is allowed with honest
labels, but is never evidence of validated real benchmark coverage.

If external datasets, private truth, credentials, authorized lab, or approval
is absent, implement all safe/offline portions; report the precise blocker.
Keep on-disk progress and do not ask the user questions during this call.

At the very end, write {receipt} as VALID JSON:
{{
  "id": "{item['id']}",
  "status": "DONE_DEV" | "IMPLEMENTED_DEV" | "BLOCKED",
  "tests": [{{"command": "literal command actually run", "exit_code": 0}}],
  "changed_files": ["repo relative paths to actual implementation"],
  "blockers": ["specific missing prerequisite, if any"],
  "notes": "distinguish synthetic dev from verified lab evidence"
}}
Do not state PASSED unless tests were actually run. For a domain item use
IMPLEMENTED_DEV only if it has real runnable scorer + source-correct output
contract + dev episode + independent test; otherwise BLOCKED.
A receipt is not sufficient proof: the supervisor will independently run tests.
Finish this item, not the entire backlog in this one Claude invocation.
"""


def approved_service_domains() -> list[str]:
    """Use only explicitly authorised existing service hosts (never scan)."""
    inventory_path = ROOT / "config/existing-environment.json"
    if not inventory_path.is_file():
        return []
    try:
        inv = json.loads(inventory_path.read_text(encoding="utf8"))
    except (OSError, ValueError):
        return []
    domains: set[str] = set()
    for service in inv.get("services", []):
        if not isinstance(service, dict) or service.get("approved_for_read_only_use") is not True:
            continue
        base = service.get("api_base_url")
        if not isinstance(base, str):
            continue
        parsed = urlsplit(base)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            continue
        if parsed.hostname.upper().startswith("REPLACE-"):
            continue
        domains.add(parsed.hostname)
    return sorted(domains)


def claude_command(prompt: str, budget: float, turns: int, strict_sandbox: bool,
                   billing_mode: str = "subscription") -> list[str]:
    cmd = ["claude", "-p", prompt, "--permission-mode", "dontAsk",
           "--output-format", "stream-json", "--verbose", "--max-turns", str(turns),
           "--tools", "Bash,Read,Edit,Write,Glob,Grep,Agent",
           "--strict-mcp-config"]
    if billing_mode == "api":
        cmd += ["--max-budget-usd", f"{budget:.2f}"]
    # Deny-by-default with strictly scoped permissions. Sandboxed shell is
    # useful for ordinary commands; CLI permission mode will reject unknowns.
    safe_tools = ["Read", "Edit", "Write", "Glob", "Grep", "Agent",
        "Bash(python3 scripts/*)", "Bash(python scripts/*)",
        "Bash(python -m pytest *)", "Bash(python3 -m pytest *)",
        "Bash(python3 -m venv *)", "Bash(python -m venv *)",
        "Bash(.venv/bin/pip install *)", "Bash(.venv/bin/python *)",
        "Bash(uv run *)", "Bash(uv sync *)", "Bash(uv pip *)",
        "Bash(pip list *)", "Bash(python3 -m pip list *)",
        "Bash(.venv/bin/python *)", "Bash(pytest *)", "Bash(make *)",
        "Bash(git status *)", "Bash(git diff *)", "Bash(git log *)",
        "Bash(git add *)", "Bash(git commit *)",
        "Bash(npm run *)", "Bash(npm test *)", "Bash(node --version)",
        "Bash(python --version)", "Bash(python3 --version)",
        "Bash(command -v *)", "Bash(ls *)", "Bash(rg *)", "Bash(find *)",
        "Bash(cat *)", "Bash(head *)", "Bash(docker compose ps *)",
        "Bash(podman ps *)", "Bash(virsh list *)", "Bash(systemctl status *)"]
    cmd += ["--allowedTools", *safe_tools,
            "--disallowedTools", "mcp__*", "Bash(sudo *)", "Bash(terraform apply *)",
            "Bash(tofu apply *)", "Bash(ansible-playbook *)", "Bash(kubectl apply *)",
            "Bash(kubectl delete *)", "Bash(git push *)", "Bash(git reset --hard *)",
            "Bash(docker rm *)", "Bash(docker system prune *)"]
    if strict_sandbox:
        # None of this relaxes organization policies. No unsandboxed fallback.
        settings = {"sandbox": {"enabled": True, "failIfUnavailable": True,
                "allowUnsandboxedCommands": False,
                "network": {"allowedDomains": sorted({"pypi.org", "files.pythonhosted.org",
                                               "registry.npmjs.org", *approved_service_domains()})}}}
        cmd += ["--settings", json.dumps(settings)]
    return cmd



# Only recognized subscription usage-limit errors may pause and retry without
# consuming a development attempt. Auth, permissions, missing lab inputs, and
# ordinary test failures must NEVER turn into an infinite waiting loop.
_QUOTA_PATTERNS = (
    re.compile(r"\busage limit (?:reached|exceeded)\b", re.IGNORECASE),
    re.compile(r"\b(?:reached|exceeded) (?:your |the )?(?:five.hour|5.hour|weekly|session|usage) (?:usage )?limit\b", re.IGNORECASE),
    re.compile(r"\brate limit (?:reached|exceeded)\b", re.IGNORECASE),
    re.compile(r"\blimit reached.{0,80}\breset", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bout of usage\b", re.IGNORECASE),
)


def subscription_quota_exhausted(exit_code: int, error_detail: str) -> bool:
    """Check error output only; never interpret successful agent prose as a quota."""
    return exit_code != 0 and any(p.search(error_detail) for p in _QUOTA_PATTERNS)


def quota_recheck_seconds(detail: str, base_minutes: float) -> int:
    """Wait longer when an unambiguous relative reset hint exists.

    Never assume a time zone from a vague 'resets at 3 PM' message.
    Restrict sleeps to 2 hours so stopping the supervisor remains manageable.
    """
    delay = int(base_minutes * 60)
    pattern = re.search(r"reset(?:s|ting)?\s+in\s+(?:(\d+)\s*(?:hours?|hrs?|h)\s*)?(?:(\d+)\s*(?:minutes?|mins?|m)\b)?", detail, re.I)
    if pattern and (pattern.group(1) or pattern.group(2)):
        secs = int(pattern.group(1) or 0) * 3600 + int(pattern.group(2) or 0) * 60
        delay = secs + 90  # Account/CLI reset propagation margin.
    return max(60, min(delay, 2 * 3600))


def quota_wait_elapsed_hours(state_item: dict[str, Any]) -> float:
    since = state_item.get("quota_wait_started_at")
    if not isinstance(since, str):
        return 0.0
    try:
        value = datetime.fromisoformat(since)
        if value.tzinfo is None:
            return 0.0
        return max(0.0, (datetime.now(timezone.utc) - value).total_seconds() / 3600)
    except (TypeError, ValueError):
        return 0.0

def invoke(item: dict[str, str], attempt: int, budget: float, turns: int,
           timeout_sec: int, strict_sandbox: bool,
           billing_mode: str = "subscription") -> tuple[int, float, str]:
    RUN_LOGS.mkdir(parents=True, exist_ok=True)
    basename = f"{item['id']}-attempt{attempt}"
    outfile, errfile = RUN_LOGS / (basename + ".jsonl"), RUN_LOGS / (basename + ".stderr")
    prompt = build_prompt(item, attempt)
    cmd = claude_command(prompt, budget, turns, strict_sandbox, billing_mode)
    # Passing prompt as an argv element avoids shell injection. stdin is closed.
    print(f"[{utcnow()}] {item['id']} attempt={attempt} logs={outfile.relative_to(ROOT)}", flush=True)
    with outfile.open("w", encoding="utf8") as out, errfile.open("w", encoding="utf8") as err:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, start_new_session=True)
        try:
            rc = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            return 124, 0.0, "Timed out; inspect task log"
    result: dict[str, Any] | None = None
    with outfile.open("r", encoding="utf8") as f:
        for raw in f:
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("type") == "result":
                result = row
    if result is None:
        # Quota errors can occur before any stream-json result is emitted.
        stderr = errfile.read_text(encoding="utf8", errors="replace")[-2000:]
        return rc if rc else 2, 0.0, stderr or "No final result event; inspect stderr/log"
    # In subscription mode any model-price estimate is diagnostic, NOT a
    # charge to the user or a subscriber allowance. Ignore it for accounting.
    if billing_mode == "subscription":
        if result.get("is_error") and rc == 0:
            rc = 3
        errors = result.get("errors")
        context = str(result.get("result", ""))
        if errors:
            context += " " + str(errors)
        if rc:
            context += " " + errfile.read_text(encoding="utf8", errors="replace")[-1500:]
        return rc, 0.0, context[-2000:]
    estimated_cost = result.get("total_cost_usd")
    if not isinstance(estimated_cost, (int, float)) or estimated_cost < 0:
        # API mode must not continue without cost accounting.
        rc = rc or 9
        return rc, 0.0, "Cost metadata unavailable: stopping this item to avoid uncontrolled spending"
    if result.get("is_error") and rc == 0:
        rc = 3
    excerpt = str(result.get("result", ""))[-500:]
    return rc, float(estimated_cost), excerpt


def test_python() -> str:
    venv = ROOT / ".venv/bin/python"
    if venv.is_file():
        test = subprocess.run([str(venv), "-m", "pytest", "--version"], cwd=ROOT,
                              capture_output=True, timeout=15, check=False)
        if test.returncode == 0:
            return str(venv)
    return sys.executable


def verify(item: dict[str, str]) -> tuple[bool, str]:
    """Independent smoke verification; not a cryptographic lab attestation."""
    rid = item["id"]
    path = RECEIPTS / (rid + ".json")
    if not path.exists():
        return False, "Missing per-item receipt"
    try:
        receipt = json.loads(path.read_text(encoding="utf8"))
    except (ValueError, OSError) as exc:
        return False, f"Invalid receipt: {exc}"
    if receipt.get("id") != rid:
        return False, "Wrong receipt ID"
    if receipt.get("status") not in {"DONE_DEV", "IMPLEMENTED_DEV"}:
        return False, "; ".join(receipt.get("blockers", [])) or "Reported BLOCKED"
    changed = receipt.get("changed_files")
    if not isinstance(changed, list) or not changed or not receipt.get("tests"):
        return False, "No implementation file/test evidence declared"
    # Paths in a model-written receipt are untrusted and may not escape repo.
    safe_files: list[Path] = []
    for raw in changed:
        if not isinstance(raw, str):
            return False, "Invalid changed_files record"
        candidate = (ROOT / raw).resolve()
        if not candidate.is_relative_to(ROOT.resolve()) or not candidate.is_file():
            return False, "Missing/outside implementation path: " + raw
        safe_files.append(candidate)
    if not any(p.relative_to(ROOT).parts[0] in {"src", "tests", "scripts", "infra", "web", "scenarios", "schemas", "alembic", "pyproject.toml"} for p in safe_files):
        return False, "No real implementation source/test/config file in changed_files"
    if not all(isinstance(t, dict) and t.get("exit_code") == 0
               and isinstance(t.get("command"), str) for t in receipt["tests"]):
        return False, "Receipt contains missing or failing command records"

    if item["kind"] == "domain":
        testfile = ROOT / "tests/subtasks" / f"test_{rid.lower().replace('.', '_')}.py"
        if not testfile.is_file():
            return False, f"Required standalone test missing: {testfile.relative_to(ROOT)}"
        cmd = [test_python(), "-m", "pytest", "-q", str(testfile.relative_to(ROOT))]
    else:
        # A feature test changed in this item is required; otherwise a generic
        # catalog sanity check could falsely certify an unfinished engineering PR.
        feature_tests = [p.relative_to(ROOT).as_posix() for p in safe_files
                         if p.relative_to(ROOT).parts[0] == "tests"
                         and p.name.startswith("test_") and p.suffix == ".py"]
        if not feature_tests:
            return False, "No new feature test file declared for engineering item"
        cmd = [test_python(), "-m", "pytest", "-q", *feature_tests]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              timeout=240, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Independent verification failed to execute: {exc}"
    path = RUN_LOGS / f"{rid}-verify.txt"
    path.write_text("Command: " + " ".join(cmd) + "\nexit=" +
                    str(proc.returncode) + "\n" + proc.stdout + proc.stderr,
                    encoding="utf8")
    if proc.returncode:
        return False, f"Independent test failed (exit {proc.returncode})"
    return True, "Independent DEV tests passed; not lab-certified"


def report(items: list[dict[str, str]], state: dict[str, Any]) -> None:
    statuses: dict[str, list[str]] = {}
    for item in items:
        statuses.setdefault(state["items"][item["id"]]["status"], []).append(item["id"])
    lines = ["# SABER unattended development supervisor — measured status", "",
             f"Updated: {utcnow()}", "",
             f"- Total work items: **{len(items)}** (5 bridge + 38 engineering + 175 domain)",
             f"- Claude Code invocations: **{state['invocations']}** (quota-limited responses: {state.get('quota_rechecks', 0)})",
             (f"- API cost estimate: **${state['estimated_api_cost_usd']:.2f}** (not a billing guarantee)"
              if state.get("billing_mode") == "api" else
              "- Billing mode: **subscription** (included-plan usage; not metered here)"), "",
             "| Status | Count |", "|---|---:|"]
    for key in ("DONE_DEV", "PAUSED_QUOTA", "BLOCKED", "FAILED", "PENDING", "RUNNING"):
        lines.append(f"| {key} | {len(statuses.get(key, []))} |")
    lines += ["", "**DONE_DEV only means local development checks passed.** It is not real benchmark readiness.",
              "Private evidence/labels, live SOC connectivity and VM approvals require separate verification.",
              "", "## Unresolved tasks", ""]
    for item in items:
        d = state["items"][item["id"]]
        if d["status"] != "DONE_DEV":
            lines.append(f"- `{item['id']}` ({item['environment']}): {d['status']} — {d['reason']}")
    (STATE_DIR / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf8")
    billing = (f"api-cost-est=${state['estimated_api_cost_usd']:.2f}"
               if state.get("billing_mode") == "api" else "billing=subscription")
    print(f"Status: {len(statuses.get('DONE_DEV', []))}/{len(items)} DEV-verified; "
          f"blocked={len(statuses.get('BLOCKED', []))}, failed={len(statuses.get('FAILED', []))}; "
          f"{billing}; report={STATE_DIR / 'REPORT.md'}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--billing-mode", choices=("subscription", "api"),
                        default="subscription",
                        help="Default: use existing Claude.ai subscription only; API mode is explicit")
    parser.add_argument("--budget-usd", type=float, default=MAX_COST_DEFAULT,
                        help="Estimated USD limit, relevant ONLY to explicit --billing-mode api")
    parser.add_argument("--per-item-budget-usd", type=float, default=8.0)
    parser.add_argument("--max-turns", type=int, default=70)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--max-invocations", type=int, default=500)
    parser.add_argument("--timeout-minutes", type=int, default=90)
    parser.add_argument("--only", nargs="*", default=[], help="Optional IDs to run, for smoke testing")
    parser.add_argument("--retry-blocked", action="store_true",
                        help="After resolving external blockers, reset BLOCKED/FAILED attempts")
    parser.add_argument("--dry-run", action="store_true", help="List work without invoking Claude")
    parser.add_argument("--no-wait-on-quota", dest="wait_on_quota", action="store_false",
                        help="Stop at a Pro/Max subscription usage limit instead of waiting for reset")
    parser.add_argument("--quota-recheck-minutes", type=float, default=60.0,
                        help="Subscription-only retry interval if Claude does not report a reset duration")
    parser.add_argument("--max-quota-wait-hours", type=float, default=192.0,
                        help="Safety cap for consecutive quota waiting without a successful invocation")
    parser.set_defaults(wait_on_quota=True)
    parser.add_argument("--strict-sandbox", action="store_true",
                        help="Require sandbox and refuse unsandboxed fallbacks (recommended)")
    args = parser.parse_args()
    if args.budget_usd <= 0 or args.per_item_budget_usd <= 0 or args.max_attempts < 1:
        parser.error("budgets/attempt count must be positive")
    if args.quota_recheck_minutes <= 0 or args.max_quota_wait_hours <= 0:
        parser.error("quota recheck interval/wait limit must be positive")
    items = work_items()
    if args.only:
        unknown = set(args.only).difference(i["id"] for i in items)
        if unknown:
            parser.error(f"Unknown items: {sorted(unknown)}")
        items = [item for item in items if item["id"] in args.only]
    print(f"SABER plan: {len(items)} items; {'DRY RUN' if args.dry_run else 'LIVE'}; "
          f"billing={args.billing_mode}", flush=True)
    if args.dry_run:
        for i in items:
            print(f" {i['phase']:<22} {i['id']:<14} {i['environment']}")
        return 0
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)
    environment_snapshot()
    try:
        preflight(args.strict_sandbox, args.billing_mode)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"PREFLIGHT BLOCKED: {exc}", file=sys.stderr)
        return 2
    # Always store complete queue to make partial --only smoke tests resumable.
    state = initial_state(work_items())
    prior_mode = state.get("billing_mode")
    if prior_mode and prior_mode != args.billing_mode:
        raise RuntimeError(f"Checkpoint belongs to billing_mode={prior_mode}; cannot silently switch to {args.billing_mode}")
    if not prior_mode and state["invocations"]:
        raise RuntimeError("Previous checkpoint has no billing_mode; manually review usage before migrating")
    state["billing_mode"] = args.billing_mode
    write_json(STATE_FILE, state)
    if args.retry_blocked:
        for item in items:
            entry = state["items"][item["id"]]
            if entry["status"] in {"BLOCKED", "FAILED"}:
                entry["attempts"] = 0
                record(state, item["id"], "PENDING", "Explicit retry after operator addressed blocker")
    budget_exhausted = False
    for item in items:
        sid = item["id"]
        data = state["items"][sid]
        if data["status"] == "DONE_DEV":
            continue
        # Process may have crashed after writing receipt, including on the
        # final permitted attempt. Verify it before checking the attempt cap.
        if data["status"] == "RUNNING":
            recovered, recovery_reason = verify(item)
            if recovered:
                record(state, sid, "DONE_DEV", recovery_reason)
                report(work_items(), state)
                continue
            if data["attempts"] >= args.max_attempts:
                record(state, sid, "FAILED", "Stale final attempt; " + recovery_reason)
                report(work_items(), state)
                continue
        # A previous process could die while a tool is executing; a stale
        # RUNNING item is resumed from the repository and receipt on disk.
        while data["attempts"] < args.max_attempts:
            if state["invocations"] - state.get("quota_rechecks", 0) >= args.max_invocations or \
               (args.billing_mode == "api" and state["estimated_api_cost_usd"] >= args.budget_usd):
                budget_exhausted = True
                break
            attempt = data["attempts"] + 1
            # Before any new Claude invocation, verify a surviving receipt.
            if data["status"] == "RUNNING":
                ok, why = verify(item)
                if ok:
                    record(state, sid, "DONE_DEV", why)
                    break
            data["attempts"] = attempt
            record(state, sid, "RUNNING", f"Attempt {attempt}")
            remaining = max(0.01, args.budget_usd - state["estimated_api_cost_usd"])
            budget = min(args.per_item_budget_usd, remaining) if args.billing_mode == "api" else 0.0
            try:
                rc, cost, detail = invoke(item, attempt, budget, args.max_turns,
                                          args.timeout_minutes * 60, args.strict_sandbox,
                                          args.billing_mode)
            except (OSError, ValueError) as exc:
                rc, cost, detail = 2, 0.0, repr(exc)
            state["invocations"] += 1
            state["estimated_api_cost_usd"] += cost
            if args.billing_mode == "subscription" and subscription_quota_exhausted(rc, detail):
                state["quota_rechecks"] = state.get("quota_rechecks", 0) + 1
                # The work item never ran: do not consume one of its allowed
                # code/test attempts. Persist the pause and safely sleep until
                # subscription quota becomes available, without switching to API.
                data["attempts"] -= 1
                if "quota_wait_started_at" not in data:
                    data["quota_wait_started_at"] = utcnow()
                elapsed = quota_wait_elapsed_hours(data)
                record(state, sid, "PAUSED_QUOTA", "Claude Pro/Max usage limit reached; no API fallback")
                report(work_items(), state)
                if not args.wait_on_quota or elapsed >= args.max_quota_wait_hours:
                    print("Subscription quota paused. No extra usage purchased. "
                          "Resume with ./run.sh after reset, or adjust quota waiting policy.", flush=True)
                    return 6
                delay = quota_recheck_seconds(detail, args.quota_recheck_minutes)
                delay = min(delay, max(60, int((args.max_quota_wait_hours - elapsed) * 3600)))
                print(f"Subscription quota reached: waiting {delay // 60} minute(s), "
                      f"then retrying {sid} on the SAME subscription (no paid API).", flush=True)
                try:
                    time.sleep(delay)
                except KeyboardInterrupt:
                    print("Quota wait interrupted; checkpoint preserved.", flush=True)
                    return 130
                continue
            # Any non-quota response means the subscription is usable again.
            data.pop("quota_wait_started_at", None)
            ok, why = verify(item)
            if ok:
                record(state, sid, "DONE_DEV", why)
                break
            reason = f"claude_exit={rc}; {why}; {detail[:240]}"
            # External-data/approval blockers should not burn another expensive
            # attempt immediately. Next one-shot run can retry after provisioning.
            receipt_path = RECEIPTS / (sid + ".json")
            try:
                current_receipt = json.loads(receipt_path.read_text(encoding="utf8"))
            except (OSError, ValueError):
                current_receipt = {}
            if current_receipt.get("id") == sid and current_receipt.get("status") == "BLOCKED":
                record(state, sid, "BLOCKED", reason)
                break
            if data["attempts"] < args.max_attempts:
                record(state, sid, "FAILED", reason + "; will retry")
            else:
                is_block = "BLOCKED" in why.upper() or "blocked" in detail.lower()
                record(state, sid, "BLOCKED" if is_block else "FAILED", reason)
            report(work_items(), state)
        if budget_exhausted:
            break
        report(work_items(), state)
    report(work_items(), state)
    if budget_exhausted:
        print("Budget/invocation cap reached. Rerun same command to resume after adjusting limits.", flush=True)
        return 3
    missing = [item for item in items if state["items"][item["id"]]["status"] != "DONE_DEV"]
    if missing:
        print("Finished available attempts, with unresolved items. Check REPORT.md.", flush=True)
        return 4
    # Full integration regression check after selected work passes. Individual
    # feature tests alone do not prove the entire application still works.
    cmd = [test_python(), "-m", "pytest", "-q"]
    try:
        regression = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                    timeout=20 * 60, check=False)
        (RUN_LOGS / "final-regression.txt").write_text(
            "Command: " + " ".join(cmd) + "\nexit=" + str(regression.returncode) +
            "\n" + regression.stdout + regression.stderr, encoding="utf8")
        if regression.returncode:
            print("Full pytest regression FAILED; inspect final-regression.txt. No completed claim.", flush=True)
            return 5
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"Full pytest regression BLOCKED: {exc}", flush=True)
        return 5
    print("Selected items passed independent DEV tests and full pytest; "
          "lab/source certification remains separate.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
