"""Gold pilot T1348.002 (MON, file) — label each admin activity legit vs attack (accuracy).

Artifact: a list of administrative actions (PsExec, WMI, PowerShell remoting, scheduled task,
net user) plus an internal whitelist (approved admin accounts and the host scope they manage).
Ground truth is independently derived from the whitelist + scope: an action is legit iff its source
account is an approved admin AND its target is inside that admin's managed scope; otherwise attack.
Hard negatives: the SAME tool (e.g. PsExec) is legit for a whitelisted admin and attack for a
non-admin source. Scored by accuracy over per-activity labels (source `accuracy`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, Split, VerificationResult, finalize
from saber.grading.primitives import accuracy
from saber.grading.results import ItemScore, ScoreResult
from saber.subtasks._hv.common import Rng

_TOOLS = ("PsExec", "WMI", "PowerShell-remoting", "scheduled-task", "net-user-add")


def _derive(activity: Mapping[str, Any], whitelist: Mapping[str, Any]) -> str:
    admins = whitelist["admin_accounts"]
    scope = set(whitelist["managed_hosts"])
    src = activity["account"]
    tgt = activity["target_host"]
    return "legit" if (src in admins and tgt in scope) else "attack"


class Pilot(GoldPilot):
    SUBTASK_ID = "T1348.002"
    SOURCE_VERSIONS = {"artifact": "admin-activity-log", "policy": "internal-whitelist"}
    OUTPUT_SPEC = 'JSON {"labels": {"<activity_id>": "legit"|"attack", ...}} for every activity'

    def build(self, split: Split, seed: int) -> GoldEpisode:
        rng = Rng(f"gold:{seed}", self.SUBTASK_ID, split)
        admins = [f"adm.{rng.pick(('an', 'binh', 'huy'))}{rng.randint(1, 9)}" for _ in range(2)]
        managed = [rng.hostname("srv") for _ in range(4)]
        whitelist = {"admin_accounts": admins, "managed_hosts": managed}
        activities: list[dict[str, Any]] = []
        n = rng.randint(8, 12)
        intent: dict[str, str] = {}
        for i in range(n):
            tool = rng.pick(_TOOLS)
            # mix: legit (admin+managed), attack (non-admin or out-of-scope). The branch records
            # the authored CONSTRUCTION INTENT, which is the truth; independent_verify re-derives
            # the label from the whitelist policy (_derive) and must agree — a genuine 2nd route.
            if rng.chance(0.5):
                acct, tgt, label = rng.pick(admins), rng.pick(managed), "legit"
            elif rng.chance(0.5):
                acct, tgt, label = rng.username(), rng.pick(managed), "attack"  # non-admin source
            else:
                acct, tgt, label = rng.pick(admins), rng.hostname("ws"), "attack"  # out-of-scope
            aid = f"act-{i:02d}"
            intent[aid] = label
            activities.append(
                {"id": aid, "tool": tool, "account": acct, "target_host": tgt, "ts": None}
            )
        activities = rng.shuffle(activities)
        truth = {a["id"]: intent[a["id"]] for a in activities}
        public = {
            "activities": activities,
            "whitelist": {"hv": "HV-40", **whitelist},
            "objective": "Label each admin activity legit or attack using the internal whitelist and managed-host scope.",
        }
        gold_truth = {"labels": truth}
        prov = Provenance(
            builder=f"{__name__}.Pilot",
            method="authored admin-activity log + internal whitelist; same tool appears legit and attack",
            independent_derivation="truth = authored construction intent per activity; verify re-derives the label independently from the whitelist policy (admin account AND target in managed scope => legit) and must agree — a policy route, not a tool-name heuristic",
            source_versions=self.SOURCE_VERSIONS,
            hard_negatives=[
                "PsExec/WMI legit for a whitelisted admin but attack from a non-admin",
                "admin acting outside managed scope is attack",
            ],
            adjudication_required=[
                "whether an admin acting out-of-scope is 'attack' vs 'policy-violation' — owner to confirm the binary label"
            ],
        )
        return finalize(
            self.SUBTASK_ID,
            split,
            seed,
            public,
            gold_truth,
            prov,
            evidence_ids=[a["id"] for a in activities],
        )

    def independent_verify(self, episode: GoldEpisode) -> VerificationResult:
        wl = {
            "admin_accounts": episode.public_inputs["whitelist"]["admin_accounts"],
            "managed_hosts": episode.public_inputs["whitelist"]["managed_hosts"],
        }
        rederived = {a["id"]: _derive(a, wl) for a in episode.public_inputs["activities"]}
        if rederived == episode.gold_truth["labels"]:
            return VerificationResult(
                True, f"policy verifier matched {len(rederived)} labels", ["labels"]
            )
        return VerificationResult(False, "policy re-derivation disagrees with gold labels")

    def answer_from_gold(self, episode: GoldEpisode) -> dict[str, Any]:
        return {"labels": dict(episode.gold_truth["labels"])}

    def grade(
        self,
        episode: GoldEpisode,
        answer: Mapping[str, Any],
        *,
        agent_id: str,
        evidence_refs: list[str] | None = None,
    ) -> ScoreResult:
        truth = episode.gold_truth["labels"]
        raw = answer.get("labels")
        pred = raw if isinstance(raw, dict) else {}
        score, detail = accuracy([(pred.get(k), v) for k, v in truth.items()])
        return self._result(
            episode,
            answer,
            score,
            components=[ItemScore(field="labels", score=score, weight=1.0, detail=detail)],
            trace=[f"accuracy {detail}"],
        )
