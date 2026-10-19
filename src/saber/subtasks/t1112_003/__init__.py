"""T1112.003 (MON, soc) — validate a full SIEM case and its alert claim.

Source scorer: `Σ wᵢ·sᵢ ; cap 0.30 nếu classification sai`, with weights classification 0.30,
claim_confirmed 0.30, alert_claim 0.15, triggering_rule 0.125, affected_asset 0.125, and an
`explain` citation gate. A wrong classification caps the whole score at 0.30; unresolved/absent
citations zero it.

Enum label domains are DEV-chosen (the source does not enumerate them) and are flagged for
adjudication. soc integration against a real SIEM/EDR case store is BLOCKED_INTEGRATION.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from saber.domain.base import StrictModel
from saber.domain.subtask import ToolPolicy
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng

Classification = Literal["TRUE_POSITIVE", "FALSE_POSITIVE", "INCONCLUSIVE"]
ClaimConfirmed = Literal["confirmed", "refuted", "unverified"]
AlertClaim = Literal["valid", "invalid"]


class T1112_003Output(StrictModel):
    classification: Classification
    claim_confirmed: ClaimConfirmed
    alert_claim: AlertClaim
    triggering_rule: str
    affected_asset: str
    explain: list[str] = []


class Subtask(SubtaskBase):
    SUBTASK_ID = "T1112.003"
    OutputModel = T1112_003Output
    TOOL_POLICY = ToolPolicy(
        allow=["read_fixture", "search_case", "search_events"], state_mutation=False
    )
    ADJUDICATION_NOTES = [
        "classification labels {TRUE_POSITIVE,FALSE_POSITIVE,INCONCLUSIVE} are DEV-chosen; confirm with source owner",
        "claim_confirmed/alert_claim label sets are DEV-chosen pending adjudication",
    ]
    VARIANTS = ("tp", "fp")

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        host = rng.hostname("ws")
        rule = rng.pick(
            ["SIGMA_OFFICE_SPAWNS_INTERPRETER", "EDR_SUSPICIOUS_DROPPER", "NSM_PORT_SCAN"]
        )
        ev_alert, ev_log, ev_proc = rng.hexid("ALERT"), rng.hexid("LOG"), rng.hexid("PROC")
        claim_text = (
            "alert asserts an interpreter was spawned by an office document and beaconed out"
        )
        if variant == "fp":
            classification: Classification = "FALSE_POSITIVE"
            claim: ClaimConfirmed = "refuted"
            alert_claim: AlertClaim = "invalid"
            # Evidence that REFUTES the alert's claim: the flagged process is a signed admin tool
            # launched interactively, with no office parent and no external connection.
            proc_detail = "process is a signed IT admin tool launched from an interactive console; parent is explorer.exe, not an office app"
            log_detail = (
                "no outbound connection in the window; activity matches an approved change ticket"
            )
        else:
            classification = "TRUE_POSITIVE"
            claim = "confirmed"
            alert_claim = "valid"
            # Evidence that CONFIRMS the alert's claim.
            proc_detail = "winword.exe spawned an interpreter with encoded arguments (office parent confirmed)"
            log_detail = (
                "interpreter opened an outbound connection to a rare external host in the window"
            )
        case = {
            "hv": "HV-07",
            "case_id": rng.hexid("CASE"),
            "alert_id": ev_alert,
            "rule_name": rule,
            "host": host,
            "alert_claim_text": claim_text,
        }
        logs = {"hv": "HV-02", "lines": [{"id": ev_log, "host": host, "detail": log_detail}]}
        proc = {"hv": "HV-15", "events": [{"id": ev_proc, "host": host, "detail": proc_detail}]}
        assets = {"hv": "HV-38", "assets": [{"host": host, "tier": rng.pick(["t1", "t2", "t3"])}]}
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={"case": case, "logs": logs, "process": proc, "assets": assets},
            sealed_truth={
                "classification": classification,
                "claim_confirmed": claim,
                "alert_claim": alert_claim,
                "triggering_rule": rule,
                "affected_asset": host,
                "cite_refs": [ev_alert, ev_log],
            },
            evidence_ids=[ev_alert, ev_log, ev_proc],
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "classification",
            "claim_confirmed",
            "alert_claim",
            "triggering_rule",
            "affected_asset",
        )
        return {**{k: truth[k] for k in keys}, "explain": list(truth.get("cite_refs", []))}

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        comps = [
            self.enum_item("classification", answer.classification, truth["classification"]),
            self.enum_item("claim_confirmed", answer.claim_confirmed, truth["claim_confirmed"]),
            self.enum_item("alert_claim", answer.alert_claim, truth["alert_claim"]),
            self.enum_item("triggering_rule", answer.triggering_rule, truth["triggering_rule"]),
            self.enum_item("affected_asset", answer.affected_asset, truth["affected_asset"]),
        ]
        cls_ok = comps[0].score == 1.0
        gates = [
            self.cite_gate(answer.explain, ctx, name="explain"),
            self.gate(
                "cap:classification",
                cls_ok,
                "classification wrong -> cap 0.30",
                mode="cap",
                factor=0.30,
            ),
        ]
        return ScoreParts(
            components=comps, gates=gates, trace=[f"{c.field}={c.score}" for c in comps]
        )

    def perfect_evidence_refs(self, bundle: FixtureBundle) -> list[str]:
        return list(bundle.evidence_ids[:1])

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        case = public_inputs["case"]
        proc_text = " ".join(
            e.get("detail", "") for e in public_inputs["process"]["events"]
        ).lower()
        log_text = " ".join(
            line.get("detail", "") for line in public_inputs["logs"]["lines"]
        ).lower()
        text = proc_text + " " + log_text
        confirms = any(
            m in text
            for m in ("office parent", "encoded arguments", "outbound connection to a rare")
        )
        refutes = any(
            m in text
            for m in ("signed it admin tool", "approved change ticket", "no outbound connection")
        )
        malicious = confirms and not refutes
        answer = {
            "classification": "TRUE_POSITIVE" if malicious else "FALSE_POSITIVE",
            "claim_confirmed": "confirmed" if malicious else "refuted",
            "alert_claim": "valid" if malicious else "invalid",
            "triggering_rule": case["rule_name"],
            "affected_asset": case["host"],
            "explain": [case["alert_id"]],
        }
        return answer, [case["alert_id"]]

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        t = bundle.sealed_truth
        ev = bundle.evidence_ids
        wrong_cls: Classification = (
            "INCONCLUSIVE" if t["classification"] != "INCONCLUSIVE" else "TRUE_POSITIVE"
        )
        perfect = self.answer_from_truth(t)
        return [
            GoldenCase(
                "no_citation",
                {**perfect, "explain": []},
                expected_score=0.0,
                expect_trace_contains="explain",
            ),
            GoldenCase(
                "hallucinated_citation",
                {**perfect, "explain": ["ev-nonexistent"]},
                expected_score=0.0,
            ),
            GoldenCase(
                "wrong_classification_capped",
                {**perfect, "classification": wrong_cls, "explain": ev[:1]},
                expected_max=0.30,
            ),
            GoldenCase("perfect_with_cite", {**perfect, "explain": ev[:1]}, expected_score=1.0),
        ]
