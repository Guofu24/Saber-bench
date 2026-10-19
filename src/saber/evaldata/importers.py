"""Importers + validators for genuine external security data.

Each importer normalizes a specific real-world format into plain record dicts and reports validation
issues; it never executes the data. Formats:

* ``event_log`` — Windows/Sysmon or generic event JSON (array or JSON-lines).
* ``network_capture`` — Zeek ``conn.log`` (TSV) or JSON flows. Raw ``.pcap`` is reported as needing
  an optional dependency (dpkt/scapy) rather than silently skipped.
* ``host_artifact`` — autoruns/registry exports as JSON or CSV.
* ``detection_test`` — Sigma rule YAML or Atomic Red Team test YAML (detection-test corpora).

The dispatcher :func:`import_dataset` attaches a :class:`ProvenanceRecord` (checksum, size, tier,
lineage keys). Reading downloaded artifacts stays pure-data (json/csv/yaml), no import side effects.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from saber.evaldata.contamination import lineage_key
from saber.evaldata.provenance import DataSource, LabelTier, ProvenanceRecord, sha256_file

_TS_FIELDS = ("timestamp", "ts", "@timestamp", "EventTime", "UtcTime", "time")


@dataclass
class ImportResult:
    records: list[dict[str, Any]]
    provenance: ProvenanceRecord
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.provenance.validated and not self.issues


def _load_json_or_lines(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            # some datasets wrap events under a key
            for key in ("events", "data", "records", "hits"):
                v = obj.get(key)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
            return [obj]
    except json.JSONDecodeError:
        pass
    # JSON-lines fallback
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def _import_event_log(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows = _load_json_or_lines(path)
    issues: list[str] = []
    norm: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        ts = next((r[f] for f in _TS_FIELDS if f in r), None)
        if ts is None:
            issues.append(f"event {i}: no timestamp field {_TS_FIELDS}")
        norm.append(
            {
                "ts": ts,
                "host": r.get("Hostname") or r.get("host") or r.get("Computer"),
                "channel": r.get("Channel") or r.get("source") or r.get("SourceName"),
                "event_id": r.get("EventID") or r.get("event_id") or r.get("id"),
                "raw": r,
            }
        )
    if not norm:
        issues.append("no event records parsed")
    return norm, issues


def _import_network(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if path.suffix.lower() in (".pcap", ".pcapng"):
        return [], [
            f"{path.name}: raw pcap needs an optional parser (dpkt/scapy) not installed in the "
            "venv; provide a Zeek conn.log (TSV) or JSON flow export instead, or add the dep"
        ]
    text = path.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    norm: list[dict[str, Any]] = []
    first_line = text.splitlines()[0] if text.strip() else ""
    is_zeek_tsv = first_line.startswith("#") or "\t" in first_line
    if is_zeek_tsv:
        # Zeek TSV conn.log: header lines start with '#fields'
        fields: list[str] = []
        for line in text.splitlines():
            if line.startswith("#fields"):
                fields = line.split("\t")[1:]
                continue
            if line.startswith("#") or not line.strip():
                continue
            vals = line.split("\t")
            row = dict(zip(fields, vals, strict=False)) if fields else {"line": line}
            norm.append(
                {
                    "ts": row.get("ts"),
                    "src": row.get("id.orig_h"),
                    "dst": row.get("id.resp_h"),
                    "proto": row.get("proto"),
                    "raw": row,
                }
            )
        if not fields:
            issues.append("zeek conn.log: no #fields header")
    else:
        rows = _load_json_or_lines(path)
        for r in rows:
            norm.append(
                {
                    "ts": r.get("ts") or r.get("timestamp"),
                    "src": r.get("src") or r.get("src_ip") or r.get("id.orig_h"),
                    "dst": r.get("dst") or r.get("dst_ip") or r.get("id.resp_h"),
                    "proto": r.get("proto") or r.get("protocol"),
                    "raw": r,
                }
            )
    if not norm:
        issues.append("no network flows parsed")
    return norm, issues


def _import_host_artifact(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    norm: list[dict[str, Any]] = []
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            for r in csv.DictReader(fh):
                norm.append(_norm_artifact(r))
    else:
        for r in _load_json_or_lines(path):
            norm.append(_norm_artifact(r))
    if not norm:
        issues.append("no host-artifact entries parsed")
    return norm, issues


def _norm_artifact(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": r.get("type") or r.get("Category") or r.get("entry_type"),
        "location": r.get("location") or r.get("Location") or r.get("path") or r.get("Key"),
        "signer": r.get("signer") or r.get("Signer") or r.get("Publisher"),
        "points_to": r.get("points_to")
        or r.get("ImagePath")
        or r.get("command")
        or r.get("Target"),
        "raw": r,
    }


def _import_detection_test(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    norm: list[dict[str, Any]] = []
    try:
        docs = [
            d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if isinstance(d, dict)
        ]
    except yaml.YAMLError as exc:
        return [], [f"{path.name}: YAML parse error: {exc}"]
    for d in docs:
        if "detection" in d and "logsource" in d:  # Sigma rule
            tags = [t for t in (d.get("tags") or []) if isinstance(t, str)]
            techniques = sorted(
                {
                    m.group(0).upper()
                    for tag in tags
                    for m in [re.search(r"t\d{4}(?:\.\d{3})?", tag.lower())]
                    if m
                }
            )
            norm.append(
                {
                    "corpus": "sigma",
                    "title": d.get("title"),
                    "rule_id": d.get("id"),
                    "logsource": d.get("logsource"),
                    "detection": json.dumps(d.get("detection"), sort_keys=True),
                    "techniques": techniques,
                    "level": d.get("level"),
                    "raw": d,
                }
            )
        elif "atomic_tests" in d or "attack_technique" in d:  # Atomic Red Team
            tech = d.get("attack_technique")
            for t in d.get("atomic_tests") or []:
                if not isinstance(t, dict):
                    continue
                norm.append(
                    {
                        "corpus": "atomic_red_team",
                        "title": t.get("name"),
                        "techniques": [tech] if isinstance(tech, str) else [],
                        "executor": (t.get("executor") or {}).get("name"),
                        "raw": t,
                    }
                )
        else:
            issues.append("YAML doc is neither a Sigma rule nor an Atomic test")
    if not norm:
        issues.append("no detection-test entries parsed")
    return norm, issues


_IMPORTERS = {
    "event_log": _import_event_log,
    "network_capture": _import_network,
    "host_artifact": _import_host_artifact,
    "detection_test": _import_detection_test,
}


def import_dataset(
    path: str | Path,
    *,
    source: DataSource,
    label_tier: LabelTier,
    retrieved_at: datetime | None = None,
) -> ImportResult:
    """Import + validate one artifact, attaching provenance (checksum, tier, lineage keys)."""
    p = Path(path)
    importer = _IMPORTERS.get(source.kind)
    if importer is None:
        raise ValueError(f"unknown dataset kind: {source.kind!r}")
    if not p.exists():
        raise FileNotFoundError(p)
    records, issues = importer(p)
    digest, size = sha256_file(p)
    lineages = sorted({lineage_key(r) for r in records}) if records else []
    prov = ProvenanceRecord(
        source=source,
        local_path=str(p),
        sha256=digest,
        size_bytes=size,
        retrieved_at=(retrieved_at or datetime.now(UTC)),
        label_tier=label_tier,
        record_count=len(records),
        validated=(len(records) > 0 and not issues),
        validation_detail=("; ".join(issues) if issues else f"{len(records)} records validated"),
        lineage_keys=lineages,
    )
    return ImportResult(records=records, provenance=prov, issues=issues)
