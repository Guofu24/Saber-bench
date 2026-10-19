"""Gold pilot T0397.002 (IR, file) — classify malicious persistence entries by location and type.

Artifact: a realistic autoruns/registry export mixing benign OS/vendor persistence with attacker
persistence across run_key / service / scheduled_task / wmi / startup / systemd. Ground truth
(which entries are malicious, and their type) is independently derived from signer + path + target
reputation — a route distinct from the solver's. Hard negatives: legitimate Run keys (OneDrive),
signed services (Spooler), vendor scheduled tasks (GoogleUpdate). An entry matched on location but
mis-typed earns half credit (source F1 partial), via the existing bespoke scorer.
"""

from __future__ import annotations

from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.subtasks._hv.common import Rng, iso

# (type, location, signer/None, points-to)
_Entry = tuple[str, str, "str | None", str]
_BENIGN: tuple[_Entry, ...] = (
    (
        "run_key",
        r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run\OneDrive",
        "Microsoft",
        r"C:\Program Files\OneDrive\OneDrive.exe",
    ),
    (
        "service",
        r"HKLM\System\CurrentControlSet\Services\Spooler",
        "Microsoft",
        r"C:\Windows\System32\spoolsv.exe",
    ),
    (
        "scheduled_task",
        r"\Microsoft\Windows\UpdateOrchestrator\Refresh",
        "Microsoft",
        r"C:\Windows\System32\usoclient.exe",
    ),
    (
        "scheduled_task",
        r"\GoogleUpdateTaskMachineCore",
        "Google LLC",
        r"C:\Program Files\Google\Update\GoogleUpdate.exe",
    ),
    (
        "startup",
        r"C:\ProgramData\...\Startup\Teams.lnk",
        "Microsoft",
        r"C:\Users\x\AppData\Local\Teams\current\Teams.exe",
    ),
    ("systemd", r"/etc/systemd/system/nginx.service", "distro", r"/usr/sbin/nginx"),
    (
        "run_key",
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Slack",
        "Slack Technologies",
        r"C:\Users\x\AppData\Local\slack\slack.exe",
    ),
)
_MAL: tuple[_Entry, ...] = (
    (
        "run_key",
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run\updater",
        None,
        r"C:\Users\x\AppData\Roaming\svch0st.exe",
    ),
    (
        "service",
        r"HKLM\System\CurrentControlSet\Services\WinHelpSvc",
        None,
        r"C:\Windows\Temp\whs.exe",
    ),
    ("scheduled_task", r"\Microsoft\Windows\.NET\DiagTask", None, r"C:\Users\Public\diag.vbs"),
    (
        "wmi",
        r"ROOT\subscription:CommandLineEventConsumer=SysMon",
        None,
        r"powershell -enc <redacted>",
    ),
    (
        "startup",
        r"C:\Users\x\AppData\Roaming\...\Startup\run.lnk",
        None,
        r"C:\Users\x\AppData\Roaming\run.scr",
    ),
    ("systemd", r"/etc/systemd/system/.cache-agent.service", None, r"/tmp/.cache/agent"),
)


def _is_malicious(signer: str | None, points_to: str) -> bool:
    """Independent route: unsigned AND pointing to a user-writable/temp or encoded target."""
    p = points_to.lower()
    suspect_path = any(
        s in p
        for s in (
            "\\temp\\",
            "\\appdata\\roaming\\",
            "\\users\\public\\",
            "/tmp/",
            "-enc",
            ".scr",
            ".vbs",
            "svch0st",
        )
    )
    return signer is None and suspect_path


class Pilot(GoldPilot):
    SUBTASK_ID = "T0397.002"
    SOURCE_VERSIONS = {"export": "autoruns-subset"}
    OUTPUT_SPEC = 'JSON {"entries": [{"location": "<reg/path>", "type": "run_key|service|scheduled_task|wmi|startup|systemd"}, ...]} listing only the malicious persistence entries'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        n_benign = rng.randint(5, 7)
        mal = rng.sample(_MAL, rng.randint(3, 5))
        chosen_benign = rng.sample(_BENIGN, n_benign)
        entries = []
        truth = []
        for typ, loc, signer, pts in chosen_benign:
            entries.append(
                {
                    "type": typ,
                    "location": loc,
                    "signer": signer,
                    "points_to": pts,
                    "mtime": iso(rng.time()),
                }
            )
        for typ, loc, signer, pts in mal:
            entries.append(
                {
                    "type": typ,
                    "location": loc,
                    "signer": signer,
                    "points_to": pts,
                    "mtime": iso(rng.time()),
                }
            )
            truth.append({"location": loc, "type": typ})
        entries = rng.shuffle(entries)
        public = {
            "autoruns": {"hv": "HV-16", "host": rng.hostname("ws"), "entries": entries},
            "objective": "List the malicious persistence entries with their correct type.",
        }
        gold_truth = {"entries": truth, "m": len(truth)}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored autoruns export; malicious entries are unsigned pointing to temp/roaming/encoded targets",
            independent_derivation="verifier re-derives malicious set from (unsigned AND suspect target path); must equal authored malicious set",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "signed OneDrive/Slack Run keys",
                "signed Spooler service",
                "GoogleUpdate/Windows scheduled tasks",
                "nginx systemd unit",
            ],
            adjudication_required=[
                "wmi CommandLineEventConsumer is a strong signal; confirm type taxonomy with owner"
            ],
        )
        return finalize(
            self.SUBTASK_ID,
            split,
            seed,
            public,
            gold_truth,
            prov,
            evidence_ids=[f"entry-{i}" for i in range(len(entries))],
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        entries = episode.public_inputs["autoruns"]["entries"]
        rederived = {
            (e["location"], e["type"])
            for e in entries
            if _is_malicious(e.get("signer"), e.get("points_to", ""))
        }
        gold = {(t["location"], t["type"]) for t in episode.gold_truth["entries"]}
        if rederived == gold:
            return VerificationResult(
                True, f"reputation verifier matched {len(gold)} malicious entries", ["entries"]
            )
        return VerificationResult(
            False, f"mismatch: gold={sorted(gold)} derived={sorted(rederived)}"
        )

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {"entries": [dict(e) for e in episode.gold_truth["entries"]]}
