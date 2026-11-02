"""Authenticated loopback HTTP tools; agents have no direct database or host access."""

from __future__ import annotations

import contextlib
import json
import secrets
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from saber.world.environment import World
from saber.world.models import Action

if TYPE_CHECKING:
    from saber.world.native import NativeExecutor


class LabServer:
    def __init__(self, world: World) -> None:
        self.world = world
        self._tokens = {secrets.token_urlsafe(32): a for a in world.actors.values()}
        self._by_actor = {a.id: token for token, a in self._tokens.items()}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def reply(self, status: int, data: dict[str, Any]) -> None:
                payload = json.dumps(data, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                actor = owner._tokens.get(
                    self.headers.get("Authorization", "").removeprefix("Bearer ")
                )
                if actor is None:
                    self.reply(401, {"error": "authentication required"})
                elif self.path != "/v1/observe":
                    self.reply(404, {"error": "unknown tool endpoint"})
                else:
                    self.reply(200, owner.world.observe(actor))

            def do_POST(self) -> None:  # noqa: N802
                actor = owner._tokens.get(
                    self.headers.get("Authorization", "").removeprefix("Bearer ")
                )
                if actor is None:
                    self.reply(401, {"error": "authentication required"})
                    return
                if self.path != "/v1/act":
                    self.reply(404, {"error": "unknown tool endpoint"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 16384 or self.headers.get("Transfer-Encoding"):
                        self.reply(413, {"error": "request too large or unsupported encoding"})
                        return
                    self.connection.settimeout(5)
                    action = Action.model_validate_json(self.rfile.read(length))
                except (ValueError, ValidationError, TimeoutError):
                    self.reply(400, {"error": "invalid action"})
                    return
                result = owner.world.act(actor, action)
                self.reply(int(result["status"]), result)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.http.daemon_threads = True
        self.thread = threading.Thread(
            target=self.http.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.http.server_port}"

    def client(self, actor_id: str) -> ToolClient:
        return ToolClient(self.url, self._by_actor[actor_id])

    def start(self) -> None:
        self.thread.start()

    def native_act(
        self, executor: NativeExecutor, actor_id: str, tick: int, action: Action
    ) -> dict[str, Any]:
        return executor.act(actor_id, tick, self.http.server_port, self._by_actor[actor_id], action)

    def close(self) -> None:
        if self.thread.is_alive():
            self.http.shutdown()
            self.thread.join(timeout=5)
        self.http.server_close()


class ToolClient:
    def __init__(self, url: str, token: str) -> None:
        self._url = url
        self._token = token
        # Never route local tools through HTTP_PROXY/HTTPS_PROXY inherited from the host.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        req = urllib.request.Request(
            self._url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
        )
        try:
            with self._opener.open(req, timeout=10) as response:
                result: dict[str, Any] = json.loads(response.read())
                return result
        except urllib.error.HTTPError as exc:
            error: dict[str, Any] = json.loads(exc.read())
            return error

    def observe(self) -> dict[str, Any]:
        return self._request("/v1/observe")

    def act(self, action: Action) -> dict[str, Any]:
        return self._request("/v1/act", action.model_dump())
