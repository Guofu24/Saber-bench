"""Bounded real-process SOC demonstration without Docker, VMs or provider keys.

Uses only synthetic accounts/documents and loopback HTTP. The separate target
acceptance still owns Docker isolation, OpenSearch, Zeek and Windows/AD validation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import socket
import threading
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

import uvicorn

from saber.lab.analysis_cli import self_test
from saber.lab.analysis_service import AnalysisQueue, create_analysis
from saber.lab.application import create_application
from saber.lab.collector import create_collector
from saber.lab.controller import Controller
from saber.lab.deployment import initialize_secrets, principal, render
from saber.lab.events import Emitter
from saber.lab.ledger import Ledger
from saber.lab.models import preset_spec
from saber.lab.soar import SoarRunner, create_soar
from saber.lab.transport import request
from saber.lab.worker import create_worker


@contextmanager
def served(app: Any) -> Any:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("Loopback server did not start")
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(15)
        sock.close()


def run(out: Path, chrome: Path, ticks: int) -> dict[str, Any]:
    if out.exists() or not chrome.is_file():
        raise ValueError("Choose new output and an existing Chromium executable")
    out.mkdir(parents=True)
    spec = preset_spec("linux-small", "loopback-proof")
    ids = {"client-1", "client-2", "red-access", "blue-ir", "blue-content", "blue-dfir"}
    spec.actors = [a for a in spec.actors if a.id in ids]
    spec.tick_seconds = 0.1
    bundle = out / "bundle"
    render(spec, bundle)
    initialize_secrets(bundle, spec)
    creds = {p.stem: json.loads(p.read_text()) for p in (bundle / ".secrets").glob("*.json")}
    stores, emitters = {}, []
    with ExitStack() as stack:
        for role in ("app", "collector", "analysis", "soar", "client", "red", "blue"):
            stores[role] = Ledger(out / role)
            stack.callback(stores[role].close)
        collector = stack.enter_context(
            served(create_collector(stores["collector"], creds["collector"]))
        )

        def emitter(role: str) -> Emitter:
            value = Emitter(
                stores[role], role + "-loopback", collector, creds[role]["ingest_token"]
            )
            value.start()
            emitters.append(value)
            stack.callback(value.close)
            return value

        app = stack.enter_context(
            served(create_application(stores["app"], creds["app"], emitter("app")))
        )
        analysis = AnalysisQueue(
            stores["analysis"],
            creds["analysis"],
            spec.analysis,
            bundle / "analysis",
            emitter("analysis"),
        )
        analysis.thread.start()
        stack.callback(analysis.close)
        analysis_url = stack.enter_context(served(create_analysis(analysis)))
        soar = SoarRunner(stores["soar"], creds["soar"], spec.soar, collector, app, emitter("soar"))
        soar.thread.start()

        def stop_soar() -> None:
            soar.stop.set()
            soar.thread.join(30)

        stack.callback(stop_soar)
        soar_url = stack.enter_context(served(create_soar(soar)))
        self_test(bundle, analysis_url)
        urls = {}
        for team in ("client", "red", "blue"):
            credentials = creds[team] | (
                {"analysis_url": analysis_url, "soar_url": soar_url} if team == "blue" else {}
            )
            worker = create_worker(
                stores[team],
                credentials,
                team,
                app,
                collector,
                emitter(team),
                browser_executable=str(chrome.resolve()),
            )
            urls[team] = stack.enter_context(served(worker))
        controller = Controller(spec, out / "controller", creds["controller"], urls, collector)
        stack.callback(controller.close)
        # Observe each verified response while its TTL can still be active. A
        # short run may not schedule another red read; a slow run can legitimately
        # outlive session containment. Neither should replace a real access check.
        owner, red = principal("client-1"), principal("red-access")
        probes: list[dict[str, Any]] = []
        checked_responses: set[str] = set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as scheduler:
            running = scheduler.submit(controller.run, ticks=ticks)
            while True:
                for response in stores["soar"].events(kind="soar.completed", limit=100):
                    if response["id"] in checked_responses or not response["data"].get("verified"):
                        continue
                    checked_responses.add(response["id"])
                    previous_events = {e["id"] for e in stores["app"].events(limit=1000)}
                    probe = {
                        "response_event_id": response["id"],
                        "playbook": response["data"]["playbook"],
                    }
                    for team, user in (("red", red), ("client", owner)):
                        status, _ = request(
                            app + "/documents/" + owner,
                            token=creds["app"]["accounts"][user]["token"],
                        )
                        probe[team + "_status"] = status
                    probe["evidence_ids"] = [
                        e["id"]
                        for e in stores["app"].events(limit=1000)
                        if e["id"] not in previous_events
                    ]
                    probes.append(probe)
                if running.done():
                    running.result()
                    break
                time.sleep(0.1)
        for value in emitters:
            while value.flush():
                pass
        controller.publish(stopped=True)
        events = stores["collector"].events(limit=1000)
        verified_probes = [
            p for p in probes if p["red_status"] == 403 and p["client_status"] == 200
        ]
        probe_ids = {eid for p in verified_probes for eid in p["evidence_ids"]}
        probe_events = [e for e in events if e["host"] == "app-loopback" and e["id"] in probe_ids]
        checks = {
            "all_agents_executed": all(
                controller.store.get("lab-memory", a.id, {}).get("turn", 0) > 0 for a in spec.actors
            ),
            "soar_effect_verified": any(
                e["kind"] == "soar.completed" and e["data"].get("verified") for e in events
            ),
            "enforced_denial": any(
                e["kind"] in ("auth.denied", "file.access_denied")
                and e["data"].get("principal") == red
                for e in probe_events
            ),
            "benign_access_preserved": any(
                e["kind"] == "file.read"
                and e["data"].get("principal") == owner
                and e["data"].get("owner") == owner
                for e in probe_events
            ),
            "native_yara": any(
                e["kind"] == "analysis.completed"
                and e["data"].get("engine") == "yara"
                and e["data"].get("state") == "SUCCEEDED"
                for e in events
            ),
            "browser_artifact": any(
                a.get("name") == "browser.png"
                for e in events
                for a in e["data"].get("artifacts", [])
            ),
        }
        report = {
            "passed": all(checks.values()),
            "checks": checks,
            "actors": len(spec.actors),
            "ticks": ticks,
            "response_probes": probes,
            "probe_origin": "operator verification during agent execution; no policy changes",
            "scope": "real loopback services/processes/browser/YARA, scripted planning; no Docker/AD acceptance",
            "office_world": str(out / "controller"),
        }
        (out / "proof.json").write_text(json.dumps(report, indent=2))
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--chrome", type=Path, required=True)
    parser.add_argument("--ticks", type=int, default=12, choices=range(8, 31))
    args = parser.parse_args()
    result = run(args.out, args.chrome, args.ticks)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
