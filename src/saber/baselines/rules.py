"""Deterministic "rules" baseline: a naive first-pass heuristic per gold pilot.

Each heuristic is what a non-expert analyst's first rule would look like — it uses ONLY
the public artifact (never the sealed truth) and is deliberately simple so the pilot's
hard negatives trip it (false positives) or its recall traps catch it (false negatives).
This is the discrimination FLOOR against which the oracle and the LLM are compared; it
is explicitly NOT a reference solution.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from saber.gold.base import GoldEpisode

# IOC types for the HUNT extraction pilot (mirrors the pilot's own tuple).
_IOC_TYPES = ("ipv4", "domain", "url", "sha256", "email", "cve")
_NAIVE_IPV4 = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
# Markers a naive "contains a scary API" triage would flag as malicious.
_SCARY_API = ("eval", "base64", "upx", "pack", "powershell", "-enc")


def _t1112(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: always call it a true positive; copy the observable rule + host.
    alert = ep.public_inputs["alert"]
    return {
        "verdict": "TP",
        "triggering_rule": alert.get("rule_name", ""),
        "affected_asset": alert.get("host", ""),
    }


def _t1348(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: treat every admin-tool use as an attack (ignores the whitelist/scope).
    return {"labels": {a["id"]: "attack" for a in ep.public_inputs["activities"]}}


def _t1387(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: trust the alert (TP) and claim the whole payload matched.
    length = int(ep.public_inputs["payload"].get("length", 0))
    return {"verdict": "TP", "payload_offset": {"start": 0, "end": length}}


def _t0020(_ep: GoldEpisode) -> dict[str, Any]:
    # Naive: match any SQL *word* (trips on benign q=select, SQL_union page, drop-shipping).
    return {
        "rule": {
            "engine": "regex",
            "pattern": r"select|union|drop|insert|or|sleep",
            "ignore_case": True,
        }
    }


def _t1406(_ep: GoldEpisode) -> dict[str, Any]:
    # Naive: match the shared "cfg=" prefix (also matches the SynthBackup near-miss).
    return {
        "rule": {
            "name": "naive_cfg",
            "strings": {"$a": {"kind": "text", "value": "cfg=", "nocase": False}},
            "condition": "$a",
        }
    }


def _t1111(_ep: GoldEpisode) -> dict[str, Any]:
    # Naive: suppress on raw file-count (also drops the ransomware TPs) + wrong cause.
    return {
        "filter": {"all_of": [{"field": "files_read", "op": "gt", "value": 1000}]},
        "fp_cause": "data_quality",
    }


def _t2013(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: grab only non-defanged IPv4 (misses defanged malicious IOCs, includes benign ones).
    text = "\n".join(ep.public_inputs["log"]["lines"])
    ips = sorted(set(_NAIVE_IPV4.findall(text)))
    ioc: dict[str, list[str]] = {t: [] for t in _IOC_TYPES}
    ioc["ipv4"] = ips
    return {"ioc": ioc}


def _t1102(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: flag only hosts with a LIVE connection (misses the past-only-trace host).
    hosts = ep.public_inputs["extract"]["hosts"]
    live = [h["host"] for h in hosts if h.get("connections")]
    return {"compromised": sorted(live)}


def _t0167(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: "contains a scary API ⇒ malicious" (trips on webpack eval, signed packers).
    verdicts: dict[str, str] = {}
    for f in ep.public_inputs["files"]:
        blob = " ".join(str(s) for s in f.get("strings", [])).lower()
        verdicts[f["name"]] = "malicious" if any(k in blob for k in _SCARY_API) else "benign"
    return {"verdicts": verdicts}


def _t0173(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: submit events in the given (shuffled) order using their LOCAL time strings
    # verbatim (no UTC conversion) — fails both ordering and normalisation.
    events = ep.public_inputs["log"]["events"]
    order = [e["id"] for e in events]
    times = [str(e.get("local_time", "")) for e in events]
    return {"event_order": order, "utc_times": times}


def _t0397(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: flag every entry whose location is a "classic" persistence type, ignoring the
    # signer (trips on signed OneDrive Run keys, GoogleUpdate tasks, SysMon-style WMI).
    classic = {"run_key", "scheduled_task", "wmi"}
    entries = [
        {"location": e["location"], "type": e["type"]}
        for e in ep.public_inputs["autoruns"]["entries"]
        if e.get("type") in classic
    ]
    return {"entries": entries}


def _t1324(ep: GoldEpisode) -> dict[str, Any]:
    # Naive: keep the given (shuffled) order and give no preservation methods.
    return {
        "collection_order": list(ep.public_inputs["evidence_types"]),
        "preservation": {},
    }


_DISPATCH = {
    "T1112.002": _t1112,
    "T1348.002": _t1348,
    "T1387.002": _t1387,
    "T0020.001": _t0020,
    "T1406.001": _t1406,
    "T1111.002": _t1111,
    "T2013.001": _t2013,
    "T1102.002": _t1102,
    "T0167.002": _t0167,
    "T0173.002": _t0173,
    "T0397.002": _t0397,
    "T1324.002": _t1324,
}


def naive_answer(subtask_id: str, episode: GoldEpisode) -> dict[str, Any]:
    """Return the naive rules-baseline answer for a gold pilot episode (public inputs only)."""
    try:
        fn = _DISPATCH[subtask_id]
    except KeyError as exc:
        raise KeyError(f"no rules baseline for {subtask_id}") from exc
    return fn(episode)
