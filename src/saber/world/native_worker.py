"""Fixed, stdlib-only workload worker, invoked with Python -I (no model shell).

These are measurements of this worker's completed operations, not a kernel sensor.
No credentials, HTTP bodies, environment values or arbitrary commands are logged.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import struct
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DNS_QUESTION = b"\x03lab\x05saber\x04test\x00\x00\x01\x00\x01"


def execute(request: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    def record(kind: str, **data: Any) -> None:
        rows.append({"kind": kind, "ts": datetime.now(UTC).isoformat(), **data})

    # A real DNS datagram exchange with the run's private loopback responder.
    # It never uses the host resolver, Internet DNS or user-selected hostnames.
    transaction = os.urandom(2)
    packet = transaction + struct.pack("!HHHHH", 0x0100, 1, 0, 0, 0) + DNS_QUESTION
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns:
        dns.settimeout(3)
        dns.connect(("127.0.0.1", int(request["dns_port"])))
        dns.send(packet)
        reply = dns.recv(512)
        expected = transaction + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0)
        answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x00\x00\x04\x7f\x00\x00\x01"
        if reply != expected + DNS_QUESTION + answer:
            raise ValueError("Invalid private DNS response")
        address = socket.inet_ntoa(reply[-4:])
        record(
            "dns.response",
            name="lab.saber.test",
            answer=address,
            server=f"127.0.0.1:{request['dns_port']}",
            transport="udp",
            bytes=len(reply),
        )

    connection = http.client.HTTPConnection(address, int(request["http_port"]), timeout=10)
    try:
        connection.connect()
        assert connection.sock is not None
        local, peer = connection.sock.getsockname(), connection.sock.getpeername()
        record(
            "network.connect",
            local=f"{local[0]}:{local[1]}",
            remote=f"{peer[0]}:{peer[1]}",
            transport="tcp",
        )
        body = json.dumps(request["action"]).encode("utf-8")
        start = time.monotonic()
        connection.request(
            "POST",
            "/v1/act",
            body=body,
            headers={
                "Authorization": "Bearer " + request["token"],
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        payload = response.read(1_048_577)
        if len(payload) > 1_048_576:
            raise ValueError("Response exceeds workload limit")
        result: dict[str, Any] = json.loads(payload)
        record(
            "http.response",
            method="POST",
            path="/v1/act",
            status=response.status,
            bytes=len(payload),
            duration_ms=round((time.monotonic() - start) * 1000, 3),
        )
    finally:
        connection.close()

    # Bounded, real per-actor disk artifact. Store metadata only; never document
    # contents, submitted text, tokens or model instructions in these public logs.
    receipt = json.dumps({"event_id": result.get("event_id"), "status": result["status"]}).encode()
    path = Path("last-action.json")
    # Refuse pre-existing links; only this fixed basename is writable.
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError("Workload artifact must be an ordinary file")
    with path.open("wb") as stream:
        stream.write(receipt)
        stream.flush()
        os.fsync(stream.fileno())
    record("file.write", path=path.name, bytes=len(receipt))
    actual = path.read_bytes()
    if actual != receipt:
        raise OSError("File readback mismatch")
    record(
        "file.read", path=path.name, bytes=len(actual), sha256=hashlib.sha256(actual).hexdigest()
    )
    return result


def main() -> None:
    rows: list[dict[str, Any]] = []
    result: dict[str, Any] = {}
    error = None
    try:
        request = json.loads(sys.stdin.buffer.readline(32769))
        result = execute(request, rows)
    except Exception as exc:
        # Class name only: exceptions can contain credentials or request bodies.
        error = type(exc).__name__
    print(json.dumps({"result": result, "events": rows, "error": error}), flush=True)
    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
