"""SABER-authored competency tracks; no HTB content, answers or access entitlement."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    requirement: str


class Track(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    team: Literal["red", "blue", "purple"]
    title: str
    roles: tuple[str, ...]
    source_url: str
    guidance_topic: str
    criteria: tuple[Criterion, ...]


PRO = "https://help.hackthebox.com/en/articles/5185470-how-to-play-pro-labs"
SHERLOCKS = "https://help.hackthebox.com/en/articles/8570249-how-to-play-sherlocks"
SOC = "https://enterprise-help.hackthebox.com/en/articles/15654060-soc-range"
AI = "https://www.hackthebox.com/ai/agent-competence"
BLUE_GUIDE = "soc-orchestrator--external-practice"
RED_GUIDE = "external-practice"
COMMON = (
    Criterion(
        id="scope",
        requirement="Identify the assigned assets, identities, time window, objective and unavailable capabilities.",
    ),
    Criterion(
        id="lineage",
        requirement="Cite original evidence and any conversion's hashes, method, timezone and completeness limits.",
    ),
    Criterion(
        id="uncertainty",
        requirement="Test a plausible alternative and distinguish observations, interpretations and unknowns.",
    ),
)


def track(
    id: str,
    team: Literal["red", "blue", "purple"],
    title: str,
    roles: tuple[str, ...],
    url: str,
    requirements: tuple[tuple[str, str], ...],
) -> Track:
    return Track(
        id=id,
        team=team,
        title=title,
        roles=roles,
        source_url=url,
        guidance_topic=RED_GUIDE if team == "red" else BLUE_GUIDE,
        criteria=COMMON + tuple(Criterion(id=k, requirement=v) for k, v in requirements),
    )


TRACKS = {
    t.id: t
    for t in (
        track(
            "red-web",
            "red",
            "Web and API access boundaries",
            ("recon", "access"),
            PRO,
            (
                (
                    "boundary",
                    "Compare expected authorization with observed resource access under identified principals.",
                ),
                (
                    "effect",
                    "Support each claimed effect with an execution receipt and observable result, beyond an HTTP status.",
                ),
                (
                    "handoff",
                    "Include failed checks, reproducible observations and the capability actually handed to the next actor.",
                ),
            ),
        ),
        track(
            "red-enterprise",
            "red",
            "Windows/Linux and enterprise attack paths",
            ("recon", "access", "impact"),
            PRO,
            (
                (
                    "path",
                    "Document prerequisites and evidence for each asset/principal/privilege transition.",
                ),
                (
                    "capability",
                    "Verify destination identity and effective access; distinguish candidate relationships from traversed edges.",
                ),
                (
                    "closeout",
                    "Record objective limits, residual changes and verified cleanup or explicitly outstanding work.",
                ),
            ),
        ),
        track(
            "red-agent-evaluation",
            "red",
            "Repeatable agent execution assessment",
            ("recon", "access", "impact"),
            AI,
            (
                (
                    "conditions",
                    "Record model/skill/tool versions, fresh instance boundary, budget and prior assistance.",
                ),
                (
                    "outcomes",
                    "Separate objective evidence from tool failures, provider failures and unsupported agent claims.",
                ),
                (
                    "replay",
                    "Test a proposed improvement on a fresh attempt without transferring task answers.",
                ),
            ),
        ),
        track(
            "blue-dfir",
            "blue",
            "Evidence reconstruction and incident scope",
            ("dfir", "network", "identity"),
            SHERLOCKS,
            (
                (
                    "timeline",
                    "Reconstruct a cited timeline with scoped entity joins and explicit clock uncertainty.",
                ),
                (
                    "impact",
                    "Distinguish execution, access, collection and transfer using the evidence available.",
                ),
                (
                    "handoff",
                    "Report confirmed/suspected/unknown scope and the next discriminating collection or check.",
                ),
            ),
        ),
        track(
            "blue-soc",
            "blue",
            "SOC shift, triage and response decisions",
            ("monitor", "lead", "ir", "recovery", "platform"),
            SOC,
            (
                (
                    "triage",
                    "Prioritize and classify alerts using raw evidence, benign alternatives and asset context.",
                ),
                (
                    "response",
                    "Distinguish proposed, authorized, applied and verified response; mark offline effects unavailable.",
                ),
                (
                    "closure",
                    "Document handoff, telemetry gaps, client/service recovery and unresolved risk before closure.",
                ),
            ),
        ),
        track(
            "blue-hunt-detection",
            "blue",
            "Hypothesis hunting and detection validation",
            ("hunter", "content", "intel", "platform"),
            SHERLOCKS,
            (
                (
                    "hypothesis",
                    "Provide a falsifiable hypothesis and reproducible queries with scope and pagination.",
                ),
                (
                    "controls",
                    "Evaluate detection logic on positive and benign controls, retaining source and rule versions.",
                ),
                (
                    "coverage",
                    "Report observed coverage and denominators; do not infer no missed incidents from an empty queue.",
                ),
            ),
        ),
        track(
            "blue-malware",
            "blue",
            "Malware and network evidence analysis",
            ("malware", "network", "dfir"),
            SHERLOCKS,
            (
                (
                    "analysis",
                    "Identify sample/capture hashes, analysis methods, tools and environment limitations.",
                ),
                (
                    "behavior",
                    "Correlate static indicators with observed process or network behavior; do not equate strings with execution.",
                ),
                (
                    "affected-scope",
                    "Separate sample characteristics from affected-host evidence and list unanswered incident questions.",
                ),
            ),
        ),
        track(
            "blue-identity-cloud",
            "blue",
            "Identity, cloud and session investigation",
            ("identity", "dfir", "hunter", "ir"),
            SHERLOCKS,
            (
                (
                    "identity",
                    "Resolve tenant/domain, principal, session and effective privilege with audit coverage.",
                ),
                (
                    "activity",
                    "Join control-plane and data-plane evidence without inventing unlogged activity.",
                ),
                (
                    "revocation",
                    "Explain how token/grant revocation and recovery would be independently verified, or why unavailable.",
                ),
            ),
        ),
        track(
            "purple-validation",
            "purple",
            "Local attack/detection/response debrief",
            ("lead", "content", "ir", "recovery"),
            SOC,
            (
                (
                    "separation",
                    "Keep red plans and evaluator truth hidden from blue during the exercise.",
                ),
                (
                    "comparison",
                    "Compare attempted actions, observed effects, available telemetry and blue decisions after the run.",
                ),
                (
                    "regression",
                    "Replay a general improvement against positive and benign cases without answer leakage.",
                ),
            ),
        ),
    )
}
