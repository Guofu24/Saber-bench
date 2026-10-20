"""A real, minimal HTTP service run as a subprocess by the live lab control plane.

It binds loopback only, serves a few benign routes plus a toy auth endpoint, and writes a genuine
JSON access log (one line per request). It is the "Linux application/service" of the lab; its log is
real telemetry, not fabricated. Run standalone:

    python -m saber.range.live.service_main --host 127.0.0.1 --port 0 --log access.log --ready-file r

The service writes its actually-bound port to the ready-file once listening, so the parent can
discover an ephemeral port without a race. It exits on SIGTERM / process-tree kill from the parent.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_AUTH_OK_PASSWORD = "correct-horse-battery"  # the one valid password for the toy /login endpoint


class _Handler(BaseHTTPRequestHandler):
    log_path: Path = Path("access.log")
    _lock = threading.Lock()
    protocol_version = "HTTP/1.1"

    def _write_log(self, status: int) -> None:
        rec = {
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "client": self.client_address[0],
            "method": self.command,
            "target": self.path,  # raw request target incl. query (url-encoded as sent)
            "status": status,
            "ua": self.headers.get("User-Agent", "-"),
        }
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock, self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _respond(self, status: int, body: bytes = b"ok") -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parts = urlsplit(self.path)
        status = 200
        if parts.path == "/login":
            qs = parse_qs(parts.query)
            pw = (qs.get("pass") or [""])[0]
            status = 200 if pw == _AUTH_OK_PASSWORD else 401
        self._write_log(status)
        self._respond(status, b"ok" if status == 200 else b"unauthorized")

    def log_message(self, _format: str, *_args: object) -> None:
        # Silence the default stderr logging; the JSON access log is the telemetry of record.
        return


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--log", required=True)
    ap.add_argument("--ready-file", required=True)
    args = ap.parse_args(argv)

    if args.host not in ("127.0.0.1", "::1", "localhost"):
        print(f"refusing to bind non-loopback host {args.host!r}", file=sys.stderr)
        return 2

    _Handler.log_path = Path(args.log)
    _Handler.log_path.parent.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((args.host, args.port), _Handler)
    bound_port = httpd.server_address[1]
    Path(args.ready_file).write_text(str(bound_port), encoding="utf-8")
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:  # pragma: no cover - parent kill path
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
