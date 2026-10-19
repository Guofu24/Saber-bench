"""Gold Evaluation Pilot v1: domain-faithful evaluation artifacts with independently-derived truth.

This is a deliberate step up from the archetype engine's STRUCTURAL fixtures. A gold pilot for a
subtask provides a realistic artifact (real log/alert/process/registry formats, real ATT&CK ids and
IOC shapes), a ground truth that is **independently derived** — a separate verifier re-derives it
from the artifact content by a different route than any solver's inference rule, and the two must
agree — plus provenance (how it was built, checksums, source versions), hard negatives, a dev vs
hidden split, and a human-adjudication queue for anything that cannot be independently verified.

Honesty: these artifacts are hand-curated synthetic, domain-faithful, and cross-validated, but they
are NOT externally licensed corpora and NOT human-expert-signed. A gold pilot subtask is therefore
`IMPLEMENTED_OFFLINE`/`VERIFIED_OFFLINE` with a gold artifact; it only becomes `READY_BENCHMARK`
after the queued human adjudication and external validation, which this code never fakes.
"""

from saber.gold.base import GoldEpisode, GoldPilot, Provenance, load_pilot, pilot_ids

__all__ = ["GoldEpisode", "GoldPilot", "Provenance", "load_pilot", "pilot_ids"]
