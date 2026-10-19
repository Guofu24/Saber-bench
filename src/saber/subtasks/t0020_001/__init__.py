"""T0020.001 (CNT, file) — write a detection rule (regex) for a log corpus.

Source scenario: given a log file with N lines, M of which are the technique to catch, write one
regex/rule; the verifier runs the rule and counts. Source scorer: `rule` (exec/corpus) with
aggregate `max(0, M'/M - N'/(N'+M'))`.

The corpus is synthetic HTTP access-log text. Positive lines carry an abstracted path-traversal
marker; benign lines are ordinary requests, some of which are deliberately easy to over-match
(long query strings, encoded but legitimate parameters). The rule runs in the sandboxed regex
engine with a timeout; a rule that fails to compile or times out scores 0.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field

from saber.domain.base import StrictModel
from saber.grading.execsandbox import corpus_metrics, run_regex_rule
from saber.grading.primitives import score_set_delta
from saber.grading.results import ItemScore
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng, iso

_BENIGN_PATHS = (
    "/",
    "/index.html",
    "/api/v1/users",
    "/static/app.js",
    "/login",
    "/search?q=laptop",
    "/cart/add?id=42",
)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0)",
    "Mozilla/5.0 (Macintosh)",
    "curl/8.4.0",
    "python-requests/2.31",
)
# Abstracted traversal markers — representative, not a working exploit against any real target.
_TRAVERSAL = (
    "/files?p=../../../synthetic/marker",
    "/dl?f=..%2f..%2fsynthetic%2fmarker",
    "/view?doc=....//....//marker",
)


class RuleSpec(StrictModel):
    engine: Literal["regex"] = "regex"
    pattern: str = Field(min_length=1, max_length=2000)
    ignore_case: bool = True


class T0020Output(StrictModel):
    rule: RuleSpec


class Subtask(SubtaskBase):
    SUBTASK_ID = "T0020.001"
    OutputModel = T0020Output
    VARIANTS = ("default", "sparse", "noisy")

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        n_total = {"sparse": rng.randint(40, 60), "noisy": rng.randint(80, 120)}.get(
            variant, rng.randint(50, 80)
        )
        m_target = rng.randint(3, 5) if variant == "sparse" else rng.randint(6, 12)
        m_target = min(m_target, n_total // 3)
        host = rng.hostname("web")
        lines: list[str] = []
        positives: list[int] = []
        times = rng.times_sorted(n_total, span_minutes=120)
        for i in range(n_total):
            ts = iso(times[i])
            ip = rng.internal_ip() if rng.chance(0.5) else rng.external_ip()
            ua = rng.pick(_UA)
            lines.append(f'{ts} {ip} GET {rng.pick(_BENIGN_PATHS)} 200 "{ua}"')
        pos_idx = rng.sample(range(n_total), m_target)
        for i in sorted(pos_idx):
            ts = iso(times[i])
            ip = rng.external_ip()
            path = rng.pick(_TRAVERSAL)
            lines[i] = f'{ts} {ip} GET {path} 404 "{rng.pick(_UA)}"'
            positives.append(i)
        # noisy negatives that a naive rule might over-match (long encoded but legit params)
        if variant == "noisy":
            for i in rng.sample(
                [j for j in range(n_total) if j not in positives], min(6, n_total - m_target)
            ):
                ts = iso(times[i])
                lines[i] = (
                    f'{ts} {rng.internal_ip()} GET /report?path=%2Fhome%2Freports%2Fq3.pdf 200 "{rng.pick(_UA)}"'
                )
        corpus = {
            "hv": "HV-02",
            "host": host,
            "format": "ts ip method path status ua",
            "lines": lines,
        }
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={
                "corpus": corpus,
                "objective": "Write a regex matching lines containing a path-traversal marker.",
            },
            sealed_truth={"positive_lines": sorted(positives), "n": n_total, "m": m_target},
            evidence_ids=[f"line-{i}" for i in range(n_total)],
            notes="Rule runs in sandboxed regex engine; parse failure/timeout -> 0.",
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        # A reference regex that matches the abstracted traversal markers.
        return {
            "rule": {
                "engine": "regex",
                "pattern": r"(\.\./|\.\.%2f|\.\.\.\./)",
                "ignore_case": True,
            }
        }

    def _run_rule(
        self, pattern: str, ignore_case: bool, lines: list[str], positives: set[int]
    ) -> tuple[float, dict[str, Any]]:
        res = run_regex_rule(pattern, lines, ignore_case=ignore_case)
        if not res.parse_ok:
            return 0.0, {"parse_ok": False, "error": res.error, "timed_out": res.timed_out}
        matched = set(res.matched)
        matched_pos = [f"line-{i}" for i in matched & positives]
        truth_pos = [f"line-{i}" for i in positives]
        delta = score_set_delta(matched_pos, truth_pos, canon=str)
        # set_delta over matched positives vs truth already encodes M'/M; subtract FP penalty N'/(N'+M')
        m = len(positives)
        m_hit = len(matched & positives)
        n_fp = len(matched - positives)
        second = n_fp / (n_fp + m_hit) if (n_fp + m_hit) else 0.0
        score = max(0.0, (m_hit / m if m else 0.0) - second)
        metrics = corpus_metrics(matched, positives, len(lines))
        metrics.update(
            {
                "parse_ok": True,
                "score_formula": "max(0, M'/M - N'/(N'+M'))",
                "delta_detail": delta.detail(),
            }
        )
        return score, metrics

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        lines = list((ctx.public_inputs or {}).get("corpus", {}).get("lines", []))
        positives = set(truth["positive_lines"])
        score, detail = self._run_rule(
            answer.rule.pattern, answer.rule.ignore_case, lines, positives
        )
        comp = ItemScore(field="rule", score=score, weight=1.0, detail=detail)
        trace = [
            f"rule exec/corpus -> {score:.4f} (tp={detail.get('tp')}, fp={detail.get('fp')}, parse_ok={detail.get('parse_ok')})"
        ]
        return ScoreParts(components=[comp], raw_score=score, trace=trace)

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        return self.answer_from_truth({}), []

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        return [
            GoldenCase(
                "match_nothing",
                {"rule": {"engine": "regex", "pattern": "ZZZ_NO_MATCH_ZZZ", "ignore_case": True}},
                expected_score=0.0,
            ),
            GoldenCase(
                "match_everything",
                {"rule": {"engine": "regex", "pattern": "GET", "ignore_case": True}},
                expected_max=0.5,
            ),
            GoldenCase(
                "bad_regex",
                {"rule": {"engine": "regex", "pattern": "(unclosed", "ignore_case": True}},
                expected_score=0.0,
                expect_trace_contains="parse_ok=False",
            ),
        ]
