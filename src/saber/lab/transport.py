"""Bounded HTTP JSON transport; no inherited proxy, redirects or secret diagnostics."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def request(
    url: str,
    *,
    token: str = "",
    body: Any = None,
    method: str | None = None,
    ca: str | None = None,
    timeout: float = 15,
) -> tuple[int, Any]:
    parts = urlsplit(url)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Invalid credential-free HTTP endpoint")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=ca)),
    )
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers=headers,
        method=method,
    )
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    except (OSError, urllib.error.URLError):
        raise ConnectionError("Lab service unavailable; diagnostics redacted") from None
    with response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Lab response exceeds limit")
        try:
            return int(response.code), json.loads(data) if data else {}
        except ValueError:
            raise ValueError("Lab response is not JSON") from None
