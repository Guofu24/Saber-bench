"""Small scripted HTTP investigation, original preservation and Office proof. No API keys."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from saber.forensics.vault import Vault
from saber.world.agents import action, baseline
from saber.world.models import default_config
from saber.world.runtime import Runner, atomic_json
from saber.world.store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    original = root / "synthetic-access.log"
    original.write_text(
        '192.0.2.8 - - [03/Nov/2026:10:00:00 +0700] "GET /portal HTTP/1.1" 200 23\n'
        '192.0.2.8 - - [03/Nov/2026:10:01:00 +0700] "GET /missing HTTP/1.1" 404 0\n'
        '192.0.2.9 - - [03/Nov/2026:10:02:00 +0700] "GET /portal HTTP/1.1" 200 12\n',
        encoding="utf-8",
    )
    with Vault(root) as vault:
        manifest = vault.import_file(
            original, "apache", "Synthetic HTTP evidence; no attack verdict"
        )
    config = default_config(1).model_copy(update={"tick_seconds": 0.01, "learning_enabled": False})
    atomic_json(root / "config.json", config.model_dump(mode="json"))

    def scripted(actor, observation, turn):
        if actor.id != "blue-dfir":
            return baseline(actor, observation, turn)
        previous = observation.get("last_result", {}).get("forensics", {})
        if turn == 0:
            return action("forensic_sources")
        if turn == 1:
            return action(
                "forensic_open",
                source_ids=[previous["sources"][0]["id"]],
                question="Does this access log prove compromise or successful response?",
            )
        if turn == 2:
            return action(
                "forensic_query", session_id=previous["id"], text="/portal", mode="timeline"
            )
        if turn == 3:
            return action(
                "forensic_record",
                session_id=previous["session_id"],
                category="observation",
                text="Two HTTP 200 requests are visible; independent host and response evidence is still missing.",
                evidence_ids=[e["id"] for e in previous["evidence"]],
            )
        if turn == 4:
            return action(
                "response_review",
                session_id=previous["session_id"],
                residual_risk="Access logs alone cannot establish exploit success or recovery.",
            )
        return action(
            "forensic_finish",
            session_id=previous["session_id"],
            disposition="partial",
            summary="Request host, identity and response telemetry; no compromise verdict from HTTP 200.",
        )

    store = Store(root)
    runner = Runner(store, config)
    try:
        with patch("saber.world.runtime.baseline", scripted):
            runner.run(ticks=6)
        result = store.get("results", "blue-dfir")
        assert result["status"] == 200 and result["forensics"]["state"] == "PARTIAL", result
        with Vault(root) as vault:
            integrity = vault.verify(manifest["id"])
            assert integrity["integrity_verified"]
            assert original.read_bytes() == vault.original(manifest["id"]).read_bytes()
        proof = {
            "passed": True,
            "scope": "scripted tools through real world HTTP; no model-quality verdict",
            "gemini_called": False,
            "source_preserved": True,
            "session_id": result["forensics"]["session_id"],
            "final_state": "PARTIAL",
            "integrity": integrity,
            "office": str(root / "office.json"),
        }
        atomic_json(root / "proof.json", proof)
        print(json.dumps(proof, indent=2))
    finally:
        runner.close()
        store.close()


if __name__ == "__main__":
    main()
