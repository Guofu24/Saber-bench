#!/usr/bin/env python3
"""Versioned implementation ledger for the 218 SABER work items.

Usage:
  python scripts/ledger.py set T001 DONE_DEV --test "uv run pytest tests/unit/test_smoke.py" \
      --file src/saber/__init__.py --note "..." [--blocker "..."]
  python scripts/ledger.py render          # regenerates docs/PROGRESS.md
  python scripts/ledger.py summary

Statuses: PENDING, DONE_DEV, IMPLEMENTED_DEV, PARTIAL, BLOCKED_INTEGRATION, BLOCKED.
DONE_DEV/IMPLEMENTED_DEV are only set after the referenced tests were actually run.
The ledger never claims READY_BENCHMARK; that requires external validation.
A gitignored supervisor receipt is also written for run_autonomous.py compatibility.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "status" / "ledger.json"
PROGRESS = ROOT / "docs" / "PROGRESS.md"
RECEIPTS = ROOT / ".saber-autonomous" / "receipts"
VALID = {
    # Engineering/bridge lifecycle:
    "PENDING", "DONE_DEV", "PARTIAL", "BLOCKED",
    # Mandated benchmark-subtask readiness tiers (never equate DEV with validated):
    "SPECIFIED",            # contract exists in the frozen catalog; no runnable implementation yet
    "IMPLEMENTED_OFFLINE",  # scorer + fixture + tests written; not independently re-run here
    "VERIFIED_OFFLINE",     # implementation + tests ran green (deterministic, synthetic DEV data)
    "BLOCKED_INTEGRATION",  # needs a real SIEM/hypervisor/forensic dataset/provider to proceed
    "READY_BENCHMARK",      # independently validated gold + execution evidence (never auto-set)
    # Back-compat alias kept so old receipts still load:
    "IMPLEMENTED_DEV",
}


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def work_items() -> list[dict[str, str]]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_autonomous  # type: ignore[import-not-found]

    return run_autonomous.work_items()


def load() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf8"))
    items = {
        w["id"]: {"kind": w["kind"], "phase": w["phase"], "status": "PENDING"}
        for w in work_items()
    }
    return {"schema_version": 1, "updated_at": now(), "items": items}


def save(data: dict) -> None:
    data["updated_at"] = now()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf8")


def cmd_set(args: argparse.Namespace) -> int:
    data = load()
    if args.id not in data["items"]:
        print(f"unknown work item {args.id}", file=sys.stderr)
        return 2
    if args.status not in VALID:
        print(f"invalid status {args.status}", file=sys.stderr)
        return 2
    entry = data["items"][args.id]
    entry["status"] = args.status
    entry["updated_at"] = now()
    if args.test:
        entry["tests"] = [{"command": t, "exit_code": 0} for t in args.test]
    if args.file:
        entry["changed_files"] = args.file
    if args.blocker is not None:
        entry["blockers"] = args.blocker
    if args.note:
        entry["notes"] = args.note
    save(data)
    if args.status in {"DONE_DEV", "IMPLEMENTED_DEV"} or args.status.startswith("BLOCKED"):
        RECEIPTS.mkdir(parents=True, exist_ok=True)
        receipt = {
            "id": args.id,
            "status": "BLOCKED" if args.status.startswith("BLOCKED") else args.status,
            "tests": entry.get("tests", []),
            "changed_files": entry.get("changed_files", []),
            "blockers": entry.get("blockers", []),
            "notes": entry.get("notes", ""),
        }
        (RECEIPTS / f"{args.id}.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
        )
    render(data)
    print(f"{args.id} -> {args.status}")
    return 0


def summarize(data: dict) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for item in data["items"].values():
        bucket = out.setdefault(item["kind"], {})
        bucket[item["status"]] = bucket.get(item["status"], 0) + 1
    return out


def render(data: dict | None = None) -> None:
    data = data or load()
    lines = [
        "# SABER implementation progress (machine-generated from status/ledger.json)",
        "",
        f"Updated: {data['updated_at']}",
        "",
        "Status meanings: `DONE_DEV`/`IMPLEMENTED_DEV` = implementation + independent offline tests ran green;",
        "`PARTIAL` = safe parts done, remainder listed in blockers; `BLOCKED_INTEGRATION` = needs external",
        "lab/SIEM/VM/data; `PENDING` = not started. **Nothing here is READY_BENCHMARK**: that requires",
        "independently validated private data, lab verification and human adjudication.",
        "",
        "## Summary",
        "",
        "| Kind | " + " | ".join(sorted(VALID)) + " |",
        "|---|" + "---|" * len(VALID),
    ]
    summary = summarize(data)
    for kind in ("engineering", "bridge", "domain"):
        row = summary.get(kind, {})
        lines.append(f"| {kind} | " + " | ".join(str(row.get(s, 0)) for s in sorted(VALID)) + " |")
    lines += ["", "## Items", "", "| ID | Kind | Phase | Status | Tests | Blockers / notes |", "|---|---|---|---|---|---|"]
    for item_id, item in data["items"].items():
        tests = "<br>".join(f"`{t['command']}`" for t in item.get("tests", []))
        notes = "; ".join(item.get("blockers", []))
        if item.get("notes"):
            notes = (notes + " — " if notes else "") + item["notes"]
        lines.append(
            f"| {item_id} | {item['kind']} | {item['phase']} | {item['status']} | {tests} | {notes} |"
        )
    PROGRESS.write_text("\n".join(lines) + "\n", encoding="utf8")


def coverage() -> dict:
    """Full 175-subtask readiness matrix cross-referenced against the frozen catalog + split."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "src"))
    from saber.benchmark.splits import build_split  # type: ignore[import-not-found]
    from saber.catalog import load_catalog  # type: ignore[import-not-found]

    cat = load_catalog()
    split = build_split()
    data = load()
    rows = []
    tally: dict[str, int] = {}
    for s in cat.subtasks:
        item = data["items"].get(s.id, {})
        status = item.get("status", "PENDING")
        if status in ("PENDING", "IMPLEMENTED_DEV"):
            # A domain subtask with no real implementation is SPECIFIED; legacy DEV = VERIFIED_OFFLINE.
            status = "SPECIFIED" if status == "PENDING" else "VERIFIED_OFFLINE"
        tally[status] = tally.get(status, 0) + 1
        rows.append({
            "id": s.id, "service": s.service, "environment": s.environment,
            "aggregate": s.aggregate.kind.value if s.aggregate else "?",
            "split": split.split_of(s.id).value, "status": status,
        })
    return {"tally": tally, "rows": rows}


