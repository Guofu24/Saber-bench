"""Emit agent-office events so the live population shows up in the 3D office viewer.

agent-office (the sibling ``agent-office/`` tool) visualizes a multi-agent run. It normally infers
agents by proxying OpenAI/Anthropic HTTP traffic, but it does NOT speak Gemini's native API — which
is exactly what :class:`~saber.agents.gemini.GeminiProvider` calls. So instead of proxying, we push
explicit events to its ``POST /ingest`` endpoint: each population role becomes an office agent, each
Gemini call a think→answer, and each routing/report a handoff. This is both Gemini-compatible and
more precise than inference (we know the real roles and handoffs).

Fail-soft by design: if no office URL is set (or the viewer is down) every method is a cheap no-op,
so a normal ``saber population run`` is unaffected. The URL comes from ``AGENT_OFFICE_URL`` (set
automatically when launched via ``agent-office run -- ...``) or an explicit ``--office-url``.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable
from typing import Any

# id -> (display name, role, color). Stable desks in the office.
ROLE_AGENTS: dict[str, tuple[str, str, str]] = {
    "client": ("Client", "Người dùng/máy lành tính", "#4fd8ff"),
    "red": ("Red Team", "Mô phỏng đối thủ (allowlist trơ)", "#ff5c5c"),
    "range": ("Range", "Cyber range cô lập", "#b892ff"),
    "orchestrator": ("Orchestrator", "Điều phối SOC / định tuyến", "#ffd36b"),
    "blue": ("Blue Team", "Phòng thủ / phát hiện", "#6bf29b"),
}

Sink = Callable[[list[dict[str, Any]]], None]


class OfficeEmitter:
    """Posts office events to agent-office. Inject ``sink`` in tests; else it POSTs to ``url``."""

    def __init__(self, url: str | None = None, *, sink: Sink | None = None) -> None:
        self.url = (url or os.environ.get("AGENT_OFFICE_URL") or "").rstrip("/") or None
        self._sink = sink
        self.enabled = bool(self._sink or self.url)
        self._fails = 0

    def _send(self, events: list[dict[str, Any]]) -> None:
        if not self.enabled:
            return
        if self._sink is not None:
            self._sink(events)
            return
        try:
            req = urllib.request.Request(  # noqa: S310 - fixed loopback agent-office endpoint
                f"{self.url}/ingest",
                data=json.dumps(events).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=1.0):  # noqa: S310
                self._fails = 0
        except Exception:  # fail-soft: never let the viewer break the run
            self._fails += 1
            if self._fails >= 3:  # viewer clearly not there; stop trying
                self.enabled = False

    # --- event helpers ---------------------------------------------------------------------------
    def world_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Publish one bounded, sanitized runtime snapshot instead of inferred LLM events."""
        self._send([snapshot])

    def register_agents(self) -> None:
        self._send(
            [
                {"type": "agent", "id": aid, "name": name, "role": role, "color": color}
                for aid, (name, role, color) in ROLE_AGENTS.items()
            ]
        )

    def agent(self, agent_id: str, name: str, role: str, color: str | None = None) -> None:
        ev: dict[str, Any] = {"type": "agent", "id": agent_id, "name": name, "role": role}
        if color:
            ev["color"] = color
        self._send([ev])

    def task(self, agent_id: str, title: str) -> None:
        self._send([{"type": "task", "id": agent_id, "title": title}])

    def llm_start(self, agent_id: str, model: str) -> None:
        self._send([{"type": "llm_start", "id": agent_id, "model": model}])

    def llm_end(self, agent_id: str, ms: int, text: str, usage: dict[str, int]) -> None:
        self._send(
            [{"type": "llm_end", "id": agent_id, "ms": ms, "text": text[:280], "usage": usage}]
        )

    def tool(self, agent_id: str, name: str) -> None:
        self._send([{"type": "tool", "id": agent_id, "name": name}])

    def handoff(self, from_id: str, to_id: str, via: str) -> None:
        self._send([{"type": "handoff", "from": from_id, "to": to_id, "via": via}])

    def message(self, agent_id: str | None, text: str) -> None:
        ev: dict[str, Any] = {"type": "message", "text": text}
        if agent_id:
            ev["id"] = agent_id
        self._send([ev])

    def status(self, agent_id: str, state: str, text: str = "") -> None:
        self._send([{"type": "status", "id": agent_id, "state": state, "text": text}])
