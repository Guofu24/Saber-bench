"""Documented catalog of candidate public security datasets (provenance + license + feasibility).

This is a *reviewed* list of reusable public sources, not an auto-download list. Each entry records
the license and whether research/eval usage is permitted, the dataset kind, and whether ingestion is
feasible on this host (``feasible_here``) or gated on an operator step (large download / license
acceptance / a binary parser dependency). Licenses noted here were reviewed from each project's
stated terms; the operator should re-confirm before redistribution.
"""

from __future__ import annotations

from saber.evaldata.provenance import DataSource

# name, kind, url, license, usage_permitted, notes
CANDIDATE_SOURCES: list[DataSource] = [
    DataSource(
        name="SigmaHQ/sigma",
        kind="detection_test",
        url="https://github.com/SigmaHQ/sigma",
        license="Detection Rule License (DRL) 1.1",
        usage_permitted=True,
        homepage="https://sigmahq.io/",
        notes="Generic detection rules w/ ATT&CK tags. Small per-rule YAML; permissive; feasible.",
    ),
    DataSource(
        name="redcanaryco/atomic-red-team",
        kind="detection_test",
        url="https://github.com/redcanaryco/atomic-red-team",
        license="MIT",
        usage_permitted=True,
        notes="Atomic tests (YAML) mapped to ATT&CK techniques. Small per-technique files; feasible.",
    ),
    DataSource(
        name="OTRF/Security-Datasets",
        kind="event_log",
        url="https://github.com/OTRF/Security-Datasets",
        license="GPL-3.0 (data)",
        usage_permitted=True,
        notes="Real Sysmon/Windows event logs from attack simulations (JSON). Copyleft; per-dataset "
        "download; operator should confirm redistribution terms. Gated on a sizeable download.",
    ),
    DataSource(
        name="CIC-IDS-2017 (UNB)",
        kind="network_capture",
        url="https://www.unb.ca/cic/datasets/ids-2017.html",
        license="UNB CIC academic terms (registration/attribution)",
        usage_permitted=True,
        notes="Labeled flow/pcap IDS dataset. Large; requires registration + license acceptance by "
        "the operator. Not auto-downloaded.",
    ),
    DataSource(
        name="malware-traffic-analysis.net",
        kind="network_capture",
        url="https://malware-traffic-analysis.net/",
        license="site terms (research use; per-post)",
        usage_permitted=True,
        notes="Real malicious pcaps with write-ups. Per-post license/terms; operator reviews each.",
    ),
]


def candidate_by_kind(kind: str) -> list[DataSource]:
    return [s for s in CANDIDATE_SOURCES if s.kind == kind]
