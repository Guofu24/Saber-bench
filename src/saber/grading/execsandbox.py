"""Sandboxed execution of agent-authored detection content (`exec/*` items).

Rules run in a separate interpreter (`python -I -S`) with stdin JSON, no file or network
access by construction (the runner only uses `re`, `json`, `base64`), a wall-clock timeout and a
pattern-size cap. Timeout or parse failure yields `parse_ok=False` (source: score 0).

Engines (DEV): `regex` (Python re, one line = one record), `yara_subset` (strings + condition),
`filter` (structured condition DSL evaluated in-process, no code execution).
Real YARA / Suricata / vendor SIEM compilers are BLOCKED_INTEGRATION adapters.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import Field, field_validator

from saber.domain.base import StrictModel

MAX_PATTERN_LEN = 2000
MAX_INPUT_BYTES = 50_000_000
DEFAULT_TIMEOUT_S = 5.0

_RUNNER = r"""
import json, re, sys, base64
req = json.loads(sys.stdin.read())
engine = req["engine"]
out = {"ok": True, "matched": [], "error": None}
try:
    if engine == "regex":
        flags = re.IGNORECASE if req.get("ignore_case") else 0
        rx = re.compile(req["pattern"], flags)
        out["matched"] = [i for i, line in enumerate(req["lines"]) if rx.search(line)]
    elif engine == "yara_subset":
        strings = req["strings"]
        cond = req["condition"]
        samples = [base64.b64decode(s) for s in req["samples_b64"]]
        compiled = {}
        for name, spec in strings.items():
            kind = spec.get("kind", "text")
            if kind == "text":
                needle = spec["value"].encode("utf-8")
                compiled[name] = ("bytes", needle.lower() if spec.get("nocase") else needle, bool(spec.get("nocase")))
            elif kind == "hex":
                compiled[name] = ("bytes", bytes.fromhex(spec["value"].replace(" ", "")), False)
            elif kind == "regex":
                compiled[name] = ("regex", re.compile(spec["value"].encode("utf-8"), re.IGNORECASE if spec.get("nocase") else 0), False)
            else:
                raise ValueError("unknown string kind " + str(kind))
        def hits(data):
            found = set()
            lowered = None
            for name, (kind, needle, nocase) in compiled.items():
                if kind == "bytes":
                    hay = data
                    if nocase:
                        if lowered is None:
                            lowered = data.lower()
                        hay = lowered
                    if needle in hay:
                        found.add(name)
                else:
                    if needle.search(data):
                        found.add(name)
            return found
        n_total = len(compiled)
        def satisfied(found):
            c = cond.strip().lower()
            if c in ("any of them", "any"):
                return len(found) > 0
            if c in ("all of them", "all"):
                return len(found) == n_total and n_total > 0
            m = re.match(r"^(\d+)\s+of\s+them$", c)
            if m:
                return len(found) >= int(m.group(1))
            m = re.match(r"^(\d+)\s+of\s+\(([^)]*)\)$", c)
            if m:
                names = [x.strip() for x in m.group(2).split(",") if x.strip()]
                return len([x for x in names if x in found]) >= int(m.group(1))
            if c.startswith("$") and " " not in c:
                return c in found
            if " and " in c or " or " in c:
                tokens = re.findall(r"\$\w+|and|or|not|\(|\)", c)
                expr = " ".join(("True" if t in found else "False") if t.startswith("$") else t for t in tokens)
                if not re.fullmatch(r"[True False andornot()]+", expr):
                    raise ValueError("unsupported condition")
                return bool(eval(expr, {"__builtins__": {}}, {}))
            raise ValueError("unsupported condition")
        out["matched"] = [i for i, s in enumerate(samples) if satisfied(hits(s))]
    else:
        raise ValueError("unknown engine")
except Exception as exc:
    out = {"ok": False, "matched": [], "error": type(exc).__name__ + ": " + str(exc)[:200]}
