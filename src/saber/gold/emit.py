"""Emit the gold pilot provenance manifest + adjudication queue (reproducible, no hidden labels).

The dev-split artifacts and gold truth are written for inspection; the hidden-split *truth* is NOT
written (only its artifact hash + provenance), to keep the hidden evaluation set sealed. The pilot
builders are deterministic, so any episode is reproducible from code + seed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.catalog.loader import repo_root
from saber.gold import load_pilot, pilot_ids


def build_manifest() -> dict[str, Any]:
    rows = []
    queue: list[dict[str, Any]] = []
    for sid in pilot_ids():
        p = load_pilot(sid)
        entry: dict[str, Any] = {"subtask_id": sid, "splits": {}}
        for split in ("dev", "hidden"):
            ep = p.build(split, 1)
            v = p.independent_verify(ep)
            oracle = p.grade(ep, p.answer_from_gold(ep), agent_id="gold_oracle")
            entry["splits"][split] = {
                "episode_id": str(ep.episode_id),
                "artifact_sha256": ep.artifact_sha256,
                "independent_verification": {
                    "ok": v.ok,
                    "detail": v.detail,
                    "fields": v.cross_checked_fields,
                },
                "gold_oracle_score": round(oracle.score, 4),
            }
            if split == "dev":
                entry["provenance"] = ep.provenance.model_dump()
                for item in ep.provenance.adjudication_required:
                    queue.append({"subtask_id": sid, "item": item})
        rows.append(entry)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "label": "GOLD_PILOT_V1 — domain-faithful synthetic, independently cross-validated, NOT human-signed; not READY_BENCHMARK",
        "pilots": rows,
        "adjudication_queue_size": len(queue),
    }


def write_manifest(root: Path | None = None) -> tuple[Path, Path]:
    base = (root or repo_root()) / "gold"
    base.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    mpath = base / "MANIFEST.json"
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Gold Evaluation Pilot v1 — human adjudication queue",
        "",
        "These labels or conventions are DEV-chosen and cross-validated by an independent verifier,",
        "but still need business-owner / IR-lead sign-off before any subtask can move toward",
        "READY_BENCHMARK. Nothing here is claimed as expert-approved.",
        "",
        "| Subtask | Item needing adjudication |",
        "|---|---|",
    ]
    for sid in pilot_ids():
        p = load_pilot(sid)
        ep = p.build("dev", 1)
        for item in ep.provenance.adjudication_required:
            lines.append(f"| {sid} | {item} |")
    if lines[-1].endswith("|---|"):
        lines.append("| (none) | all pilot conventions were independently verifiable |")
    qpath = base / "ADJUDICATION_QUEUE.md"
    qpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mpath, qpath
