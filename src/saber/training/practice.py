"""Local practice manifests and evidence-backed operator review; no external executor."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from saber.forensics.vault import MAX_SOURCE_BYTES, Vault, display
from saber.training.catalog import TRACKS, Track

MAX_JSON_BYTES = 128 * 1024
Id = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Manifest(Strict):
    schema_version: Literal[1] = 1
    run_id: Id
    exercise: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    origin: Literal["operator-supplied", "synthetic"]
    created_at: datetime
    source_url: str = Field(max_length=500)
    track: Track
    assisted: bool = False
    live_execution: Literal[False] = False
    benchmark_ready: Literal[False] = False

    @field_validator("source_url")
    @classmethod
    def public_htb_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not (
                parsed.hostname == "hackthebox.com" or parsed.hostname.endswith(".hackthebox.com")
            )
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.query
            or parsed.fragment
            or any(c.isspace() or ord(c) < 32 or c == "\\" for c in value)
        ):
            raise ValueError(
                "Use a public HTTPS HTB content URL without credentials/query/fragment"
            )
        return value


class Attachment(Strict):
    schema_version: Literal[1] = 1
    run_id: Id
    manifest_sha256: Digest
    source_id: Id
    sha256: Digest
    rights_note: str = Field(min_length=1, max_length=1000)
    conversion_note: str = Field(min_length=1, max_length=1000)


class Judgment(Strict):
    criterion: str = Field(min_length=1, max_length=80)
    verdict: Literal["unreviewed", "supported", "contradicted", "inconclusive"] = "unreviewed"
    rationale: str = Field(default="", max_length=2000)
    evidence_ids: list[Annotated[int, Field(strict=True, ge=1, le=9223372036854775807)]] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def substantiated(self) -> Judgment:
        if self.verdict != "unreviewed" and not self.rationale:
            raise ValueError("Explain every reviewed criterion")
        if self.verdict in {"supported", "contradicted"} and not self.evidence_ids:
            raise ValueError("Support the judgment with record IDs")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Duplicate evidence IDs")
        return self


class Review(Strict):
    schema_version: Literal[1] = 1
    run_id: Id
    manifest_sha256: Digest
    reviewer: str = Field(min_length=1, max_length=100)
    criteria: list[Judgment] = Field(min_length=1, max_length=32)


def canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


def digest(manifest: Manifest) -> str:
    return hashlib.sha256(canonical(manifest.model_dump(mode="json"))).hexdigest()


def read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular JSON file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON exceeds the 128 KiB limit")
    return json.loads(raw)


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write("\n")


def load_manifest(root: Path) -> Manifest:
    if root.is_symlink() or (root / "world").is_symlink():
        raise ValueError("Practice directory cannot be a symlink")
    manifest = Manifest.model_validate(read_json(root / "practice.json"))
    criteria = [c.id for c in manifest.track.criteria]
    if not criteria or len(criteria) > 32 or len(set(criteria)) != len(criteria):
        raise ValueError("Invalid pinned rubric")
    return manifest


def initialize(
    root: Path,
    track_id: str,
    exercise: str,
    source_url: str | None = None,
    *,
    synthetic: bool = False,
    assisted: bool = False,
) -> Manifest:
    selected = TRACKS[track_id]
    manifest = Manifest(
        run_id=uuid.uuid4().hex,
        exercise=exercise,
        origin="synthetic" if synthetic else "operator-supplied",
        created_at=datetime.now(UTC),
        source_url=source_url or selected.source_url,
        track=selected,
        assisted=assisted,
    )
    # A new directory prevents accidentally mixing exercises or overwriting evidence.
    root.mkdir(parents=True, exist_ok=False)
    write_new(root / "practice.json", manifest.model_dump(mode="json"))
    (root / "attachments").mkdir()
    write_new(
        root / "review-template.json",
        {
            "schema_version": 1,
            "run_id": manifest.run_id,
            "manifest_sha256": digest(manifest),
            "reviewer": "",
            "criteria": [Judgment(criterion=c.id).model_dump() for c in selected.criteria],
        },
    )
    brief = (
        f"# {selected.title}\n\nExercise: {exercise}\n\n"
        f"Roles: {', '.join(selected.roles)}.\n\n"
        "SABER-authored practice rubric; no official HTB questions, answers or access included.\n"
        "Use only runtime-provided tools. This brief does not grant an external executor.\n"
        "Consult the external-practice topic in your pinned skill index when available.\n\n"
        "## Deliverables\n\n"
        + "\n".join(f"- **{c.id}:** {c.requirement}" for c in selected.criteria)
        + "\n\nCite record IDs and document uncertainty. Do not read the operator review.\n"
    )
    (root / "brief.md").write_text(brief, encoding="utf-8")
    return manifest


def attach(
    root: Path,
    source: Path,
    fmt: str,
    label: str,
    rights_note: str,
    conversion_note: str,
    offset: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(root)
    folder = root / "attachments"
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Invalid attachment directory")
    if len(list(folder.iterdir())) >= 100:
        raise ValueError("Attachment limit reached")
    # Validate metadata before touching the source or vault.
    receipt = Attachment(
        run_id=manifest.run_id,
        manifest_sha256=digest(manifest),
        source_id=uuid.uuid4().hex,
        sha256="0" * 64,
        rights_note=rights_note,
        conversion_note=conversion_note,
    )
    pending = folder / (uuid.uuid4().hex + ".json")
    write_new(pending, {"state": "incomplete", "run_id": manifest.run_id})
    # The incomplete receipt remains visible on failure; no successful report can hide it.
    with Vault(root / "world") as vault:
        imported = vault.import_file(source, fmt, label, offset)
    receipt.source_id = imported["id"]
    receipt.sha256 = imported["sha256"]
    temporary = pending.with_suffix(".tmp")
    write_new(temporary, receipt.model_dump(mode="json"))
    temporary.replace(pending)
    return {
        "source": imported,
        "receipt": pending.name,
        "semantic_verification": False,
        "benchmark_ready": False,
    }


def report(root: Path, review_path: Path | None = None) -> dict[str, Any]:
    manifest = load_manifest(root)
    manifest_hash = digest(manifest)
    folder = root / "attachments"
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Invalid attachment directory")
    files = list(folder.iterdir())
    if len(files) > 100:
        raise ValueError("Attachment limit exceeded")
    issues: list[str] = []
    sources: list[dict[str, Any]] = []
    registered: dict[str, Attachment] = {}
    for path in sorted(files):
        try:
            receipt = Attachment.model_validate(read_json(path))
            if receipt.run_id != manifest.run_id or receipt.manifest_sha256 != manifest_hash:
                raise ValueError("Receipt belongs to another manifest")
            if receipt.source_id in registered:
                raise ValueError("Duplicate attachment")
            registered[receipt.source_id] = receipt
        except (ValueError, OSError):
            issues.append("Invalid or incomplete attachment receipt")

    review = Review.model_validate(read_json(review_path)) if review_path else None
    required = {c.id for c in manifest.track.criteria}
    if review:
        if review.run_id != manifest.run_id or review.manifest_sha256 != manifest_hash:
            raise ValueError("Review belongs to another manifest")
        ids = [c.criterion for c in review.criteria]
        if len(set(ids)) != len(ids) or not set(ids) <= required:
            raise ValueError("Duplicate or unknown review criteria")
    citations = {eid for j in review.criteria for eid in j.evidence_ids} if review else set()
    dbpath = root / "world/forensics/index.sqlite3"
    vault_root = dbpath.parent
    source_hashes: dict[str, str] = {}
    evidence: dict[int, dict[str, Any]] = {}
    if registered or citations:
        if dbpath.is_symlink() or vault_root.is_symlink() or not dbpath.is_file():
            issues.append("Evidence vault is missing or invalid")
        else:
            db = sqlite3.connect(dbpath.resolve().as_uri() + "?mode=ro", uri=True)
            db.row_factory = sqlite3.Row
            try:
                for sid, receipt in registered.items():
                    try:
                        original = vault_root / f"{sid}.original"
                        if original.is_symlink() or original.stat().st_size > MAX_SOURCE_BYTES:
                            raise ValueError("Invalid original")
                        with original.open("rb") as stream:
                            actual = hashlib.file_digest(stream, "sha256").hexdigest()
                        row = db.execute(
                            "SELECT manifest FROM sources WHERE id=?", (sid,)
                        ).fetchone()
                        if row is None:
                            raise ValueError("Missing source metadata")
                        details = json.loads(row[0])
                        valid = receipt.sha256 == actual == details["sha256"]
                        if not valid:
                            issues.append(f"Source integrity mismatch: {sid}")
                        else:
                            source_hashes[sid] = actual
                        sources.append(
                            {
                                "id": sid,
                                "sha256": actual,
                                "integrity_verified": valid,
                                "indexed_complete": details["indexed_complete"],
                                "warnings": details["warnings"],
                                "records": details["records"],
                                "rights_note": receipt.rights_note,
                                "conversion_note": receipt.conversion_note,
                            }
                        )
                    except (ValueError, OSError, KeyError, TypeError):
                        issues.append(f"Missing or invalid source: {sid}")
                for eid in sorted(citations):
                    row = db.execute(
                        "SELECT source,offset,length,sha256 FROM records WHERE id=?", (eid,)
                    ).fetchone()
                    if row is None or row["source"] not in source_hashes:
                        issues.append(f"Citation outside verified exercise sources: {eid}")
                        continue
                    if not (row["offset"] >= 0 and 0 < row["length"] <= 131072):
                        issues.append(f"Invalid record boundary: {eid}")
                        continue
                    with (vault_root / f"{row['source']}.original").open("rb") as stream:
                        stream.seek(row["offset"])
                        raw = stream.read(row["length"])
                    if (
                        len(raw) != row["length"]
                        or hashlib.sha256(raw).hexdigest() != row["sha256"]
                    ):
                        issues.append(f"Record integrity mismatch: {eid}")
                        continue
                    evidence[eid] = {"source_id": row["source"], "sha256": row["sha256"]}
            finally:
                db.close()
    judgments = {j.criterion: j for j in review.criteria} if review else {}
    rows = [
        judgments.get(c.id, Judgment(criterion=c.id)).model_dump() for c in manifest.track.criteria
    ]
    counts = Counter(r["verdict"] for r in rows)
    status = (
        "AWAITING_REVIEW"
        if review is None
        else ("REVIEW_INCOMPLETE" if counts["unreviewed"] else "REVIEW_RECORDED")
    )
    if issues:
        status = "INTEGRITY_FAILURE"
    return dict(
        display(
            {
                "schema_version": 1,
                "run_id": manifest.run_id,
                "manifest_sha256": manifest_hash,
                "track": manifest.track.id,
                "origin": manifest.origin,
                "assisted": manifest.assisted,
                "status": status,
                "sources": sources,
                "issues": issues,
                "reviewer": review.reviewer if review else None,
                "criteria": rows,
                "verdict_counts": dict(counts),
                "verified_citations": {str(k): v for k, v in evidence.items()},
                "review_authentication": "operator-supplied identity; not authenticated",
                "semantic_verification": False,
                "live_execution": False,
                "benchmark_ready": False,
                "limitations": "Integrity checks and attributed human judgments only; no automatic correctness, live effect or HTB certification claim.",
            }
        )
    )
