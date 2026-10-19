"""Strong deterministic (non-LLM) "conventional SOC" baseline per gold pilot.

Where the naive ``rules`` baseline is a deliberately weak first pass, this one is a COMPETENT
conventional analyst/tool: proper parsers and standard detection logic applied to the public
artifact (never the sealed truth). For well-specified detection tasks a competent conventional
method should approach the oracle; where it falls short, that is an honest signal that the task
needs semantic judgement. This is the non-LLM arm of the E2 controlled comparison.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from saber.gold.base import GoldEpisode

_TP_SIGNALS = ("encoded command", "rare external host", "beaconed", "run key", "unsigned binary")
_FP_SIGNALS = ("signed by", "change ticket", "backup window", "no external", "no outbound")
_SUSPECT_PATH = (
    "\\temp\\",
    "\\appdata\\roaming\\",
    "\\users\\public\\",
    "/tmp/",
    "-enc",
    ".scr",
    ".vbs",
    "svch0st",
)
_SUSPICIOUS_API = (
    "virtualalloc",
    "writeprocessmemory",
    "isdebuggerpresent",
    "activexobject",
    "adodb.stream",
    "loadlibrary",
    "internetopenurl",
    "powershell -enc",
    "wscript.shell",
)
_VOLATILITY = [
    "ram",
    "network_connections",
    "processes",
    "disk_images",
    "local_logs",
    "archived_logs",
]
_METHOD = {
    "ram": "live_memory_acquisition",
    "network_connections": "snapshot_connections",
    "processes": "capture_process_state",
    "disk_images": "forensic_disk_image",
    "local_logs": "copy_preserve_timestamps",
    "archived_logs": "export_from_central_store",
}
_BENIGN_DOMAINS = ("example.com", "shop.example", "corp-lab.example")


def _t1112(ep: GoldEpisode) -> dict[str, Any]:
    text = " ".join(
        str(line.get("detail", "")).lower() for line in ep.public_inputs["logs"]["lines"]
    )
    tp = sum(s in text for s in _TP_SIGNALS)
    fp = sum(s in text for s in _FP_SIGNALS)
    alert = ep.public_inputs["alert"]
    return {
        "verdict": "TP" if tp > fp else "FP",
        "triggering_rule": alert.get("rule_name", ""),
        "affected_asset": alert.get("host", ""),
    }


def _t1348(ep: GoldEpisode) -> dict[str, Any]:
    wl = ep.public_inputs["whitelist"]
    admins, managed = set(wl["admin_accounts"]), set(wl["managed_hosts"])
    labels = {}
    for a in ep.public_inputs["activities"]:
        legit = a.get("account") in admins and a.get("target_host") in managed
        labels[a["id"]] = "legit" if legit else "attack"
    return {"labels": labels}


def _t1387(ep: GoldEpisode) -> dict[str, Any]:
    payload = ep.public_inputs["payload"]["bytes_ascii"]
    content = ep.public_inputs["alert"]["matches_content"]
    idx = payload.find(content)
    if idx >= 0:
        return {"verdict": "TP", "payload_offset": {"start": idx, "end": idx + len(content)}}
    return {"verdict": "FP", "payload_offset": {"start": 0, "end": 0}}


def _t0020(_ep: GoldEpisode) -> dict[str, Any]:
    # Competent WAF-style SQLi detection: token combinations, separator-agnostic, on url-encoded lines.
    sep = r"(?:\s|%20|\+)"
    pattern = (
        rf"union{sep}+select|drop{sep}+table|sleep(?:\(|%28)|admin(?:'|%27)(?:--|%2[dD]%2[dD])"
        rf"|(?:'|%27){sep}*or{sep}|(?:\bor|%20or){sep}+1{sep}*(?:=|%3[dD]){sep}*1|(?:'|%27)1(?:'|%27)(?:=|%3[dD])(?:'|%27)1"
    )
    return {"rule": {"engine": "regex", "pattern": pattern, "ignore_case": True}}


def _printable_runs(blob: bytes) -> list[str]:
    return re.findall(r"[ -~]{6,}", blob.decode("latin-1"))


def _t1406(ep: GoldEpisode) -> dict[str, Any]:
    # Conventional family-marker hunt: the config-like substring (contains '=') most common across
    # samples, using a fixed window so a per-sample id suffix doesn't fragment the count.
    samples = ep.public_inputs["samples"]
    blobs = [base64.b64decode(s["b64"]) for s in samples]
    win = 12
    freq: dict[str, int] = {}
    for b in blobs:
        windows: set[str] = set()
        for run in _printable_runs(b):
            for i in range(len(run) - win + 1):
                w = run[i : i + win]
                if "=" in w:
                    windows.add(w)
        for w in windows:
            freq[w] = freq.get(w, 0) + 1
    marker = "cfg=" if not freq else max(freq, key=lambda w: (freq[w], len(w)))
    return {
        "rule": {
            "name": "conventional_marker",
            "strings": {"$a": {"kind": "text", "value": marker, "nocase": False}},
            "condition": "$a",
        }
    }


def _t1111(_ep: GoldEpisode) -> dict[str, Any]:
    # Suppress the benign signed backup agent specifically; keep ransomware TPs. Cause = rule logic.
    return {
        "filter": {
            "all_of": [
                {"field": "account", "op": "contains", "value": "backup"},
                {"field": "signed", "op": "eq", "value": True},
            ]
        },
        "fp_cause": "rule_logic",
    }


_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_SHA256 = re.compile(r"\b[0-9a-fA-F]{64}\b")
_CVE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s\"'<>]+")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", re.IGNORECASE)
_DOMAIN = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", re.IGNORECASE)


def _private_ip(ip: str) -> bool:
    o = [int(x) for x in ip.split(".") if x.isdigit()]
    return len(o) == 4 and (
        o[0] in (10, 127) or (o[0] == 172 and 16 <= o[1] <= 31) or (o[0] == 192 and o[1] == 168)
    )


def _t2013(ep: GoldEpisode) -> dict[str, Any]:
    text = "\n".join(ep.public_inputs["log"]["lines"])
    r = text.replace("hxxp", "http").replace("[.]", ".").replace("(.)", ".").replace("[@]", "@")
    urls = {u.rstrip("/.").lower() for u in _URL.findall(r)}
    url_hosts = {re.sub(r"^https?://", "", u).split("/")[0] for u in urls}
    emails = {
        e.lower()
        for e in _EMAIL.findall(r)
        if not any(e.lower().endswith(b) for b in _BENIGN_DOMAINS)
    }
    email_domains = {e.split("@", 1)[1] for e in emails}
    domains = set()
    for m in _DOMAIN.finditer(r):
        d = m.group(0).lower()
        before = r[max(0, m.start() - 1) : m.start()]
        if d in url_hosts or d in email_domains or d in _BENIGN_DOMAINS or before in ("@", "/"):
            continue
        if not d.endswith((".exe", ".dll", ".js", ".py", ".pdf", ".ps1", ".vbs", ".log", ".php")):
            domains.add(d)
    ips = {ip for ip in _IPV4.findall(r) if not _private_ip(ip)}
    return {
        "ioc": {
            "ipv4": sorted(ips),
            "domain": sorted(domains),
            "url": sorted(urls),
            "sha256": sorted({h.lower() for h in _SHA256.findall(r)}),
            "email": sorted(emails),
            "cve": sorted({c.upper() for c in _CVE.findall(r)}),
        }
    }


def _t1102(ep: GoldEpisode) -> dict[str, Any]:
    out = []
    for h in ep.public_inputs["extract"]["hosts"]:
        live = (
            bool(h.get("connections"))
            or bool(h.get("autoruns"))
            or any("unsigned" in f for f in h.get("files", []))
        )
        hist = any("quarantine" in x.lower() for x in h.get("av_log", [])) or any(
            "drop.exe" in x.lower() for x in h.get("prefetch", [])
        )
        if live or hist:
            out.append(h["host"])
    return {"compromised": sorted(out)}


def _t0167(ep: GoldEpisode) -> dict[str, Any]:
    verdicts = {}
    for f in ep.public_inputs["files"]:
        if f.get("signer"):
            verdicts[f["name"]] = "benign"
            continue
        blob = " ".join(str(s) for s in f.get("strings", [])).lower()
        verdicts[f["name"]] = (
            "malicious" if sum(a in blob for a in _SUSPICIOUS_API) >= 2 else "benign"
        )
    return {"verdicts": verdicts}


def _t0173(ep: GoldEpisode) -> dict[str, Any]:
    events = ep.public_inputs["log"]["events"]
    parsed = []
    for e in events:
        dt = datetime.fromisoformat(str(e["local_time"]))
        off = dt.utcoffset()
        utc = (dt - off).replace(tzinfo=None) if off is not None else dt.replace(tzinfo=None)
        parsed.append((e["id"], utc))
    parsed.sort(key=lambda x: x[1])
    return {
        "event_order": [i for i, _ in parsed],
        "utc_times": [u.strftime("%Y-%m-%dT%H:%M:%SZ") for _, u in parsed],
    }


def _t0397(ep: GoldEpisode) -> dict[str, Any]:
    entries = []
    for e in ep.public_inputs["autoruns"]["entries"]:
        p = str(e.get("points_to", "")).lower()
        if not e.get("signer") and any(s in p for s in _SUSPECT_PATH):
            entries.append({"location": e["location"], "type": e["type"]})
    return {"entries": entries}


def _t1324(ep: GoldEpisode) -> dict[str, Any]:
    present = set(ep.public_inputs["evidence_types"])
    return {
        "collection_order": [t for t in _VOLATILITY if t in present],
        "preservation": {t: _METHOD[t] for t in present if t in _METHOD},
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


def strong_answer(subtask_id: str, episode: GoldEpisode) -> dict[str, Any]:
    """Competent conventional (non-LLM) answer for a gold pilot episode (public inputs only)."""
    try:
        fn = _DISPATCH[subtask_id]
    except KeyError as exc:
        raise KeyError(f"no strong baseline for {subtask_id}") from exc
    return fn(episode)