sys.stdout.write(json.dumps(out))
"""


@dataclass
class ExecResult:
    engine: str
    parse_ok: bool
    timed_out: bool
    matched: list[int] = field(default_factory=list)
    error: str | None = None
    duration_s: float = 0.0
    labels: list[str] = field(default_factory=lambda: ["DEV_SANDBOX"])

    def detail(self) -> dict[str, Any]:
        return {
            "engine": self.engine, "parse_ok": self.parse_ok, "timed_out": self.timed_out,
            "matched_count": len(self.matched), "error": self.error, "duration_s": round(self.duration_s, 4),
        }  # fmt: skip


def _rlimit_preexec() -> Any:
    """Best-effort CPU/address-space caps for the sandbox child (POSIX only; no-op elsewhere)."""
    import os

    if os.name != "posix":
        return None
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return None

    setrlimit = resource.setrlimit  # type: ignore[attr-defined]
    rlimit_cpu = resource.RLIMIT_CPU  # type: ignore[attr-defined]
    rlimit_as = resource.RLIMIT_AS  # type: ignore[attr-defined]

    def _apply() -> None:  # pragma: no cover - runs in the child before exec
        setrlimit(rlimit_cpu, (6, 6))
        gigabyte = 1024 * 1024 * 1024
        setrlimit(rlimit_as, (gigabyte, gigabyte))

    return _apply


def _run(payload: dict[str, Any], *, timeout_s: float) -> ExecResult:
    engine = str(payload.get("engine"))
    data = json.dumps(payload).encode("utf-8")
    if len(data) > MAX_INPUT_BYTES:
        return ExecResult(engine=engine, parse_ok=False, timed_out=False, error="input too large")
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-S", "-c", _RUNNER],
            input=data, capture_output=True, timeout=timeout_s, check=False,
            env={"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0", "SYSTEMROOT": _systemroot()},
            preexec_fn=_rlimit_preexec(),
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        return ExecResult(
            engine=engine,
            parse_ok=False,
            timed_out=True,
            error="timeout",
            duration_s=time.perf_counter() - start,
        )
    duration = time.perf_counter() - start
    if proc.returncode != 0:
        return ExecResult(
            engine=engine,
            parse_ok=False,
            timed_out=False,
            error=f"runner exit {proc.returncode}",
            duration_s=duration,
        )
    try:
        out = json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        return ExecResult(
            engine=engine,
            parse_ok=False,
            timed_out=False,
            error="runner produced no JSON",
            duration_s=duration,
        )
    return ExecResult(
        engine=engine, parse_ok=bool(out.get("ok")), timed_out=False,
        matched=[int(i) for i in out.get("matched", [])], error=out.get("error"), duration_s=duration,
    )  # fmt: skip


def _systemroot() -> str:
    import os

    return os.environ.get("SYSTEMROOT", "")


def run_regex_rule(
    pattern: str,
    lines: Sequence[str],
    *,
    ignore_case: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ExecResult:
    if not isinstance(pattern, str) or not pattern.strip():
        return ExecResult(engine="regex", parse_ok=False, timed_out=False, error="empty pattern")
    if len(pattern) > MAX_PATTERN_LEN:
        return ExecResult(engine="regex", parse_ok=False, timed_out=False, error="pattern too long")
    return _run(
        {"engine": "regex", "pattern": pattern, "lines": list(lines), "ignore_case": ignore_case},
        timeout_s=timeout_s,
    )


class YaraString(StrictModel):
    kind: Literal["text", "hex", "regex"] = "text"
    value: str = Field(min_length=1, max_length=MAX_PATTERN_LEN)
    nocase: bool = False


class YaraSubsetRule(StrictModel):
    """`saber-yara-subset`: named strings and a condition (any/all/N of them/boolean of $names)."""

    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    strings: dict[str, YaraString] = Field(min_length=1, max_length=64)
    condition: str = Field(min_length=1, max_length=512)

    @field_validator("strings")
    @classmethod
    def _names(cls, value: dict[str, YaraString]) -> dict[str, YaraString]:
        for key in value:
            if not key.startswith("$") or len(key) < 2:
                raise ValueError("string identifiers must start with $")
        return value


def run_yara_subset(
    rule: YaraSubsetRule | Mapping[str, Any],
    samples: Sequence[bytes],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ExecResult:
    import base64

    try:
        model = rule if isinstance(rule, YaraSubsetRule) else YaraSubsetRule.model_validate(rule)
    except Exception as exc:  # noqa: BLE001 - validation failure is a parse failure, score 0
        return ExecResult(
            engine="yara_subset",
            parse_ok=False,
            timed_out=False,
            error=f"invalid rule: {type(exc).__name__}",
        )
    payload = {
        "engine": "yara_subset",
        "strings": {k: v.model_dump() for k, v in model.strings.items()},
        "condition": model.condition,
        "samples_b64": [base64.b64encode(s).decode("ascii") for s in samples],
    }
    return _run(payload, timeout_s=timeout_s)


def corpus_metrics(matched: Iterable[int], positives: Iterable[int], total: int) -> dict[str, Any]:
    m, p = set(matched), set(positives)
    tp = len(m & p)
    fp = len(m - p)
    fn = len(p - m)
    tn = max(0, total - tp - fp - fn)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "total": total}


# ----------------------------------------------------------------------- filter DSL

FilterOp = Literal[
    "eq",
    "ne",
    "in",
    "not_in",
    "contains",
    "not_contains",
    "gte",
    "lte",
    "regex",
    "exists",
    "missing",
]


class FilterCondition(StrictModel):
    field: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.]+$")
    op: FilterOp
    value: str | int | float | bool | list[str | int | float | bool] | None = None


class FilterExpr(StrictModel):
    """Suppression filter: a record is filtered when all `all_of` hold and (if given) any `any_of` holds."""

    all_of: list[FilterCondition] = Field(default_factory=list, max_length=32)
    any_of: list[FilterCondition] = Field(default_factory=list, max_length=32)


def _get(record: Mapping[str, Any], dotted: str) -> Any:
    cur: Any = record
    for part in dotted.split("."):
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _cond(record: Mapping[str, Any], c: FilterCondition) -> bool:
    import re

    v = _get(record, c.field)
    if c.op == "exists":
        return v is not None
    if c.op == "missing":
        return v is None
    if c.op == "eq":
        return v is not None and str(v).lower() == str(c.value).lower()
    if c.op == "ne":
        return v is None or str(v).lower() != str(c.value).lower()
    if c.op in {"in", "not_in"}:
        values = c.value if isinstance(c.value, list) else [c.value]
        hit = v is not None and str(v).lower() in {str(x).lower() for x in values}
        return hit if c.op == "in" else not hit
    if c.op in {"contains", "not_contains"}:
        hit = v is not None and str(c.value).lower() in str(v).lower()
        return hit if c.op == "contains" else not hit
    if c.op in {"gte", "lte"}:
        try:
            fv, cv = float(v), float(c.value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return fv >= cv if c.op == "gte" else fv <= cv
    if c.op == "regex":
        if v is None or not isinstance(c.value, str) or len(c.value) > MAX_PATTERN_LEN:
            return False
        try:
            return re.search(c.value, str(v), re.IGNORECASE) is not None
        except re.error:
            return False
    return False


def evaluate_filter(
    expr: FilterExpr | Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> tuple[list[bool], bool]:
    """Returns (filtered_flags, parse_ok). A filtered record is suppressed by the proposed filter."""
    try:
        model = expr if isinstance(expr, FilterExpr) else FilterExpr.model_validate(expr)
    except Exception:  # noqa: BLE001
        return [False] * len(records), False
    flags: list[bool] = []
    for rec in records:
        ok_all = all(_cond(rec, c) for c in model.all_of)
        ok_any = any(_cond(rec, c) for c in model.any_of) if model.any_of else True
        flags.append(ok_all and ok_any and bool(model.all_of or model.any_of))
    return flags, True
