"""Bounded public evidence exports. No worker capability or raw prompt leaves the controller."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

from saber.lab.events import redact
from saber.lab.transport import request
from saber.world.runtime import atomic_json
from saber.world.store import Store


def publish_actor(
    store: Store,
    actor: Any,
    collector: str,
    read_token: str,
    worker: str,
    worker_token: str,
    budget: float = 2.0,
) -> None:
    history = store.get("lab-office", actor.id, [])
    deadline = time.monotonic() + budget

    def fetch(url: str, **kwargs: Any) -> tuple[int, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ConnectionError("Office evidence refresh budget reached")
        return request(url, timeout=min(0.5, remaining), **kwargs)

    # Revisit incomplete exports: the collector can receive process events after the receipt.
    for entry in reversed(history):
        if time.monotonic() >= deadline:
            break
        if entry.get("evidence_complete"):
            continue
        try:
            status, page = fetch(
                collector + "/search",
                token=read_token,
                body={"limit": 8, "filters": [{"field": "job_id", "value": entry["job_id"]}]},
            )
            if status != 200:
                break
            ids = list(
                dict.fromkeys(
                    entry["evidence_ids"]
                    + ([e["id"] for e in page.get("events", [])] if status == 200 else [])
                )
            )[:10]
            proofs = []
            for eid in ids:
                code, proof = fetch(collector + "/evidence/" + eid, token=read_token)
                if code != 200:
                    continue
                raw = json.dumps(proof["event"], sort_keys=True, separators=(",", ":")).encode()
                if hashlib.sha256(raw).hexdigest() != proof["sha256"]:
                    continue
                proofs.append(
                    {
                        "event": redact(proof["event"]),
                        "sha256": proof["sha256"],
                        "hash_verified": True,
                        "display_redacted": True,
                    }
                )
            entry["evidence"] = proofs
            kinds = {p["event"]["kind"] for p in proofs}
            entry["evidence_complete"] = {"process.launch", "process.exit"} <= kinds and all(
                eid in {p["event"]["id"] for p in proofs} for eid in entry["evidence_ids"]
            )
        except (OSError, ValueError, ConnectionError):
            break
    screen = store.get("lab-screen", actor.id)
    latest = next(
        (e for e in reversed(history) if any(a["name"] == "browser.png" for a in e["artifacts"])),
        None,
    )
    if latest and (not screen or screen["job_id"] != latest["job_id"]):
        digest = next(a["sha256"] for a in latest["artifacts"] if a["name"] == "browser.png")
        try:
            code, result = fetch(worker + "/screens/" + actor.id + "/" + digest, token=worker_token)
            data = base64.b64decode(result.get("png", ""), validate=True)
            if (
                code == 200
                and data.startswith(b"\x89PNG\r\n\x1a\n")
                and hashlib.sha256(data).hexdigest() == digest
            ):
                screen = {
                    "job_id": latest["job_id"],
                    "tick": latest["tick"],
                    "sha256": digest,
                    "png": result["png"],
                }
                with store.transaction():
                    store.put("lab-screen", actor.id, screen)
        except (OSError, ValueError, ConnectionError):
            pass
    with store.transaction():
        store.put("lab-office", actor.id, history)
    directory = store.root / "range-office"
    directory.mkdir(exist_ok=True)
    export = {
        "schema_version": 1,
        "world_id": store.get("meta", "world_id"),
        "actor_id": actor.id,
        "through_tick": store.get("meta", "tick", 0),
        "limit": 12,
        "entries": history,
        "screen": screen,
    }
    while len(json.dumps(export).encode()) > 1_900_000 and export["entries"]:
        export["entries"] = export["entries"][1:]
    atomic_json(directory / (actor.id + ".json"), export)


def record(
    store: Store,
    actor: Any,
    tick: int,
    event_id: int,
    tool: str,
    source: str,
    job_id: str,
    result: dict[str, Any],
) -> None:
    fields = (
        "status",
        "error",
        "pid",
        "exit_code",
        "executor_host",
        "guest_work",
        "analysis_job",
        "soar_job",
        "analysis",
        "case_id",
        "verified",
        "scope",
        "matches",
        "count",
        "source",
        "next_cursor",
    )
    output = redact({k: result[k] for k in fields if k in result})
    if len(json.dumps(output).encode()) > 16_000:
        output = {
            k: result[k] for k in ("status", "pid", "exit_code", "executor_host") if k in result
        }
        output["detail_omitted"] = "Result exceeds Office preview limit; inspect SOC evidence."
    history = store.get("lab-office", actor.id, [])
    history.append(
        {
            "job_id": job_id,
            "tick": tick,
            "event_id": event_id,
            "tool": tool,
            "source": source,
            "result": output,
            "artifacts": result.get("artifacts", []),
            "evidence_ids": [
                result[k] for k in ("evidence_id", "execution_evidence") if result.get(k)
            ],
            "evidence": [],
            "evidence_complete": False,
        }
    )
    store.put("lab-office", actor.id, history[-12:])
