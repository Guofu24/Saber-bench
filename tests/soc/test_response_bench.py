"""Track B response benchmark: containment is verified from real lab state, and a naive detector's
over-flagging shows up as measured benign impact (false containment) that detection-only hides."""

from __future__ import annotations

from pathlib import Path

from saber.soc import run_response_bench


def test_response_bench_measures_benign_impact(tmp_path: Path) -> None:
    rep = run_response_bench(seeds=[1, 2], workdir=tmp_path)
    conv = rep["summary"]["conventional"]
    naive = rep["summary"]["naive"]

    # Both contain the webshell (the quarantine is verified from real fs state)...
    assert conv["containment_recall_mean"] == 1.0
    assert conv["all_verified_rate"] == 1.0
    assert naive["containment_recall_mean"] == 1.0

    # ...but only the precise detector does so WITHOUT benign operational impact.
    assert conv["false_containment_total"] == 0
    assert naive["false_containment_total"] > conv["false_containment_total"]
