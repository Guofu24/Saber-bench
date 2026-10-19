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
VALID = {"PENDING", "DONE_DEV", "IMPLEMENTED_DEV", "PARTIAL", "BLOCKED_INTEGRATION", "BLOCKED"}


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
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
