"""Gold pilot T0167.002 (HUNT, file) — malicious/benign verdict per file (accuracy).

Artifact: a set of files with name, sha256, signer, and extracted strings/APIs. Hard negatives:
CLEAN files that legitimately use `eval`/`base64`/packing — a minified JS bundle, a Jinja template
engine, a commercially packed installer. Ground truth is independently derived from signer +
behaviour (a trusted signer OR a benign-tool fingerprint ⇒ benign; unsigned + obfuscation + a
suspicious API combo ⇒ malicious), a route distinct from a naive "contains eval" solver. Scored by
accuracy over the per-file verdicts (source `accuracy`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.grading.primitives import accuracy
from saber.grading.results import ItemScore, ScoreResult
from saber.subtasks._hv.common import Rng

# (filename, signer, strings/APIs, malicious?) — benign-tricky ones use eval/base64 legitimately.
_BENIGN = (
    ("app.min.js", "Webpack", ["eval(", "base64", "sourceMappingURL"], False),
    ("jinja2/nativetypes.py", "PyPA", ["eval(", "compile(", "ast.literal_eval"], False),
    ("setup_installer.exe", "Acme Corp (signed)", ["UPX0", "base64", "CreateProcess"], False),
    ("report.pdf", "Adobe", ["%PDF-1.7", "xref"], False),
    ("update.ps1", "Contoso IT (signed)", ["Invoke-WebRequest", "base64"], False),
)
_MAL = (
    (
        "invoice_scan.exe",
        None,
        ["VirtualAlloc", "base64", "WriteProcessMemory", "IsDebuggerPresent"],
        True,
    ),
    ("doc.js", None, ["eval(unescape(", "ActiveXObject", "ADODB.Stream"], True),
    ("svc.dll", None, ["LoadLibrary", "base64", "InternetOpenUrl", "RegSetValue(Run)"], True),
    ("macro.vbs", None, ["CreateObject(WScript.Shell)", "powershell -enc", "base64"], True),
)
_SUSPICIOUS_APIS = (
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


def _derive_verdict(signer: str | None, strings: list[str]) -> str:
    """Independent route: trusted signer -> benign; else unsigned + suspicious API combo -> malicious."""
    if signer is not None:
        return "benign"
    s = " ".join(strings).lower()
    suspicious = sum(1 for a in _SUSPICIOUS_APIS if a in s)
    return "malicious" if suspicious >= 2 else "benign"


class Pilot(GoldPilot):
    SUBTASK_ID = "T0167.002"
    SOURCE_VERSIONS = {"artifact": "file-triage-extract"}
    OUTPUT_SPEC = (
        'JSON {"verdicts": {"<filename>": "malicious"|"benign", ...}} with a verdict for every file'
    )

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        benign = rng.sample(_BENIGN, rng.randint(3, 5))
        mal = rng.sample(_MAL, rng.randint(2, 4))
        files: list[dict[str, Any]] = []
        truth: dict[str, str] = {}
        for name, signer, strings, is_mal in list(benign) + list(mal):
            fname = f"{rng.hexid('f', 3)}_{name}"
            files.append(
                {"name": fname, "sha256": rng.sha256(fname), "signer": signer, "strings": strings}
            )
            # Truth = the authored CONSTRUCTION INTENT (which pool the file came from). The
            # independent signer+API rule (_derive_verdict) is NOT used to define truth here;
            # independent_verify re-derives it that way and must agree — a genuine second route.
            truth[fname] = "malicious" if is_mal else "benign"
        files = rng.shuffle(files)
        public = {
            "files": files,
            "objective": "Give a malicious/benign verdict for every file. Note: legitimate tools may use eval/base64/packing.",
        }
        gold_truth = {"verdicts": truth}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored file-triage extract; benign-tricky files legitimately use eval/base64/packing",
            independent_derivation="truth = authored construction intent (source pool); verify re-derives independently from signer + suspicious-API count (>=2 unsigned APIs => malicious), NOT from mere eval/base64 presence, and must agree",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "webpack minified eval()",
                "jinja eval/compile",
                "signed packed installer (UPX+base64)",
                "signed IT PowerShell using base64",
            ],
            adjudication_required=[
                "border cases where a signer is unknown but behaviour is benign need analyst review"
            ],
        )
        return finalize(
            self.SUBTASK_ID,
            split,
            seed,
            public,
            gold_truth,
            prov,
            evidence_ids=[f["name"] for f in files],
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        rederived = {
            f["name"]: _derive_verdict(f.get("signer"), f.get("strings", []))
            for f in episode.public_inputs["files"]
        }
        if rederived == episode.gold_truth["verdicts"]:
            return VerificationResult(
                True, f"signer+API verifier matched {len(rederived)} verdicts", ["verdicts"]
            )
        diff = {
            k: (rederived[k], episode.gold_truth["verdicts"][k])
            for k in rederived
            if rederived[k] != episode.gold_truth["verdicts"].get(k)
        }
        return VerificationResult(False, f"mismatch: {diff}")

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {"verdicts": dict(episode.gold_truth["verdicts"])}

    def grade(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        *,
        agent_id: str,
        evidence_refs: list[str] | None = None,
    ) -> ScoreResult:
        truth = episode.gold_truth["verdicts"]
        raw = answer.get("verdicts")
        pred = raw if isinstance(raw, dict) else {}
        pairs = [(pred.get(k), v) for k, v in truth.items()]
        score, detail = accuracy(pairs)
        comp = ItemScore(field="verdicts", score=score, weight=1.0, detail=detail)
        return self._result(episode, answer, score, components=[comp], trace=[f"accuracy {detail}"])
