"""Gold pilot T0020.001 (CNT, file) — author a detection rule for a realistic web-access log.

Artifact: an access log whose request lines are URL-encoded (as real logs store them). The
technique to catch is SQL-injection probing in the query string. Ground truth is derived two
independent ways that must agree: (1) construction intent (each line emitted attack or benign),
and (2) an independent semantic verifier that URL-decodes the request and looks for SQL token
*combinations* (union+select, or+1=1, a quote followed by or, sleep(, drop+table, admin'--) — a
different method than the single regex a solver writes. Hard negatives: benign requests containing
one SQL *word* in a non-SQL context (`q=select+ssd`, `/wiki/SQL_union_types`, `drop-shipping`,
`coupon=SAVE1EQ1`). Scored by the source formula max(0, M'/M − N'/(N'+M')).
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.subtasks._hv.common import Rng, iso

# Canonical, inert WAF-style SQLi probe fragments (standard detection-content examples).
_SQLI = (
    "' OR '1'='1",
    "1' OR 1=1--",
    "' UNION SELECT username,password FROM users--",
    "'; DROP TABLE sessions;--",
    "1 AND SLEEP(5)",
    "admin'--",
    "' OR 1=1 LIMIT 1--",
)
_BENIGN_TRICKY = (
    "/search?q=select+ssd+drive",
    "/wiki/SQL_union_types",
    "/cart?coupon=SAVE1EQ1",
    "/docs/drop-shipping-guide",
    "/api/v1/orders?status=selected",
    "/blog/how-we-sleep-better",
)
_BENIGN_PLAIN = (
    "/",
    "/index.html",
    "/static/app.css",
    "/api/v1/users?page=2",
    "/login",
    "/products?category=laptops",
    "/cart/add?id=42",
    "/health",
    "/favicon.ico",
    "/images/logo.png",
    "/about",
    "/contact?ref=newsletter",
)


def _decode(text: str) -> str:
    return urllib.parse.unquote_plus(urllib.parse.unquote_plus(text)).lower()


def _is_sqli_semantic(request_path: str) -> bool:
    """Independent verifier: decode, then require a SQL token COMBINATION, not a single word."""
    d = _decode(request_path)
    combos = [
        bool(re.search(r"union\s+select", d)),
        bool(re.search(r"drop\s+table", d)),
        "sleep(" in d,
        bool(re.search(r"admin'\s*--", d)),
        bool(re.search(r"'\s*or\s+", d)),  # a quote followed by OR
        bool(re.search(r"\bor\s+1\s*=\s*1", d)),  # or 1=1
        bool(re.search(r"'1'\s*=\s*'1", d)),  # '1'='1
    ]
    return any(combos)


# Reference regex over the RAW (URL-encoded) line: separator-agnostic token combinations.
_SEP = r"(?:\s|%20|\+)"
_REFERENCE_PATTERN = (
    rf"union{_SEP}+select"
    rf"|drop{_SEP}+table"
    rf"|sleep(?:\(|%28)"
    rf"|admin(?:'|%27)(?:--|%2[dD]%2[dD])"
    rf"|(?:'|%27){_SEP}*or{_SEP}"
    rf"|(?:\bor|%20or){_SEP}+1{_SEP}*(?:=|%3[dD]){_SEP}*1"
    rf"|(?:'|%27)1(?:'|%27)(?:=|%3[dD])(?:'|%27)1"
)


class Pilot(GoldPilot):
    SUBTASK_ID = "T0020.001"
    SOURCE_VERSIONS = {"log_format": "access-log-url-encoded", "technique": "sql_injection_probe"}
    OUTPUT_SPEC = 'JSON {"rule": {"engine": "regex", "pattern": "<python regex matching the SQLi request lines>", "ignore_case": true}}'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        n_benign = rng.randint(20, 28)
        m = rng.randint(7, 10)
        host = rng.hostname("web")
        lines: list[str] = []
        labels: list[bool] = []
        benign_paths = list(_BENIGN_PLAIN) + list(_BENIGN_TRICKY)
        for _ in range(n_benign):
            lines.append(_fmt(rng, host, _encode_path(rng.pick(benign_paths)), 200))
            labels.append(False)
        for _ in range(m):
            payload = rng.pick(_SQLI)
            target = rng.pick(("/login", "/search", "/api/v1/orders", "/product"))
            param = rng.pick(("id", "q", "user"))
            path = f"{target}?{param}={urllib.parse.quote_plus(payload)}"
            lines.append(_fmt(rng, host, path, rng.pick((200, 403, 500))))
            labels.append(True)
        order = rng.shuffle(list(range(len(lines))))
        lines = [lines[i] for i in order]
        labels = [labels[i] for i in order]
        positives = [i for i, mal in enumerate(labels) if mal]
        public = {
            "corpus": {
                "lines": lines,
                "format": 'ISO8601 ip method url-encoded-path status "ua"',
                "note": "write a regex matching only the SQL-injection probe lines",
            },
            "objective": "Write a python regex matching the SQL-injection request lines and not the benign ones.",
        }
        gold_truth = {"positive_lines": sorted(positives), "n": len(lines), "m": len(positives)}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored URL-encoded access log; SQLi probes malicious, plain+tricky requests benign",
            independent_derivation="semantic verifier URL-decodes each request and requires a SQL token combination (not a single word); must equal the authored labels",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "q=select+ssd (search word)",
                "/wiki/SQL_union_types (page name)",
                "coupon=SAVE1EQ1 (not 1=1)",
                "drop-shipping (word)",
                "status=selected (substring)",
                "how-we-sleep-better (word, no paren)",
            ],
            adjudication_required=[],
        )
        return finalize(
            self.SUBTASK_ID,
            split,
            seed,
            public,
            gold_truth,
            prov,
            evidence_ids=[f"line-{i}" for i in range(len(lines))],
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        lines = episode.public_inputs["corpus"]["lines"]
        truth = set(episode.gold_truth["positive_lines"])
        rederived = {i for i, line in enumerate(lines) if _is_sqli_semantic(_request_path(line))}
        if rederived == truth:
            return VerificationResult(
                True, f"semantic verifier matched {len(truth)} malicious lines", ["positive_lines"]
            )
        return VerificationResult(
            False, f"mismatch: authored={sorted(truth)} semantic={sorted(rederived)}"
        )

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {"rule": {"engine": "regex", "pattern": _REFERENCE_PATTERN, "ignore_case": True}}


def _encode_path(path: str) -> str:
    if "?" not in path:
        return path
    base, query = path.split("?", 1)
    parts = []
    for pair in query.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            parts.append(f"{k}={urllib.parse.quote_plus(v)}")
        else:
            parts.append(pair)
    return base + "?" + "&".join(parts)


def _request_path(line: str) -> str:
    toks = line.split(" ")
    return toks[3] if len(toks) > 3 else line


def _fmt(rng: Rng, host: str, path: str, status: int) -> str:
    ip = rng.external_ip() if rng.chance(0.6) else rng.internal_ip()
    ua = rng.pick(("Mozilla/5.0", "curl/8.4.0", "python-requests/2.31", "sqlmap/1.7"))
    return f'{iso(rng.time())} {ip} GET {path} {status} "{ua}"'
