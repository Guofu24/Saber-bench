"""The four-service SOC case workflow run on a live episode.

A ``detect`` callable (the agent configuration under test) turns the episode's agent-visible
evidence into a detection rule + the lines it matches; the four services wrap that into a case:

* Monitoring   — validate the detection, open a case citing evidence line ids; scored vs the
  control-plane truth with T1347.001's set_delta contract (``max(0, M'/M - N'/(N'+M'))``).
* Threat Hunting — reconstruct the attack timeline and list affected entities from the evidence;
  runs even with no alert (a proactive hunt). Artifact + reported entity F1, not a scored contract.
* Incident Response — determine eligibility, and for fs_change EXECUTE the approved, reversible,
  verified quarantine action; otherwise propose containment only. Verified lab-state effect.
* Content Security — author a detection rule and test it on a HELD-OUT episode (different seed),
  measuring precision/recall/noise; scored with T0020.001's set_delta contract.

No service sees ``episode.gold_truth``; it is passed only to the scoring functions here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from saber.range.live import Approval, grant_approval, quarantine_file
from saber.range.live.episode import LiveEpisode

# A detector (the agent config under test) -> {pattern, ignore_case, matched_line_ids, calls, wall_ms}.
Detector = Callable[[LiveEpisode], dict[str, Any]]
# The operator role (NOT the detector) grants an approval bound to a specific action + target.
OperatorApprover = Callable[[str, str], Approval]

MON_SUBTASK = "T1347.001"  # set_delta: list the exploit lines
CNT_SUBTASK = "T0020.001"  # set_delta: author a detection rule


@dataclass
class Case:
    case_id: str
    scenario: str
    seed: int
    evidence_ref_count: int
    monitoring: dict[str, Any] = field(default_factory=dict)
    hunting: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    content_security: dict[str, Any] = field(default_factory=dict)
    audit: list[dict[str, Any]] = field(default_factory=list)
    labels: list[str] = field(
        default_factory=lambda: [
            "LIVE_LAB_EXECUTION",
            "AUTOMATED_LAB_GROUND_TRUTH",
            "DEV_SIMULATION_ONLY",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "scenario": self.scenario,
            "seed": self.seed,
            "evidence_ref_count": self.evidence_ref_count,
            "monitoring": self.monitoring,
            "hunting": self.hunting,
            "response": self.response,
            "content_security": self.content_security,
            "audit": self.audit,
            "labels": self.labels,
        }


def _set_delta_score(matched: set[str], truth: set[str]) -> dict[str, Any]:
    """T0020/T1347 source aggregate: max(0, M'/M - N'/(N'+M')) + FP/FN counts."""
    m = len(truth)
    m_hit = len(matched & truth)
    n_fp = len(matched - truth)
    score = max(0.0, (m_hit / m if m else 0.0) - (n_fp / (n_fp + m_hit) if (n_fp + m_hit) else 0.0))
    return {"score": round(score, 4), "false_positives": n_fp, "false_negatives": m - m_hit}


def _entities(episode: LiveEpisode, line_ids: set[str]) -> list[str]:
    """Affected entities implicated by the given lines (client / login user / uploaded file)."""
    ents: set[str] = set()
    import json as _json

    for lid in line_ids:
        try:
            rec = _json.loads(episode.access_log_lines[int(lid.split("-")[1])])
        except (ValueError, IndexError, _json.JSONDecodeError):
            continue
        q = parse_qs(urlsplit(str(rec.get("target", ""))).query)
        if episode.scenario == "auth_bruteforce":
            ents.add("user:" + (q.get("user") or ["?"])[0])
        elif episode.scenario == "fs_change":
            ents.add("file:" + (q.get("name") or ["?"])[0])
        else:
            ents.add("client:" + str(rec.get("client", "?")))
    return sorted(ents)


def _monitoring(
    episode: LiveEpisode, detection: dict[str, Any], truth: set[str], case: Case
) -> None:
    matched = {str(x) for x in detection.get("matched_line_ids", [])}
    valid = matched <= set(episode.evidence_ids)  # cited evidence must exist in the episode
    case.monitoring = {
        "subtask": MON_SUBTASK,
        "contract": "set_delta max(0, M'/M - N'/(N'+M'))",
        "cited_evidence": sorted(matched),
        "evidence_refs_valid": valid,
        "suspicious_count": len(matched),
        **_set_delta_score(matched, truth),
    }
    case.audit.append(
        {
            "service": "monitoring",
            "tool": "regex_detect",
            "n_calls": len(detection.get("calls", [])),
            "evidence_valid": valid,
        }
    )


def _threat_hunting(
    episode: LiveEpisode, detection: dict[str, Any], truth: set[str], case: Case
) -> None:
    import json as _json

    matched = {str(x) for x in detection.get("matched_line_ids", [])}
    # Timeline: the implicated events in true chronological order (real ts from the telemetry).
    order = sorted(matched, key=lambda lid: _ts_of(episode, lid))
    found_ents = _entities(episode, matched)
    truth_ents = _entities(episode, truth)
    inter = len(set(found_ents) & set(truth_ents))
    prec = inter / len(found_ents) if found_ents else 0.0
    rec = inter / len(truth_ents) if truth_ents else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    case.hunting = {
        "hypothesis": f"malicious activity of type {episode.scenario} present in the window",
        "timeline": [{"line": lid, "ts": _ts_raw(episode, lid)} for lid in order],
        "affected_entities": found_ents,
        "entity_f1_reported": round(f1, 4),  # reported artifact metric, NOT a source-contract score
        "proactive": detection.get("proactive", False),
        "note": "timeline + entities derived from the evidence; not claimed as source-contract coverage",
    }
    _ = _json  # (kept for symmetry; parsing done in helpers)
    case.audit.append(
        {"service": "threat_hunting", "tool": "timeline_search", "entities": len(found_ents)}
    )


def _ts_of(episode: LiveEpisode, lid: str) -> str:
    return _ts_raw(episode, lid) or ""


def _ts_raw(episode: LiveEpisode, lid: str) -> str:
    import json as _json

    try:
        return str(_json.loads(episode.access_log_lines[int(lid.split("-")[1])]).get("ts", ""))
    except (ValueError, IndexError, _json.JSONDecodeError):
        return ""


def _incident_response(
    episode: LiveEpisode, case: Case, *, operator_approve: OperatorApprover, executor_token: str
) -> None:
    confirmed = case.monitoring.get("cited_evidence", [])
    eligible = bool(confirmed)
    resp: dict[str, Any] = {"eligible": eligible, "actions": []}
    if not eligible:
        resp["note"] = "no confirmed finding; no containment"
        case.response = resp
        return
    if episode.scenario == "fs_change" and episode.evidence_dir:
        import json as _json
        from pathlib import Path
        from urllib.parse import parse_qs, urlsplit

        webroot = Path(episode.evidence_dir) / "webroot"
        # Targets come from the AGENT's confirmed findings (cited evidence), NOT privileged lab
        # state — so IR outcomes depend on detection quality (a missed webshell is not contained; a
        # false positive causes benign collateral). Separation of duties: the OPERATOR (not the
        # detector) grants an approval bound to the exact file; the executor runs it with its token.
        targets: list[str] = []
        for lid in confirmed:
            try:
                rec = _json.loads(episode.access_log_lines[int(str(lid).split("-")[1])])
            except (ValueError, IndexError, _json.JSONDecodeError):
                continue
            if "/fs/put" in str(rec.get("target", "")):
                name = Path(
                    (parse_qs(urlsplit(str(rec["target"])).query).get("name") or [""])[0]
                ).name
                if name:
                    targets.append(name)
        for name in dict.fromkeys(targets):  # dedupe, preserve order
            approval = operator_approve("quarantine_webroot_file", name)
            result = quarantine_file(
                webroot, name, approval=approval, executor_token=executor_token
            )
            resp["actions"].append(result.audit())
            case.audit.append(
                {"service": "incident_response", "tool": "quarantine", **result.audit()}
            )
        resp["targets_from"] = "agent_confirmed_findings"
        resp["verified"] = all(a["verified"] for a in resp["actions"]) if resp["actions"] else False
        resp["collateral"] = sorted({c for a in resp["actions"] for c in a.get("collateral", [])})
        resp["note"] = "executed approved reversible quarantine; effect verified from real fs state"
    else:
        resp["proposed_containment"] = (
            "rate-limit/block the offending source"
            if episode.scenario == "auth_bruteforce"
            else "deploy the detection rule inline"
        )
        resp["verified"] = False
        resp["note"] = (
            "containment PROPOSED only (no reversible lab action available for this scenario)"
        )
    case.response = resp


def _content_security(
    episode: LiveEpisode,
    heldout: LiveEpisode,
    heldout_truth: set[str],
    heldout_detection: dict[str, Any],
    case: Case,
) -> None:
    # The "detection content" is the detector rule; testing on held-out = running it on a fresh
    # episode (generalises to regex and non-regex rules alike).
    pattern = heldout_detection.get("pattern", "")
    matched = {str(x) for x in heldout_detection.get("matched_line_ids", [])}
    m = len(heldout_truth)
    m_hit = len(matched & heldout_truth)
    n_fp = len(matched - heldout_truth)
    prec = m_hit / (m_hit + n_fp) if (m_hit + n_fp) else 0.0
    rec = m_hit / m if m else 0.0
    case.content_security = {
        "subtask": CNT_SUBTASK,
        "contract": "set_delta max(0, M'/M - N'/(N'+M'))",
        "rule_version": "v1",
        "pattern": pattern,
        "heldout_seed": heldout.seed,
        "heldout_precision": round(prec, 4),
        "heldout_recall": round(rec, 4),
        "heldout_noise_fp": n_fp,
        "heldout_kind": "same-family re-draw (disjoint seed) — tests robustness to a re-draw, NOT "
        "cross-family generalization",
        **{"heldout_" + k: v for k, v in _set_delta_score(matched, heldout_truth).items()},
    }
    case.audit.append(
        {"service": "content_security", "tool": "rule_test_heldout", "heldout_seed": heldout.seed}
    )


def default_lab_operator(executor_token: str) -> OperatorApprover:
    """A lab operator role (distinct from the detector) that grants per-target bound approvals."""

    def approve(action: str, target: str) -> Approval:
        return grant_approval(action, target, executor_token=executor_token, ttl_s=300)

    return approve


def run_case_workflow(
    episode: LiveEpisode,
    heldout: LiveEpisode,
    detect: Detector,
    *,
    episode_truth: set[str],
    heldout_truth: set[str],
    operator_approve: OperatorApprover | None = None,
    executor_token: str | None = None,
) -> Case:
    """Run the four services end-to-end on a live episode; return the structured case.

    The IR executor token and the operator (approver) are kept distinct from the detector/agent
    (separation of duties). A lab operator + token are used by default.
    """
    token = executor_token or "LAB-EXECUTOR-TOKEN"
    approver = operator_approve or default_lab_operator(token)
    case = Case(
        case_id=f"CASE-{episode.scenario}-{episode.seed}",
        scenario=episode.scenario,
        seed=episode.seed,
        evidence_ref_count=len(episode.evidence_ids),
    )
    detection = detect(episode)
    _monitoring(episode, detection, episode_truth, case)
    _threat_hunting(episode, detection, episode_truth, case)
    _incident_response(episode, case, operator_approve=approver, executor_token=token)
    _content_security(episode, heldout, heldout_truth, detect(heldout), case)
    case.monitoring["rule_pattern"] = detection.get("pattern")
    case.audit.append({"workflow": "complete", "at": datetime.now(UTC).isoformat()})
    return case
