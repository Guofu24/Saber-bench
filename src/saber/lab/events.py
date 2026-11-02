"""Sensor events and a durable delivery queue; evidence is never a model verdict."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from saber.lab.ledger import Ledger, now
from saber.lab.transport import request


class SensorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    ts: str
    host: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    sensor: str = Field(max_length=80)
    data: dict[str, Any]

    @field_validator("ts")
    @classmethod
    def timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("Sensor timestamps require timezone")
        return parsed.astimezone(UTC).isoformat(timespec="milliseconds")

    @field_validator("data")
    @classmethod
    def bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value)) > 16384:
            raise ValueError("Evidence metadata too large")
        return value


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if any(
                s in k.lower() for s in ("password", "token", "authorization", "api_key", "secret")
            )
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"AIza[\w-]{25,}", "[REDACTED]", value)
        return re.sub(
            r"(?i)((?:password|token|api[_-]?key|secret)[\s=:]+)\S+", r"\1[REDACTED]", value
        )[:4096]
    return value


class Emitter:
    def __init__(self, ledger: Ledger, host: str, collector: str, token: str) -> None:
        self.ledger, self.host, self.collector, self.token = ledger, host, collector, token
        self.stopping = threading.Event()
        self.thread: threading.Thread | None = None

    def emit(self, kind: str, data: dict[str, Any], sensor: str = "saber-service-v1") -> str:
        event = SensorEvent(
            id=str(uuid.uuid4()),
            ts=now(),
            host=self.host,
            kind=kind,
            sensor=sensor,
            data=redact(data),
        )
        self.ledger.append(event.model_dump())
        return event.id

    def flush(self) -> int:
        if not self.collector:
            return 0
        rows = self.ledger.events(pending=True, limit=100)
        if not rows:
            return 0
        status, result = request(
            self.collector + "/ingest", token=self.token, body={"events": rows}
        )
        if status != 200 or set(result.get("accepted", [])) != {r["id"] for r in rows}:
            raise ConnectionError("Collector did not acknowledge evidence batch")
        with self.ledger.lock, self.ledger.db:
            self.ledger.db.executemany(
                "UPDATE events SET delivered=1 WHERE id=?", [(r["id"],) for r in rows]
            )
        return len(rows)

    def start(self) -> None:
        def loop() -> None:
            while not self.stopping.wait(2):
                try:
                    self.flush()
                except (ConnectionError, ValueError, OSError):
                    continue  # persisted outbox retains every unacknowledged event

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=20)
