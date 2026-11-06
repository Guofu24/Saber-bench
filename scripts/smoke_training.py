"""Synthetic external-practice demo through real world HTTP; no HTB or model calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from saber.cli.main import cli
from saber.training.practice import attach, digest, initialize, report, write_new
from saber.world.agents import action
from saber.world.models import WorldConfig
from saber.world.runtime import Runner
from saber.world.store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.out.resolve()
    manifest = initialize(root, "blue-dfir", "synthetic-request-review", synthetic=True)
    original = root / "synthetic-access.log"
    original.write_text(
        '192.0.2.8 - - [05/Nov/2026:10:00:00 +0000] "GET /portal HTTP/1.1" 200 23\n'
        '192.0.2.8 - - [05/Nov/2026:10:01:00 +0000] "GET /missing HTTP/1.1" 404 0\n',
        encoding="utf-8",
    )
    imported = attach(
        root,
        original,
        "apache",
        "Synthetic access log",
        "Locally authored fixture",
        "Original UTF-8 bytes",
    )
    prepared = CliRunner().invoke(cli, ["training", "prepare-world", "--run", str(root)])
    assert prepared.exit_code == 0, prepared.output
    world = root / "world"
    config = WorldConfig.model_validate_json((world / "config.json").read_text()).model_copy(
        update={"tick_seconds": 0.01}
    )

    def scripted(actor, observation, turn):
        if actor.id != "blue-dfir":
            return action("wait")
        previous = observation.get("last_result", {}).get("forensics", {})
        if turn == 0:
            return action("consult_skill", topic="soc-orchestrator--external-practice")
        if turn == 1:
            return action("forensic_sources")
        if turn == 2:
            return action(
                "forensic_open",
                source_ids=[imported["source"]["id"]],
                question="Does this access log establish compromise?",
            )
        if turn == 3:
            return action(
                "forensic_query", session_id=previous["id"], mode="timeline", text="/portal"
            )
        if turn == 4:
            return action(
                "forensic_record",
                session_id=previous["session_id"],
                category="observation",
                text="An HTTP 200 request is visible; no host execution or authorization proof is supplied.",
                evidence_ids=[e["id"] for e in previous["evidence"]],
            )
        if turn == 5:
            return action(
                "response_review",
                session_id=previous["session_id"],
                residual_risk="Historical access logs do not establish containment or recovery.",
            )
        return action(
            "forensic_finish",
            session_id=previous["session_id"],
            disposition="partial",
            summary="Need host/identity evidence before a compromise verdict. Live response was not performed.",
        )

    store = Store(world)
    runner = Runner(store, config)
    try:
        with patch("saber.world.runtime.baseline", scripted):
            runner.run(ticks=7)
        final = store.get("results", "blue-dfir")
        assert final["status"] == 200 and final["forensics"]["state"] == "PARTIAL", final
    finally:
        runner.close()
        store.close()
    review = {
        "schema_version": 1,
        "run_id": manifest.run_id,
        "manifest_sha256": digest(manifest),
        "reviewer": "Scripted test fixture; not a human adjudication",
        "criteria": [
            {
                "criterion": c.id,
                "verdict": "inconclusive",
                "rationale": "Synthetic smoke checks wiring; it does not evaluate model competence.",
                "evidence_ids": [],
            }
            for c in manifest.track.criteria
        ],
    }
    review_path = root / "synthetic-review.json"
    write_new(review_path, review)
    result = report(root, review_path)
    assert result["status"] == "REVIEW_RECORDED" and result["sources"][0]["integrity_verified"]
    assert result["semantic_verification"] is False
    write_new(root / "report.json", result)
    proof = {
        "passed": True,
        "scope": "synthetic fixture, real HTTP tools and Office snapshot",
        "htb_contacted": False,
        "gemini_called": False,
        "model_quality_evaluated": False,
        "session_state": "PARTIAL",
        "training_report": str(root / "report.json"),
        "office": str(world / "office.json"),
    }
    write_new(root / "proof.json", proof)
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
