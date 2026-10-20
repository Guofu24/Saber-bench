"""Detector configurations (the 'agent' under test) for the SOC workflow.

A detector maps a live episode's agent-visible evidence to the set of lines it flags malicious,
plus the rule it used. It never reads the sealed truth. The conventional detectors are
deterministic per scenario; the LLM-backed detectors live in :mod:`saber.soc.llm_detectors`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from saber.grading.execsandbox import run_regex_rule

if TYPE_CHECKING:
    from saber.range.live.episode import LiveEpisode

# Standard conventional WAF SQLi regex (same family as the strong baseline; public-only).
_SQLI = (
    r"union(?:\s|%20|\+)+select|(?:or|and)(?:\s|%20|\+)+\d+(?:\s|%20|\+)*(?:=|%3[dd])"
    r"|sleep(?:\(|%28)|(?:--|%2[dd]%2[dd])|(?:'|%27)(?:\s|%20|\+)*or|'1'(?:=|%3[dd])'1|information_schema"
)
# fs: a /fs/put that uploads a WEBSHELL-named server-side script (not just any script, so an
# authorized health.php/status.aspx deployment is not flagged — the precision hard negative).
_FS_SCRIPT = (
    r"/fs/put\?name=[^&\s]*(?:shell|cmd|backdoor|c99|r57|exploit)[^&\s]*\.(?:php|aspx|jsp|cgi)"
)
_BRUTEFORCE_THRESHOLD = 3


def _matched_regex(episode: LiveEpisode, pattern: str) -> list[str]:
    res = run_regex_rule(pattern, episode.access_log_lines, ignore_case=True)
    return sorted((f"line-{i}" for i in res.matched), key=lambda s: int(s.split("-")[1]))


def _auth_threshold(episode: LiveEpisode) -> list[str]:
    """Conventional auth rule: flag 401 lines whose user exceeds the failure threshold."""
    fails: dict[str, int] = {}
    recs = []
    for ln in episode.access_log_lines:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            rec = {}
        recs.append(rec)
        if rec.get("status") == 401:
            u = (parse_qs(urlsplit(str(rec.get("target", ""))).query).get("user") or [""])[0]
            fails[u] = fails.get(u, 0) + 1
    out = []
    for i, rec in enumerate(recs):
        if rec.get("status") == 401:
            u = (parse_qs(urlsplit(str(rec.get("target", ""))).query).get("user") or [""])[0]
            if fails.get(u, 0) >= _BRUTEFORCE_THRESHOLD:
                out.append(f"line-{i}")
    return out


def conventional_detector(episode: LiveEpisode) -> dict[str, Any]:
    """Deterministic non-LLM detector; dispatches by scenario, public inputs only."""
    if episode.scenario == "web_sqli_probe":
        pat = _SQLI
        return {
            "pattern": pat,
            "ignore_case": True,
            "matched_line_ids": _matched_regex(episode, pat),
            "calls": [],
            "wall_ms": 0,
        }
    if episode.scenario == "fs_change":
        pat = _FS_SCRIPT
        return {
            "pattern": pat,
            "ignore_case": True,
            "matched_line_ids": _matched_regex(episode, pat),
            "calls": [],
            "wall_ms": 0,
        }
    if episode.scenario == "auth_bruteforce":
        return {
            "pattern": f"status==401 AND failures>={_BRUTEFORCE_THRESHOLD}/user",
            "ignore_case": True,
            "matched_line_ids": _auth_threshold(episode),
            "calls": [],
            "wall_ms": 0,
        }
    raise ValueError(f"no conventional detector for scenario {episode.scenario!r}")


def naive_detector(episode: LiveEpisode) -> dict[str, Any]:
    """Weak floor: a word-level regex (over-flags benign SQL words / any 401 / any upload)."""
    weak = {
        "web_sqli_probe": r"select|union|drop|or|sleep",
        "fs_change": r"/fs/put",
        "auth_bruteforce": r'"status": 401',
    }.get(episode.scenario, r"zzz")
    return {
        "pattern": weak,
        "ignore_case": True,
        "matched_line_ids": _matched_regex(episode, weak),
        "calls": [],
        "wall_ms": 0,
    }
