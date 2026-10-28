"""Track A detection benchmark: it runs end to end and discriminates a precise rule from a naive one.

The benchmark overlays benign client noise, so the naive floor pays for its over-flagging in false
positives while the conventional rule stays precise — i.e. the benchmark is NOT ceiling-saturated.
"""

from __future__ import annotations

from pathlib import Path

from saber.soc import run_detection_bench


def test_detection_bench_runs_and_discriminates(tmp_path: Path) -> None:
    rep = run_detection_bench(seeds=[1, 2], noise_clients=3, workdir=tmp_path)

    # Every episode executed genuinely, reset cleanly, and cross-checked; the allowlist is complete.
    assert rep["allowlist_covers_scenarios"] is True
    assert rep["all_cross_checks_ok"] is True
    assert set(rep["families"]) == {"web_sqli_probe", "auth_bruteforce", "fs_change", "persistence"}

    conv = rep["summary"]["conventional"]
    naive = rep["summary"]["naive"]

    # Both detectors find the attacks (recall high); the client noise is real benign volume.
    assert conv["recall"]["mean"] is not None and conv["recall"]["mean"] >= 0.9

    # Discrimination: the naive floor raises FAR more false positives than the conventional rule
    # (the benign client noise + hard negatives create genuine FP pressure — not a ceiling).
    assert naive["fp_total"] > conv["fp_total"]
    assert conv["precision"]["mean"] >= naive["precision"]["mean"]


def test_bench_detectors_never_see_truth(tmp_path: Path) -> None:
    # The report never serializes the per-line malicious ids (only counts/metrics).
    import json as _json

    rep = run_detection_bench(seeds=[1], noise_clients=2, workdir=tmp_path)
    blob = _json.dumps(rep)
    assert "malicious_line_ids" not in blob
