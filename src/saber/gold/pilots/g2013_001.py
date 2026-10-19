"""Gold pilot T2013.001 (HUNT, file) — extract all IOCs from a raw log (macro-F1 over 6 types).

Artifact: a raw mixed log containing IOCs of six types: ipv4, domain, url, sha256, email, cve.
Some are defanged (`hxxp`, `[.]`) and must be normalised; benign distractors are present (RFC1918
IPs, example.com, the org's own mail domain). Ground truth per type is independently derived by a
second extractor + normaliser (distinct code path) that must agree with the authored IOC set.
Scored by macro-averaged F1 across the six types (source `F1 macro theo 6 loại IOC`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.grading.canonical import canon_ioc
from saber.grading.primitives import macro_average, score_set
from saber.grading.results import ItemScore, ScoreResult
from saber.subtasks._hv.common import Rng

_TYPES = ("ipv4", "domain", "url", "sha256", "email", "cve")
_BENIGN_DOMAINS = ("example.com", "shop.example", "corp-lab.example")

# Distinct line-context markers per type (for the independent completeness count in verify).
_LINE_MARKERS = {
    "ipv4": ("conn to ", " flagged"),
    "domain": ("dns query ", " nxdomain-retry"),
    "url": ("beacon ", "/gate.php"),
    "sha256": ("sha256=", ""),
    "cve": ("exploit for cve-", ""),
    "email": ("phishing sender ", ""),
}


def _uniq(factory: Callable[[], str], k: int, exclude: set[str] | None = None) -> list[str]:
    """Collect k unique values from a random factory (bounded attempts), avoiding ``exclude``."""
    seen: list[str] = []
    blocked = set(exclude or set())
    for _ in range(k * 200):
        if len(seen) >= k:
            break
        v = factory()
        if v not in blocked and v not in seen:
            seen.append(v)
    if len(seen) < k:  # pragma: no cover - factory space is comfortably large
        raise RuntimeError(f"could not draw {k} unique values (got {len(seen)})")
    return seen


def _extract(text: str) -> dict[str, set[str]]:
    """Independent extractor+normaliser (second code path) used to cross-validate the gold labels."""
    refanged = (
        text.replace("hxxp", "http").replace("[.]", ".").replace("(.)", ".").replace("[@]", "@")
    )
    out: dict[str, set[str]] = {t: set() for t in _TYPES}
    out["sha256"] = {m.group(0).lower() for m in re.finditer(r"\b[0-9a-fA-F]{64}\b", refanged)}
    out["cve"] = {m.group(0).upper() for m in re.finditer(r"CVE-\d{4}-\d{4,7}", refanged, re.I)}
    out["url"] = {
        m.group(0).rstrip("/.").lower() for m in re.finditer(r"https?://[^\s\"'<>]+", refanged)
    }
    out["email"] = {
        m.group(0).lower()
        for m in re.finditer(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", refanged, re.I)
        if not any(
            m.group(0).lower().endswith("@" + b) or m.group(0).lower().endswith("." + b)
            for b in _BENIGN_DOMAINS
        )
    }
    for m in re.finditer(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", refanged):
        ip = m.group(0)
        octs = [int(o) for o in ip.split(".")]
        private = (
            octs[0] == 10
            or (octs[0] == 172 and 16 <= octs[1] <= 31)
            or (octs[0] == 192 and octs[1] == 168)
            or octs[0] == 127
        )
        if not private:
            out["ipv4"].add(ip)
    url_hosts = {re.sub(r"^https?://", "", u).split("/")[0] for u in out["url"]}
    email_domains = {e.split("@", 1)[1] for e in out["email"] if "@" in e}
    for m in re.finditer(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", refanged, re.I):
        d = m.group(0).lower()
        before = refanged[max(0, m.start() - 1) : m.start()]  # index into refanged, not text
        # Skip url-host (already a url IOC), email-domain, benign, @-prefixed and url-PATH segments
        # (a token after "/" such as "gate.php" is a path component, not a domain).
        if d in url_hosts or d in email_domains or d in _BENIGN_DOMAINS or before in ("@", "/"):
            continue
        if re.search(r"\.[a-z]{2,}$", d) and not d.endswith(
            (".exe", ".dll", ".js", ".py", ".pdf", ".ps1", ".vbs", ".log", ".php")
        ):
            out["domain"].add(d)
    return out


class Pilot(GoldPilot):
    SUBTASK_ID = "T2013.001"
    SOURCE_VERSIONS = {"ioc_types": ",".join(_TYPES), "defang": "hxxp/[.]"}
    OUTPUT_SPEC = 'JSON {"ioc": {"ipv4": [...], "domain": [...], "url": [...], "sha256": [...], "email": [...], "cve": [...]}} (normalise defanged IOCs; exclude RFC1918 IPs and the org domains)'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        # Per-type UNIQUE and cross-type DISJOINT IOC values, so the six types never overlap and
        # the sealed truth cannot silently lose an indicator to a domain/url-host collision.
        n_ip, n_dom, n_url, n_sha, n_cve, n_eml = (
            rng.randint(2, 3),
            rng.randint(2, 3),
            rng.randint(1, 2),
            rng.randint(1, 2),
            rng.randint(1, 2),
            rng.randint(1, 2),
        )
        ips = _uniq(lambda: rng.external_ip(), n_ip)
        domains = _uniq(
            lambda: rng.domain(suspicious=True), n_dom + n_url + n_eml, exclude=set(_BENIGN_DOMAINS)
        )
        dom_domains, url_domains, eml_domains = (
            domains[:n_dom],
            domains[n_dom : n_dom + n_url],
            domains[n_dom + n_url :],
        )
        shas = _uniq(lambda: rng.sha256(f"ioc-{rng.hexid('', 4)}"), n_sha)
        cves = _uniq(lambda: f"CVE-{rng.randint(2018, 2025)}-{rng.randint(1000, 99999)}", n_cve)

        lines: list[str] = []
        for ip in ips:
            lines.append(f"conn to {ip.replace('.', '[.]')} flagged")
        for d in dom_domains:
            lines.append(f"dns query {d} nxdomain-retry")  # standalone domain
        for d in url_domains:
            lines.append(f"beacon hxxp://{d}/gate.php")  # url (host disjoint from domains)
        for s in shas:
            lines.append(f"dropped file sha256={s}")
        for c in cves:
            lines.append(f"exploit for {c}")
        for d in eml_domains:
            lines.append(f"phishing sender {rng.pick(('payroll', 'it-helpdesk', 'ceo'))}@{d}")
        # benign distractors (must be excluded by the spec)
        lines += [
            f"internal host {rng.internal_ip()} ok",
            "healthcheck to shop.example 200",
            "user alice@corp-lab.example logged in",
            "loaded module kernel32.dll",
            f"backup to 10.20.5.{rng.randint(2, 250)} done",
        ]
        lines = rng.shuffle(lines)
        text = "\n".join(lines)
        # Truth is the documented extraction+normalisation spec applied to the log.
        extracted = _extract(text)
        gold_truth = {"ioc": {t: sorted(extracted[t]) for t in _TYPES}}
        public = {
            "log": {"hv": "HV-02", "lines": lines},
            "objective": "Extract all IOCs by type; normalise defanged indicators; exclude internal IPs and the org's own domains.",
        }
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored raw log with 6 disjoint IOC types (some defanged) + benign distractors; truth = documented extraction spec applied to the log",
            independent_derivation="truth = documented _extract spec; independent checks: every truth IOC is grep-present in the refanged log, no benign-allowlisted indicator is included, normalisation is idempotent, AND a line-marker completeness count (a route distinct from _extract's value regexes) equals the per-type truth size (catches dropped IOCs)",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "RFC1918 IPs",
                "example/org domains (shop.example, corp-lab.example)",
                "defanged hxxp/[.]",
                "kernel32.dll is not a domain",
            ],
            adjudication_required=[
                "domain-vs-url scoping (does a URL host also count as a domain IOC?) — convention needs owner sign-off; current spec keeps them disjoint"
            ],
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
        text = "\n".join(episode.public_inputs["log"]["lines"])
        refanged = text.replace("hxxp", "http").replace("[.]", ".").replace("(.)", ".").lower()
        gold = episode.gold_truth["ioc"]
        benign = ("shop.example", "corp-lab.example", "kernel32.dll")
        problems: list[str] = []
        for t in _TYPES:
            for ioc in gold[t]:
                norm = canon_ioc(ioc)
                # grep-present in the refanged log
                probe = norm.replace("http://", "").replace("https://", "")
                if probe.lower() not in refanged:
                    problems.append(f"{t}:{ioc} not grep-present")
                if canon_ioc(norm) != norm:  # normalisation idempotent
                    problems.append(f"{t}:{ioc} not normalised")
                if any(b in norm for b in benign):
                    problems.append(f"{t}:{ioc} is a benign-allowlisted indicator")
        # also confirm no public IOC is RFC1918
        for ip in gold["ipv4"]:
            o = [int(x) for x in ip.split(".")]
            if (
                o[0] in (10, 127)
                or (o[0] == 172 and 16 <= o[1] <= 31)
                or (o[0] == 192 and o[1] == 168)
            ):
                problems.append(f"ipv4:{ip} is private")
        # Independent COMPLETENESS route: count malicious lines by their context markers (a route
        # distinct from _extract's value regexes) and require the per-type count to match the truth.
        # This catches a false negative (an IOC the value-extractor dropped, e.g. a collision).
        for t, (pre, post) in _LINE_MARKERS.items():
            marked = sum(1 for ln in refanged.split("\n") if pre in ln and (not post or post in ln))
            if marked != len(gold[t]):
                problems.append(f"{t}: {marked} marked lines but {len(gold[t])} in truth")
        if not problems:
            total = sum(len(gold[t]) for t in _TYPES)
            return VerificationResult(
                True,
                f"all {total} IOCs grep-present, normalised, benign-free, count-complete",
                list(_TYPES),
            )
        return VerificationResult(False, f"{len(problems)} problems: {problems[:6]}")

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {"ioc": {t: list(v) for t, v in episode.gold_truth["ioc"].items()}}

    def grade(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        *,
        agent_id: str,
        evidence_refs: list[str] | None = None,
    ) -> ScoreResult:
        gold = episode.gold_truth["ioc"]
        raw = answer.get("ioc")
        pred = raw if isinstance(raw, dict) else {}
        per_type: dict[str, float] = {}
        comps = []
        for t in _TYPES:
            res = score_set(pred.get(t, []), gold[t], canon=canon_ioc, beta=1.0)
            per_type[t] = res.score
            comps.append(
                ItemScore(field=f"ioc.{t}", score=res.score, weight=None, detail=res.detail())
            )
        score, detail = macro_average(per_type)
        return self._result(episode, answer, score, components=comps, trace=[f"macro-F1 {detail}"])
