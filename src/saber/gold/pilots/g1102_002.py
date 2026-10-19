"""Gold pilot T1102.002 (HUNT, file) — list compromised hosts incl. one with only past traces.

Artifact: a multi-host artifact extract. Each host has indicators (live malware file, autoruns,
C2 connection, OR — the hard case — only PAST traces: the dropper file is deleted, leaving an AV
quarantine log and a prefetch entry). Ground truth is independently derived from whether ANY
compromise indicator (live or historical) is present — a route distinct from the solver's — so the
past-only host must be included. Scored F2 (recall-weighted) via the existing engine scorer.
"""

from __future__ import annotations

from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.subtasks._hv.common import Rng, iso


def _host_record(rng: Rng, host: str, kind: str) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "host": host,
        "files": [],
        "autoruns": [],
        "connections": [],
        "av_log": [],
        "prefetch": [],
    }
    if kind == "clean":
        rec["files"] = [f"C:/Program Files/app{rng.randint(1, 9)}.exe (signed)"]
        rec["prefetch"] = ["CHROME.EXE-1A2B.pf", "TEAMS.EXE-3C4D.pf"]
    elif kind == "live":
        rec["files"] = [
            f"C:/Users/x/AppData/Roaming/{rng.hexid('m', 3)}.exe (unsigned, prevalence 1)"
        ]
        rec["autoruns"] = ["HKCU\\...\\Run\\updater -> the unsigned exe"]
        rec["connections"] = [f"{rng.external_ip()}:443 beacon 60s"]
    elif kind == "past_only":
        # Dropper deleted; only historical evidence remains (the hard case).
        rec["av_log"] = [
            f"{iso(rng.time(min_minutes=-10000))} QUARANTINE Trojan.Synth C:/Users/x/AppData/Roaming/drop.exe (deleted)"
        ]
        rec["prefetch"] = ["DROP.EXE-9F8E.pf (last run 6 days ago)"]
    return rec


def _is_compromised(rec: dict[str, Any]) -> bool:
    """Independent route: any live OR historical compromise indicator marks the host compromised."""
    live = (
        bool(rec.get("connections"))
        or any("unsigned" in f for f in rec.get("files", []))
        or bool(rec.get("autoruns"))
    )
    historical = any("quarantine" in x.lower() for x in rec.get("av_log", [])) or any(
        "drop.exe" in x.lower() for x in rec.get("prefetch", [])
    )
    return live or historical


class Pilot(GoldPilot):
    SUBTASK_ID = "T1102.002"
    SOURCE_VERSIONS = {"artifact": "multi-host-extract"}
    OUTPUT_SPEC = 'JSON {"compromised": ["<hostname>", ...]} listing every compromised host (include hosts with only historical traces)'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        n = rng.randint(8, 12)
        hosts = [rng.hostname("ws") for _ in range(n)]
        kinds = ["past_only"] + ["live"] * rng.randint(2, 3)
        kinds += ["clean"] * (n - len(kinds))
        kinds = rng.shuffle(kinds)
        records = [_host_record(rng, h, k) for h, k in zip(hosts, kinds, strict=True)]
        truth = [r["host"] for r in records if _is_compromised(r)]
        public = {
            "extract": {"hv": "HV-16", "hosts": records},
            "objective": "List every compromised host, including any with only historical traces (deleted file, AV log, prefetch).",
        }
        gold_truth = {"compromised": sorted(truth)}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored multi-host extract with live, clean and past-only-trace hosts",
            independent_derivation="verifier marks a host compromised on any live OR historical indicator; must equal authored compromised set",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "one host has ONLY an AV-quarantine log + prefetch (file deleted) — a recall trap for F2"
            ],
            adjudication_required=[],
        )
        return finalize(
            self.SUBTASK_ID, split, seed, public, gold_truth, prov, evidence_ids=list(hosts)
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        rederived = sorted(
            r["host"] for r in episode.public_inputs["extract"]["hosts"] if _is_compromised(r)
        )
        if rederived == episode.gold_truth["compromised"]:
            return VerificationResult(
                True, f"indicator verifier matched {len(rederived)} hosts", ["compromised"]
            )
        return VerificationResult(
            False, f"mismatch: gold={episode.gold_truth['compromised']} derived={rederived}"
        )

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {"compromised": list(episode.gold_truth["compromised"])}
