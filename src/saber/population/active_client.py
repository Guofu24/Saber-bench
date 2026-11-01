"""A continuously-active benign client: an always-on machine that keeps producing real logs.

Unlike :mod:`saber.population.loop` (which runs discrete red+client+blue *episodes*), this models a
single ordinary machine that is simply *on*: it keeps a loopback range service running and emits
benign traffic on a jittered, day-shaped rhythm until stopped — like a workstation or server quietly
living its day. Its only output is a genuine, growing access log of benign requests; it never attacks
and is not scored.

Engine — HYBRID, and safe by default:

* **Scripted executor (every tick, no LLM, no quota):** samples a small batch of benign requests
  from the current activity profile and sends them to the live service. This runs with NO provider at
  all, so the daemon is fully usable under the subscription-only rule without spending any tokens.
* **LLM profiler (sparse, opt-in):** when an operator-approved provider is supplied, it is called
  only once per ``profile_refresh_s`` window to pick a fresh *activity profile* — a weighted mix over
  benign categories plus an intensity. Between refreshes the scripted executor replays that profile
  with jitter. So an all-day run costs a handful of calls, not one per request, and it degrades to the
  scripted default the moment a provider is absent, out of budget, or returns something unusable.

Benign by construction (asserted by ``tests/population/test_active_client.py``): every category emits
only targets that no scenario's server-side truth-derivation flags — browses/searches, logins with
the valid password (never a 401), SQL-*word* hard negatives, and *authorized* script/cron deploys
(benign content, no webshell/autostart marker). The LLM only ever chooses weights over this fixed set
of categories; it can never introduce a raw request target.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from saber.agents.provider import LLMProvider
from saber.baselines.prompt import extract_answer_json
from saber.domain.errors import BudgetExceeded, IntegrationBlocked
from saber.population.agents import load_playbook
from saber.population.office import ROLE_AGENTS, OfficeEmitter
from saber.range.live.client_driver import (
    _BENIGN_TRICKY,
    _BROWSE_PATHS,
    _CLIENT_USERS,
    _GOOD_PASSWORD,
    _SEARCH_TERMS,
)
from saber.range.live.controlplane import LiveLab, _sha256_bytes
from saber.subtasks._hv.common import Rng

LABELS = ("ACTIVE_CLIENT", "LIVE_RANGE", "DEV_SIMULATION_ONLY")

# Benign activity categories the machine can perform. The LLM picks WEIGHTS over exactly this set;
# every category's generator below is benign by construction, so no weighting can make it malicious.
CATEGORIES: tuple[str, ...] = ("browse", "search", "login", "tricky", "admin_script", "cron_job")

# Authorized (benign) admin artefacts — hard negatives: same shape as an attack, benign content.
_FS_AUTHORIZED = ("health.php", "status.aspx", "api.jsp")
_CRON_AUTHORIZED = ("backup", "logrotate", "updatecheck", "healthprobe")
_ADMIN_ACTORS = ("adm.an", "adm.huy", "adm.minh")

# A sensible default "office machine" mix: mostly web use, a little admin. Used with no LLM, and as
# the fallback whenever the LLM profile is missing/unusable.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "browse": 0.42,
    "search": 0.24,
    "login": 0.18,
    "tricky": 0.08,
    "admin_script": 0.05,
    "cron_job": 0.03,
}
_DEFAULT_INTENSITY = 8.0  # baseline requests/minute at a busy hour
_MIN_INTENSITY, _MAX_INTENSITY = 1.0, 30.0


@dataclass(frozen=True)
class ActivityProfile:
    """What the machine is doing right now: a benign-category mix + intensity (requests/minute)."""

    weights: dict[str, float]
    intensity: float
    source: str  # "scripted-default" | "llm" | "scripted-fallback"
    note: str = ""

    def normalized(self) -> dict[str, float]:
        total = sum(max(0.0, w) for w in self.weights.values())
        if total <= 0:
            return dict(_DEFAULT_WEIGHTS)
        return {k: max(0.0, v) / total for k, v in self.weights.items()}


def scripted_default_profile(intensity: float | None = None) -> ActivityProfile:
    i = (
        _DEFAULT_INTENSITY
        if intensity is None
        else max(_MIN_INTENSITY, min(_MAX_INTENSITY, intensity))
    )
    return ActivityProfile(weights=dict(_DEFAULT_WEIGHTS), intensity=i, source="scripted-default")


def _gen_request(category: str, rng: Rng) -> dict[str, str]:
    """Generate one concrete, benign, loopback request target for a category."""
    if category == "search":
        return {"target": f"/search?q={quote(rng.pick(_SEARCH_TERMS))}", "intent": "benign"}
    if category == "login":
        user = rng.pick(_CLIENT_USERS)
        return {"target": f"/login?user={user}&pass={quote(_GOOD_PASSWORD)}", "intent": "benign"}
    if category == "tricky":
        return {"target": rng.pick(_BENIGN_TRICKY), "intent": "benign"}
    if category == "admin_script":
        name, actor = rng.pick(_FS_AUTHORIZED), rng.pick(_ADMIN_ACTORS)
        return {"target": f"/fs/put?name={name}&actor={actor}", "intent": "benign"}
    if category == "cron_job":
        name, actor = rng.pick(_CRON_AUTHORIZED), rng.pick(_ADMIN_ACTORS)
        return {"target": f"/cron/add?name={name}&actor={actor}", "intent": "benign"}
    return {"target": rng.pick(_BROWSE_PATHS), "intent": "benign"}  # "browse" + safe default


def _weighted_pick(rng: Rng, weights: dict[str, float]) -> str:
    """Pick one category by weight (deterministic given the rng stream)."""
    items = [(c, max(0.0, weights.get(c, 0.0))) for c in CATEGORIES]
    total = sum(w for _, w in items)
    if total <= 0:
        return "browse"
    r = rng.random() * total
    acc = 0.0
    for cat, w in items:
        acc += w
        if r <= acc:
            return cat
    return items[-1][0]


def _count_from_rate(rng: Rng, expected: float) -> int:
    """Turn an expected request count into an integer with a little jitter (deterministic)."""
    expected = max(0.0, expected)
    base = int(expected)
    n = base + (1 if rng.random() < (expected - base) else 0)
    if n > 0 and rng.random() < 0.15:  # occasional small burst
        n += 1
    return n


# Day rhythm: a multiplier on intensity by local hour, so the machine is busy in office hours, quiet
# at lunch and in the evening, and only idling (heartbeats) overnight. "flat" disables shaping.
def phase_multiplier(hour: int, rhythm: str = "real") -> float:
    if rhythm == "flat":
        return 1.0
    if 9 <= hour <= 11 or 14 <= hour <= 16:
        return 1.0  # core working hours
    if hour in (8, 12, 13, 17):
        return 0.6  # arrival / lunch / wind-down
    if 18 <= hour <= 22:
        return 0.3  # evening: occasional use
    return 0.1  # 23:00–07:59 overnight idle (still some automated/background traffic)


def llm_profile(provider: LLMProvider, rng: Rng, *, hour: int) -> ActivityProfile:
    """Ask the provider ONCE for an activity profile. Hard-guarded; never raises on bad output.

    The provider only returns weights over the fixed :data:`CATEGORIES` and an intensity; anything
    off-menu is dropped and the intensity is clamped. On empty/invalid output it falls back to the
    scripted default. (Budget/integration errors propagate so the caller can stop spending.)
    """
    system = (
        load_playbook("client-user")
        + "\n\n---\nYou are ONE ordinary machine in an isolated range, choosing how you will behave "
        "for roughly the next 15 minutes. You never attack. Output the machine answer only."
    )
    cats = ", ".join(CATEGORIES)
    user = (
        f"Local hour is {hour:02d}:00. Pick a realistic benign activity mix for right now.\n"
        f"Categories (weights 0..1, benign by construction): {cats}\n"
        "  browse/search/login = ordinary web use; tricky = benign requests that merely CONTAIN a "
        "SQL word; admin_script/cron_job = AUTHORIZED maintenance (hard negatives).\n"
        "Return ONLY one JSON object:\n"
        '{"weights": {"browse": <w>, ...}, "intensity": <requests/minute 1-30>, "note": "<one line>"}\n'
    )
    resp = provider.generate(
        [{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens=512
    )
    obj, _note = extract_answer_json(resp.text)
    if not isinstance(obj, dict):
        return ActivityProfile(dict(_DEFAULT_WEIGHTS), _DEFAULT_INTENSITY, "scripted-fallback",
                               note="LLM returned no JSON object")  # fmt: skip
    raw_w = obj.get("weights", {})
    weights: dict[str, float] = {}
    if isinstance(raw_w, dict):
        for cat in CATEGORIES:  # keep ONLY known categories; ignore anything invented
            try:
                w = float(raw_w.get(cat, 0.0))
            except (TypeError, ValueError):
                w = 0.0
            if w > 0:
                weights[cat] = w
    if not weights:
        weights = dict(_DEFAULT_WEIGHTS)
    try:
        intensity = float(obj.get("intensity", _DEFAULT_INTENSITY))
    except (TypeError, ValueError):
        intensity = _DEFAULT_INTENSITY
    intensity = max(_MIN_INTENSITY, min(_MAX_INTENSITY, intensity))
    note = str(obj.get("note", ""))[:120]
    return ActivityProfile(weights=weights, intensity=intensity, source="llm", note=note)


@dataclass
class ActiveClientReport:
    """Summary of one active-client run (what it did while alive)."""

    ticks: int
    requests_sent: int
    by_category: dict[str, int]
    log_lines: int
    access_log: str
    access_log_sha256: str
    profiles_used: list[dict[str, Any]]
    llm_calls: int
    reset_ok: bool
    labels: list[str] = field(default_factory=lambda: list(LABELS))
    note: str = ""

    def row(self) -> dict[str, Any]:
        return asdict(self)


def run_active_client(
    provider: LLMProvider | None = None,
    *,
    workdir: Path,
    seed: int = 1,
    base_interval_s: float = 20.0,
    base_intensity: float | None = None,
    profile_refresh_s: float = 900.0,
    rhythm: str = "real",
    max_ticks: int | None = None,
    stop_file: Path | None = None,
    emitter: OfficeEmitter | None = None,
    on_tick: Callable[[int, dict[str, Any]], None] | None = None,
    clock: Callable[[], float] | None = None,
    hour_fn: Callable[[], int] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> ActiveClientReport:
    """Run one always-on benign machine against a live loopback range until stopped.

    Stops on: a ``stop_file`` appearing, ``max_ticks`` reached (for tests/demos), KeyboardInterrupt,
    or — when an LLM provider is used — its billable-call budget (the daemon then keeps running
    scripted-only). ``provider=None`` (the default) is pure scripted: no LLM, no quota.

    The ``clock`` / ``hour_fn`` / ``sleep_fn`` hooks are injectable so the loop is deterministically
    testable without real time.
    """
    clock = clock or time.monotonic
    hour_fn = hour_fn or (lambda: datetime.now().hour)  # local hour drives the day rhythm
    sleep_fn = sleep_fn or time.sleep
    base = Path(workdir)
    evidence_dir = base / "active-client"
    import shutil

    if evidence_dir.exists():
        shutil.rmtree(evidence_dir, ignore_errors=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    rng = Rng("active-client", str(seed))
    em = emitter or OfficeEmitter()
    em.agent("client", *ROLE_AGENTS["client"])
    em.agent("range", *ROLE_AGENTS["range"])
    model = getattr(provider, "model_id", "scripted") if provider is not None else "scripted"
    em.message(
        "client", f"=== Active client online (seed {seed}, {rhythm} rhythm, model={model}) ==="
    )

    lab = LiveLab(
        evidence_dir, fs_root=evidence_dir / "webroot", cron_root=evidence_dir / "cronroot"
    )
    lab.start()
    em.status("range", "idle")

    profile = scripted_default_profile(base_intensity)
    profiles_used: list[dict[str, Any]] = [{"tick": 0, **_profile_row(profile)}]
    by_category: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    requests_sent = 0
    llm_calls = 0
    last_refresh: float | None = None
    tick = 0
    note = ""

    try:
        while True:
            if max_ticks is not None and tick >= max_ticks:
                break
            if stop_file is not None and Path(stop_file).exists():
                note = f"stopped: stop file present ({stop_file})"
                break
            now = clock()
            hour = int(hour_fn())

            # Sparse LLM refresh of the activity profile (hybrid). Degrades to scripted on budget/block.
            if provider is not None and (
                last_refresh is None or (now - last_refresh) >= profile_refresh_s
            ):
                em.status("client", "think")
                em.llm_start("client", model)
                try:
                    profile = llm_profile(provider, rng, hour=hour)
                    llm_calls += 1
                    last_refresh = now
                    profiles_used.append({"tick": tick, **_profile_row(profile)})
                    em.llm_end("client", 0, f"profile: {profile.source} i={profile.intensity:.0f}",
                               {"in": 0, "out": 0})  # fmt: skip
                except BudgetExceeded:
                    provider = None  # permanent: keep living, scripted-only
                    profile = scripted_default_profile(base_intensity)
                    profiles_used.append({"tick": tick, "source": "budget-exhausted",
                                          "intensity": profile.intensity, "note": "LLM off; scripted"})  # fmt: skip
                    em.message("client", "LLM budget reached — continuing scripted-only")
                except IntegrationBlocked as exc:
                    last_refresh = now  # try again next window; keep current scripted/last profile
                    profiles_used.append({"tick": tick, "source": "blocked-transient",
                                          "intensity": profile.intensity, "note": str(exc)[:80]})  # fmt: skip
                    em.message("client", f"LLM temporarily blocked: {str(exc)[:60]}")

            # Scripted executor: sample and send this tick's benign batch.
            phase = phase_multiplier(hour, rhythm)
            expected = profile.intensity * phase * (base_interval_s / 60.0)
            n = _count_from_rate(rng, expected)
            picks = [_weighted_pick(rng, profile.normalized()) for _ in range(n)]
            plan = [_gen_request(c, rng) for c in picks]
            plan = [r for r in plan if str(r["target"]).startswith("/")]  # loopback-path guard
            em.status("client", "tool", "🔧 send_benign")
            sent = lab.send(plan) if plan else 0
            for c in picks:
                by_category[c] += 1
            requests_sent += sent
            if plan:
                em.handoff("client", "range", "benign_traffic")
            em.status("client", "idle")

            tick += 1
            stats = {
                "tick": tick, "hour": hour, "phase": round(phase, 2), "sent": sent,
                "requests_sent": requests_sent, "profile_source": profile.source,
                "intensity": round(profile.intensity, 1), "llm_calls": llm_calls,
            }  # fmt: skip
            if on_tick is not None:
                on_tick(tick, stats)

            jitter = base_interval_s * (0.6 + 0.8 * rng.random())  # 0.6x .. 1.4x
            sleep_fn(jitter)
    except KeyboardInterrupt:  # pragma: no cover - interactive stop path
        note = "stopped: KeyboardInterrupt"
    finally:
        lab.stop()
        reset_ok = lab.confirm_reset()

    raw_lines = lab.read_log_lines()
    log_bytes = lab.access_log.read_bytes() if lab.access_log.exists() else b""
    em.message("client", f"Active client offline · {tick} ticks · {requests_sent} benign requests")
    return ActiveClientReport(
        ticks=tick,
        requests_sent=requests_sent,
        by_category=by_category,
        log_lines=len(raw_lines),
        access_log=str(lab.access_log),
        access_log_sha256=_sha256_bytes(log_bytes),
        profiles_used=profiles_used,
        llm_calls=llm_calls,
        reset_ok=reset_ok,
        note=note,
    )


def _profile_row(p: ActivityProfile) -> dict[str, Any]:
    return {"source": p.source, "intensity": round(p.intensity, 2),
            "weights": {k: round(v, 3) for k, v in p.normalized().items()}, "note": p.note}  # fmt: skip
