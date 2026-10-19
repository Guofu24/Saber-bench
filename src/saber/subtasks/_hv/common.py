"""Deterministic randomness and naming helpers shared by HV generators.

Pure, side-effect free, seeded. The same (seed, parts) always yields the same stream, which is
what makes DEV fixtures reproducible and hashable.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TypeVar

T = TypeVar("T")

BASE_TIME = datetime(2026, 10, 17, 1, 0, tzinfo=UTC)

HOST_PREFIXES = ("ws", "lt", "srv", "db", "web", "app", "dc", "fs", "jump", "vpn")
DEPARTMENTS = ("fin", "hr", "it", "ops", "sales", "legal", "dev", "mkt")
FIRST_NAMES = (
    "an", "binh", "chi", "dung", "giang", "hanh", "huy", "khanh", "linh",
    "minh", "nam", "phuong", "quang", "thao", "trang", "tuan", "vy", "yen",
)  # fmt: skip
# Benign OS/application processes commonly seen in telemetry.
SYSTEM_PROCESSES = (
    "svchost.exe", "lsass.exe", "csrss.exe", "explorer.exe", "winlogon.exe", "services.exe",
    "spoolsv.exe", "wininit.exe", "smss.exe", "taskhostw.exe", "dwm.exe", "RuntimeBroker.exe",
    "SearchIndexer.exe", "conhost.exe", "msedge.exe", "chrome.exe", "outlook.exe", "teams.exe",
)  # fmt: skip
# Legitimate administration tools (benign, but frequently flagged) — used for hard negatives.
ADMIN_TOOLS = (
    "PsExec.exe",
    "wmic.exe",
    "schtasks.exe",
    "sc.exe",
    "net.exe",
    "reg.exe",
    "certutil.exe",
)
# Inert placeholder family names for synthetic "flagged" artefacts; not real malware.
INERT_FAMILIES = ("LabBeacon", "TestLoader", "SynthStealer", "MockMiner", "FakeRat", "DemoShell")


class Rng:
    """Thin wrapper over random.Random with domain helpers; same seed -> same stream."""

    def __init__(self, seed: int | str, *parts: str) -> None:
        material = "|".join([str(seed), *parts]).encode("utf-8")
        self._r = random.Random(int.from_bytes(hashlib.sha256(material).digest()[:8], "big"))
        self._hosts: dict[str, int] = {}

    @property
    def raw(self) -> random.Random:
        return self._r

    def pick(self, items: Sequence[T]) -> T:
        return self._r.choice(list(items))

    def sample(self, items: Sequence[T], k: int) -> list[T]:
        pool = list(items)
        return self._r.sample(pool, min(k, len(pool)))

    def shuffle(self, items: list[T]) -> list[T]:
        out = list(items)
        self._r.shuffle(out)
        return out

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def random(self) -> float:
        return self._r.random()

    def chance(self, p: float) -> bool:
        return self._r.random() < p

    def hostname(self, prefix: str | None = None) -> str:
        pre = prefix or self.pick(HOST_PREFIXES)
        n = self._hosts.get(pre, 0) + 1
        self._hosts[pre] = n
        return f"{pre}-{self.pick(DEPARTMENTS)}-{n:02d}"

    def username(self) -> str:
        return f"{self.pick(FIRST_NAMES)}.{self.pick(FIRST_NAMES)[0]}{self.randint(1, 99)}"

    def internal_ip(self, subnet: str = "10.20") -> str:
        return f"{subnet}.{self.randint(0, 31)}.{self.randint(2, 250)}"

    def external_ip(self) -> str:
        # TEST-NET ranges (RFC 5737) so no real routable address is ever referenced.
        block = self.pick(("192.0.2", "198.51.100", "203.0.113"))
        return f"{block}.{self.randint(1, 254)}"

    def sha256(self, tag: str = "") -> str:
        return hashlib.sha256(f"{tag}:{self._r.getrandbits(64)}".encode()).hexdigest()

    def hexid(self, prefix: str, n: int = 6) -> str:
        return f"{prefix}-{self._r.getrandbits(4 * n):0{n}x}"

    def domain(self, *, suspicious: bool = False) -> str:
        if suspicious:
            label = "".join(
                self.pick("abcdefghijklmnopqrstuvwxyz0123456789")
                for _ in range(self.randint(10, 18))
            )
            return f"{label}.{self.pick(('xyz', 'top', 'icu', 'click', 'example'))}"
        return f"{self.pick(('cdn', 'api', 'static', 'mail', 'update'))}.{self.pick(('corp-lab.example', 'vendor-lab.example'))}"

    def time(
        self, base: datetime = BASE_TIME, *, min_minutes: int = 0, max_minutes: int = 600
    ) -> datetime:
        return base + timedelta(
            minutes=self.randint(min_minutes, max_minutes), seconds=self.randint(0, 59)
        )

    def times_sorted(
        self, n: int, base: datetime = BASE_TIME, span_minutes: int = 600
    ) -> list[datetime]:
        span = max(1, span_minutes * 60)
        if n <= span:
            offsets = sorted(self._r.sample(range(span), n))
        else:
            offsets = sorted(self.randint(0, span) for _ in range(n))
        return [base + timedelta(seconds=o) for o in offsets]


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def deterministic_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
