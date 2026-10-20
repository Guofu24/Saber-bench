"""G4 — independent gold-label adjudication package (NOT auto-approved).

Builds a review package from representative live episodes: for each scenario family an evidence
bundle, the PROPOSED automated-lab labels with their rationale, accepted alternatives, the scoring
convention, and the unresolved ambiguities a qualified reviewer must settle. Nothing here is
approved: the package is PENDING_EXPERT_REVIEW and keeps READY_BENCHMARK at zero. It names the exact
external review needed to promote automated-lab truth to independently-validated gold.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from saber.catalog.loader import repo_root
from saber.range.live import run_episode

# Per-family scoring convention, accepted alternatives, and unresolved ambiguities for review.
_CONVENTIONS: dict[str, dict[str, Any]] = {
    "web_sqli_probe": {
        "bound_subtask": "T1347.001 / T0020.001 (set_delta)",
        "scoring_convention": "A request line is malicious iff its URL-decoded target contains a SQL "
        "token COMBINATION (e.g. UNION SELECT, ' OR, 1=1, SLEEP(); a lone SQL word is benign.",
        "accepted_alternatives": [
            "treat a benign request with a single SQL keyword as benign (current)",
            "a stricter policy could flag any request from a scanner UA regardless of payload",
        ],
        "unresolved_ambiguities": [
            "is an in-scope authorized pentest's probe a true positive or an exclusion?",
            "should obfuscated/double-encoded payloads beyond the current token set count?",
        ],
    },
    "auth_bruteforce": {
        "bound_subtask": "none (workflow artifact; threshold convention needs a business owner)",
        "scoring_convention": "A 401 is malicious iff its user exceeds 3 failed logins in the window "
        "(brute force is a volume phenomenon); a single benign typo is not an attack.",
        "accepted_alternatives": [
            "threshold could be 5 or time-windowed; low-and-slow distributed attempts are NOT captured",
        ],
        "unresolved_ambiguities": [
            "the exact threshold is business-specific",
            "credential stuffing (one attempt per account across many accounts) is not modeled",
        ],
    },
    "fs_change": {
        "bound_subtask": "none (workflow artifact; verified reversible IR action, not a scored contract)",
        "scoring_convention": "A webroot file is unauthorized iff it is a server-side script "
        "(.php/.aspx/.jsp/.cgi) present on disk with the webshell marker.",
        "accepted_alternatives": [
            "an approved/signed script deployment could be legitimate; a change-management allowlist "
            "would reclassify it",
        ],
        "unresolved_ambiguities": [
            "is ANY server-side script in the webroot unauthorized, or only unexpected ones?",
            "who is the approving authority for a legitimate deployment?",
        ],
    },
}


def build_adjudication_package(
    scenarios: list[str], *, seed: int = 1, workdir: Path | None = None
) -> dict[str, Any]:
    wd = workdir or (repo_root() / "runs" / "adjudication")
    bundles = []
    for scenario in scenarios:
        ep = run_episode(scenario, seed, workdir=wd)
        conv = _CONVENTIONS.get(scenario, {})
        bundles.append(
            {
                "scenario": scenario,
                "seed": seed,
                "evidence": {
                    "access_log_sample": ep.access_log_lines[:12],
                    "access_log_sha256": ep.access_log_sha256,
                    "fs_state": ep.lab_state.get("fs_state", []),
                },
                "proposed_labels": {
                    "malicious_line_ids": ep.gold_truth["malicious_line_ids"],
                    "source": "AUTOMATED_LAB_GROUND_TRUTH (control plane; NOT expert-approved)",
                    "cross_check_ok": ep.cross_check_ok,
                },
                **conv,
                "reviewer_decision": None,  # to be filled by a qualified reviewer; MUST NOT auto-fill
            }
        )
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "status": "PENDING_EXPERT_REVIEW",
        "sign_off": None,
        "labels": ["AUTOMATED_LAB_GROUND_TRUTH", "PENDING_ADJUDICATION", "DEV_SIMULATION_ONLY"],
        "ready_benchmark_subtasks": 0,
        "independently_validated_gold_labels": 0,
        "external_review_required": {
            "reviewer": "a qualified SOC/IR lead independent of this project",
            "scope": "confirm, per family, the proposed malicious labels and the scoring convention; "
            "resolve the listed ambiguities; sign off or return corrections",
            "promotion_rule": "only a signed, independent confirmation may move a subtask from "
            "AUTOMATED_LAB_GROUND_TRUTH toward INDEPENDENTLY_VERIFIED / READY_BENCHMARK",
        },
        "bundles": bundles,
    }


def write_adjudication_package(
    package: dict[str, Any], out_dir: Path | None = None
) -> tuple[Path, Path]:
    base = out_dir or (repo_root() / "docs" / "adjudication")
    base.mkdir(parents=True, exist_ok=True)
    jpath = base / "adjudication_package.json"
    jpath.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mpath = base / "adjudication_package.md"
    mpath.write_text(_markdown(package), encoding="utf-8")
    return jpath, mpath


def _markdown(pkg: dict[str, Any]) -> str:
    lines = [
        "# SABER gold-label adjudication package (Phase G4)",
        "",
        f"- Generated: {pkg['generated_at']}",
        f"- Status: **{pkg['status']}** — sign_off: {pkg['sign_off']}",
        f"- Independently validated gold labels: {pkg['independently_validated_gold_labels']}; "
        f"READY_BENCHMARK subtasks: {pkg['ready_benchmark_subtasks']}",
        "",
        "These are PROPOSED automated-lab labels, NOT expert-approved. They are not auto-approved; a "
        "qualified independent reviewer must confirm them before any promotion.",
        "",
        "## External review required",
        f"- Reviewer: {pkg['external_review_required']['reviewer']}",
        f"- Scope: {pkg['external_review_required']['scope']}",
        f"- Promotion rule: {pkg['external_review_required']['promotion_rule']}",
        "",
        "## Evidence bundles",
    ]
    for b in pkg["bundles"]:
        lines += [
            f"### {b['scenario']} (seed {b['seed']})",
            f"- Bound subtask: {b.get('bound_subtask')}",
            f"- Proposed malicious labels: {len(b['proposed_labels']['malicious_line_ids'])} line(s); "
            f"cross-check {b['proposed_labels']['cross_check_ok']}",
            f"- Scoring convention: {b.get('scoring_convention')}",
            f"- Accepted alternatives: {b.get('accepted_alternatives')}",
            f"- Unresolved ambiguities: {b.get('unresolved_ambiguities')}",
            f"- Reviewer decision: {b['reviewer_decision']} (to be completed by the reviewer)",
            "",
        ]
    return "\n".join(lines) + "\n"
