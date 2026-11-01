import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from saber.environments.diagnostics import doctor, probe_service
from saber.environments.models import EnvironmentConfig, Service


@pytest.fixture
def health_service():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append((self.path, self.headers.get("Authorization")))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/unexpected")
            else:
                self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service = Service(
        name="local-test", capability="siem", api_base_url=f"http://127.0.0.1:{server.server_port}"
    )
    try:
        yield service, calls
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_service_needs_both_probe_flag_and_inventory_approval(health_service):
    service, calls = health_service
    assert probe_service(service, enabled=True)["status"] == "not_probed"
    service.approved_for_read_only_use = True
    assert probe_service(service)["status"] == "not_probed"
    assert not calls
    report = probe_service(service, enabled=True)
    assert report["status"] == "http_reachable" and not report["adapter_verified"]
    assert calls == [("/health", None)]


def test_redirect_does_not_forward_credentials_or_probe_another_path(health_service, monkeypatch):
    service, calls = health_service
    service.approved_for_read_only_use = True
    service.health_check_path = "/redirect"
    service.credential_env_name = "TEST_SERVICE_TOKEN"
    monkeypatch.setenv("TEST_SERVICE_TOKEN", "secret-for-test")
    report = probe_service(service, enabled=True)
    assert report["status"] == "redirect_refused"
    assert calls == [("/redirect", "Bearer secret-for-test")]
    assert "secret-for-test" not in json.dumps(report)


def test_missing_credentials_and_cleartext_remote_do_not_make_requests(monkeypatch):
    service = Service(
        name="test",
        capability="cases",
        api_base_url="http://192.0.2.1",
        approved_for_read_only_use=True,
        credential_env_name="TEST_SERVICE_TOKEN",
    )
    monkeypatch.delenv("TEST_SERVICE_TOKEN", raising=False)
    assert probe_service(service, enabled=True)["status"] == "credential_missing"
    monkeypatch.setenv("TEST_SERVICE_TOKEN", "secret-for-test")
    assert probe_service(service, enabled=True)["status"] == "tls_required_for_credentials"


def test_doctor_reports_missing_engine_without_starting_it(monkeypatch):
    monkeypatch.setattr("saber.environments.diagnostics.shutil.which", lambda _: None)
    report = doctor(EnvironmentConfig(name="test", profile="sandbox"))
    assert report["blockers"] and not report["runtime_verified"]
    assert not report["prerequisites_available_on_this_host"]


def test_local_doctor_does_not_require_docker_or_claim_vm_verification():
    report = doctor(EnvironmentConfig(name="test", profile="local"))
    assert report["prerequisites_available_on_this_host"]
    assert not report["runtime_verified"] and not report["isolation_verified"]
