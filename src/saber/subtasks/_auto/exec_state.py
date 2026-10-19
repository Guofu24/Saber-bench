"""Exec-corpus and VM-state handlers for AutoSubtask (reuse sandbox + action-model verifier)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from saber.catalog.models import AggregateKind, ScoreItemKind
from saber.grading.canonical import canonicalizer_for
from saber.grading.execsandbox import corpus_metrics, run_regex_rule
from saber.grading.primitives import delta_fp_tp, score_set, tpr_minus_fpr
from saber.grading.results import GateOutcome, ItemScore
from saber.grading.state import (
    MachineSnapshot,
    all_removed,
    clean_intact,
    config_restored,
    machine_unchanged,
    service_alive,
)
from saber.subtasks._framework import FixtureBundle, GoldenCase, GradeContext, ScoreParts
from saber.subtasks._hv.common import Rng, iso
from saber.subtasks._vm import (
    GuestAction,
    apply_actions,
    file_state,
    now_iso,
    snapshot_from_files,
    snapshot_to_public,
)

if TYPE_CHECKING:
    from saber.subtasks._auto.engine import AutoSubtask

_MARK_TP = "SYNTH_TECHNIQUE_MARKER"
_MARK_FP = "SYNTH_BENIGN_LOOKALIKE"
_WEB_CONFIG = "/etc/app/server.conf"
_WEB_INDEX = "/srv/www/index.page"
_CLEAN = ("/srv/www/app.page", "/etc/app/config.ini")


# ========================================================================= EXEC


def build_exec_fixture(st: AutoSubtask, rng: Rng, seed: int, variant: str) -> FixtureBundle:
    n = rng.randint(50, 90)
    m = rng.randint(6, 12)
    is_filter = st._agg.kind is AggregateKind.DELTA_FP_TP
    lines: list[str] = []
    tp_idx: list[int] = []
    fp_idx: list[int] = []
    pos = set(rng.sample(range(n), m))
    fps = set(rng.sample([i for i in range(n) if i not in pos], m)) if is_filter else set()
    for i in range(n):
        if i in pos:
            lines.append(f"{iso(rng.time())} event {_MARK_TP} id={i}")
            tp_idx.append(i)
        elif i in fps:
            lines.append(f"{iso(rng.time())} event {_MARK_FP} id={i}")
            fp_idx.append(i)
        else:
            lines.append(f"{iso(rng.time())} event normal id={i}")
    return FixtureBundle(
        subtask_id=st.SUBTASK_ID,
        seed=seed,
        variant=variant,
        episode_id=st.episode_id_for(seed, variant),
        public_inputs={
            "corpus": {"lines": lines, "format": "ts event tag id"},
            "objective": "write a regex rule matching the technique lines",
            "mode": "filter" if is_filter else "detect",
        },
        sealed_truth={"positives": sorted(tp_idx), "false_positives": sorted(fp_idx), "n": n},
        evidence_ids=[f"line-{i}" for i in range(n)],
        notes="STRUCTURAL synthetic corpus; rule runs in the sandboxed regex engine.",
    )


def exec_answer_from_truth(st: AutoSubtask, truth: Mapping[str, Any]) -> dict[str, Any]:
    pat = _MARK_FP if st._agg.kind is AggregateKind.DELTA_FP_TP else _MARK_TP
    return {"rule": {"engine": "regex", "pattern": pat, "ignore_case": True}}


def exec_reference(
    st: AutoSubtask, public_inputs: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    pat = _MARK_FP if public_inputs.get("mode") == "filter" else _MARK_TP
    return {"rule": {"engine": "regex", "pattern": pat, "ignore_case": True}}, []


def exec_score(
    st: AutoSubtask, answer: Any, truth: Mapping[str, Any], ctx: GradeContext
) -> ScoreParts:
    lines = list((ctx.public_inputs or {}).get("corpus", {}).get("lines", []))
    rule = answer.model_dump().get("rule") or {}
    pattern = str(rule.get("pattern", ""))
    res = run_regex_rule(pattern, lines, ignore_case=bool(rule.get("ignore_case", True)))
    if not res.parse_ok:
        return ScoreParts(
            components=[
                ItemScore(
                    field="rule",
                    score=0.0,
                    weight=1.0,
                    detail={"parse_ok": False, "error": res.error},
                )
            ],
            raw_score=0.0,
            trace=["parse_ok=False"],
        )
    matched = set(res.matched)
    pos = set(truth["positives"])
    if st._agg.kind is AggregateKind.DELTA_FP_TP:
        fps = set(truth["false_positives"])
        fp_removed = len(matched & fps)
        tp_lost = len(matched & pos)
        score, detail = delta_fp_tp(
            fp_before=len(fps),
            fp_after=len(fps) - fp_removed,
            tp_before=len(pos),
            tp_after=len(pos) - tp_lost,
        )
    elif st._agg.kind is AggregateKind.TPR_MINUS_FPR:
        m = corpus_metrics(matched, pos, len(lines))
        score, detail = tpr_minus_fpr(tp=m["tp"], fn=m["fn"], fp=m["fp"], tn=m["tn"])
    else:  # exec item under a set-delta-style aggregate
        mhit = len(matched & pos)
        nfp = len(matched - pos)
        second = nfp / (nfp + mhit) if (nfp + mhit) else 0.0
        score = max(0.0, (mhit / len(pos) if pos else 0.0) - second)
        detail = corpus_metrics(matched, pos, len(lines))
    return ScoreParts(
        components=[ItemScore(field="rule", score=score, weight=1.0, detail=detail)],
        raw_score=score,
        trace=[f"rule exec -> {score:.4f}"],
    )


# ========================================================================= STATE


def _is_removal(st: AutoSubtask) -> bool:
    return any(
        k in i.field.lower()
        for i in st._items
        for k in ("removed", "gone", "biến", "eradic", "all_6")
    )


def build_state_fixture(st: AutoSubtask, rng: Rng, seed: int, variant: str) -> FixtureBundle:
    mid = rng.hostname("srv")
    taken = now_iso(rng)
    files = {}
    for p in (_WEB_CONFIG, _WEB_INDEX, *_CLEAN):
        files[p] = file_state(rng, p, tag=f"clean:{p}")
    m = rng.randint(3, 6)
    malicious = [f"/tmp/.synth/{rng.hexid('m', 4)}_{i}" for i in range(m)]
    mal_hashes = []
    for p in malicious:
        fs = file_state(rng, p, tag=f"mal:{p}")
        files[p] = fs
        mal_hashes.append(fs.sha256)
    before = snapshot_from_files(mid, files, taken_at=taken, users=["root", "www"])
    # observation set items (non-gate sets) → truth = malicious hashes by default
    obs_truth: dict[str, Any] = {}
    for item, name in zip(st._items, st._field_names, strict=True):
        if item.kind is ScoreItemKind.SET:
            obs_truth[name] = list(mal_hashes)
    public = {
        "machine": snapshot_to_public(before),
        "clean_baseline_paths": [_WEB_CONFIG, *_CLEAN],
        "objective": "observe and/or remediate; keep clean files, config and service intact",
        "scored_fields": list(obs_truth),
    }
    return FixtureBundle(
        subtask_id=st.SUBTASK_ID,
        seed=seed,
        variant=variant,
        episode_id=st.episode_id_for(seed, variant),
        public_inputs=public,
        sealed_truth={
            "malicious_paths": malicious,
            "malicious_hashes": mal_hashes,
            "clean_paths": [_WEB_CONFIG, _WEB_INDEX, *_CLEAN],
            "config_paths": [_WEB_CONFIG],
            "machine_before": before.model_dump(mode="json"),
            "taken_at": taken,
            "observations": obs_truth,
            "removal": _is_removal(st),
        },
        evidence_ids=list(mal_hashes),
        notes="STRUCTURAL synthetic VM snapshot; state gates verified from declared actions (DEV).",
    )


def _before(truth: Mapping[str, Any]) -> MachineSnapshot:
    return MachineSnapshot.model_validate(truth["machine_before"])


def state_answer_from_truth(st: AutoSubtask, truth: Mapping[str, Any]) -> dict[str, Any]:
    actions = (
        [{"op": "remove", "path": p} for p in truth["malicious_paths"]]
        if truth.get("removal")
        else []
    )
    return {"actions": actions, "observations": dict(truth.get("observations", {}))}


def state_reference(
    st: AutoSubtask, public_inputs: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    machine = public_inputs.get("machine", {})
    mal = [
        meta["sha256"]
        for path, meta in machine.get("files", {}).items()
        if path.startswith("/tmp/")
    ]
    obs = {name: list(mal) for name in public_inputs.get("scored_fields", [])}
    mal_paths = [path for path in machine.get("files", {}) if path.startswith("/tmp/")]
    removal = any(
        k in i.field.lower() for i in st._items for k in ("removed", "gone", "biến", "all_6")
    )
    actions = [{"op": "remove", "path": p} for p in mal_paths] if removal else []
    return {"actions": actions, "observations": obs}, list(mal)


def state_score(
    st: AutoSubtask, answer: Any, truth: Mapping[str, Any], ctx: GradeContext
) -> ScoreParts:
    before = _before(truth)
    data = answer.model_dump()
    actions = [GuestAction.model_validate(a) for a in data.get("actions", [])]
    after = apply_actions(before, actions, taken_at=truth["taken_at"])
    comps: list[ItemScore] = []
    gates: list[GateOutcome] = []
    obs = data.get("observations", {})
    for item, name in zip(st._items, st._field_names, strict=True):
        fname = item.field.lower()
        if item.kind is ScoreItemKind.SET:
            res = score_set(
                obs.get(name),
                truth.get("observations", {}).get(name),
                canon=canonicalizer_for(item.subtype),
                beta=item.beta or 1.0,
            )
            comps.append(
                ItemScore(field=name, score=res.score, weight=item.weight, detail=res.detail())
            )
        elif item.kind in (ScoreItemKind.STATE, ScoreItemKind.GATE):
            gates.append(_state_gate(name, fname, before, after, truth))
    raw = _state_raw(st, comps)
    return ScoreParts(
        components=[_c for _c in comps],
        gates=gates,
        raw_score=raw,
        trace=[f"{c.field}={c.score:.3f}" for c in comps]
        + [f"gate {g.name}={g.passed}" for g in gates],
    )


def _state_gate(
    name: str, fname: str, before: MachineSnapshot, after: MachineSnapshot, truth: Mapping[str, Any]
) -> GateOutcome:
    if any(k in fname for k in ("removed", "gone", "biến", "all_6")):
        g, _ = all_removed(before, after, truth["malicious_paths"], name=name)
        return g
    if any(k in fname for k in ("unchanged", "không đổi", "machine")):
        return machine_unchanged(before, after, name=name)
    if any(k in fname for k in ("config", "restored", "khôi")):
        return config_restored(before, after, truth["config_paths"], name=name)
    if any(k in fname for k in ("alive", "service", "http", "sống")):

        def probe() -> bool:
            cfg = after.files.get(_WEB_CONFIG)
            base = before.files.get(_WEB_CONFIG)
            return (
                cfg is not None
                and base is not None
                and cfg.sha256 == base.sha256
                and _WEB_INDEX in after.files
            )

        return service_alive(probe, name=name)
    # default: clean/evidence intact
    return clean_intact(before, after, truth["clean_paths"], name=name)


def _state_raw(st: AutoSubtask, comps: list[ItemScore]) -> float:
    if st._agg.kind is AggregateKind.PRODUCT_GATES:
        return 1.0  # gates multiply; no weighted base
    if not comps:
        return 1.0
    total_w = sum(c.weight or 0.0 for c in comps) or 1.0
    raw = sum((c.weight or 0.0) * c.score for c in comps) / total_w
    for c in comps:
        c.weight = None
    return raw


# ========================================================================= golden


def golden_cases(st: AutoSubtask, bundle: FixtureBundle) -> list[GoldenCase]:
    if st._exec_mode:
        return [
            GoldenCase(
                "match_nothing",
                {"rule": {"engine": "regex", "pattern": "ZZZ_NOPE", "ignore_case": True}},
                expected_max=0.1,
            ),
            GoldenCase(
                "bad_regex",
                {"rule": {"engine": "regex", "pattern": "(unclosed", "ignore_case": True}},
                expected_score=0.0,
                expect_trace_contains="parse_ok=False",
            ),
        ]
    # state: a destructive mutation should fail any machine_unchanged gate; empty obs scores low.
    t = bundle.sealed_truth
    before = _before(t)
    victim = next(iter(before.files))
    cases = [GoldenCase("empty", {"actions": [], "observations": {}}, expected_max=0.6)]
    if not t.get("removal"):
        cases.append(
            GoldenCase(
                "mutated",
                {
                    "actions": [{"op": "remove", "path": victim}],
                    "observations": t.get("observations", {}),
                },
                expected_max=0.999,
            )
        )
    return cases