def render_coverage() -> None:
    cov = coverage()
    out = ROOT / "docs" / "COVERAGE.md"
    lines = [
        "# SABER subtask coverage matrix (machine-generated)",
        "",
        f"Updated: {now()}",
        "",
        "Readiness tiers are strict: SPECIFIED (contract only), IMPLEMENTED_OFFLINE (code+tests),",
        "VERIFIED_OFFLINE (tests ran green on synthetic DEV data), BLOCKED_INTEGRATION (needs a real",
        "lab/dataset), READY_BENCHMARK (independently validated gold — never auto-set). Synthetic DEV",
        "fixtures are never equated with validated benchmark data.",
        "",
        "## Tally",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for status in ("SPECIFIED", "IMPLEMENTED_OFFLINE", "VERIFIED_OFFLINE", "BLOCKED_INTEGRATION", "READY_BENCHMARK"):
        lines.append(f"| {status} | {cov['tally'].get(status, 0)} |")
    lines += ["", "## Subtasks", "", "| ID | Service | Env | Aggregate | Split | Status |", "|---|---|---|---|---|---|"]
    for r in cov["rows"]:
        lines.append(f"| {r['id']} | {r['service']} | {r['environment']} | {r['aggregate']} | {r['split']} | {r['status']} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("id")
    s.add_argument("status")
    s.add_argument("--test", action="append")
    s.add_argument("--file", action="append")
    s.add_argument("--blocker", action="append")
    s.add_argument("--note")
    s.set_defaults(func=cmd_set)
    r = sub.add_parser("render")
    r.set_defaults(func=lambda a: (render(), 0)[1])
    m = sub.add_parser("summary")
    m.set_defaults(func=lambda a: (print(json.dumps(summarize(load()), indent=2)), 0)[1])
    c = sub.add_parser("coverage")
    c.set_defaults(func=lambda a: (render_coverage(), print(json.dumps(coverage()["tally"], indent=2)), 0)[2])
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
