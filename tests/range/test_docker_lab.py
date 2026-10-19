"""Tests for the Phase E3 Docker lab adapter and offline plan validation."""

from __future__ import annotations

import pytest

from saber.domain.errors import IntegrationBlocked
from saber.range import DockerLabController, RangeController, lab_status, validate_lab_plan
from saber.range import docker_lab as dl


def test_committed_lab_plan_is_valid() -> None:
    ok, issues = validate_lab_plan()
    assert ok, f"committed lab plan failed validation: {issues}"


def test_plan_validation_flags_missing_isolation_and_hardening(tmp_path: object) -> None:
    from pathlib import Path

    bad = Path(str(tmp_path)) / "bad.yml"  # type: ignore[arg-type]
    bad.write_text(
        "services:\n"
        "  w:\n"
        "    image: x\n"
        "    privileged: true\n"
        "    network_mode: host\n"
        "    volumes:\n      - /etc:/etc\n"
        "networks:\n  n: {}\n",
        encoding="utf-8",
    )
    ok, issues = validate_lab_plan(bad)
    assert not ok
    joined = " ".join(issues)
    assert "internal" in joined and "privileged" in joined and "cap_drop" in joined
    assert "host network" in joined and "read-only" in joined


def test_plan_validation_closes_escape_vectors(tmp_path: object) -> None:
    from pathlib import Path

    # A compose that passed the OLD shallow denylist but is NOT isolated: a docker.sock mount (:ro),
    # cap_add, pid:host, seccomp unconfined, a long-form writable bind, and attachment to a
    # non-internal egress network while an internal net also exists.
    bad = Path(str(tmp_path)) / "sneaky.yml"  # type: ignore[arg-type]
    bad.write_text(
        "services:\n"
        "  w:\n"
        "    image: x\n"
        "    cap_drop: [ALL]\n"
        "    cap_add: [SYS_ADMIN]\n"
        "    pid: host\n"
        "    security_opt: ['no-new-privileges:true', 'seccomp:unconfined']\n"
        "    networks: [egress]\n"
        "    volumes:\n"
        "      - /var/run/docker.sock:/var/run/docker.sock:ro\n"
        "      - {type: bind, source: /etc, target: /etc, read_only: false}\n"
        "networks:\n  internal_net:\n    internal: true\n  egress: {}\n",
        encoding="utf-8",
    )
    ok, issues = validate_lab_plan(bad)
    assert not ok
    joined = " ".join(issues)
    assert "docker socket" in joined
    assert "cap_add" in joined
    assert "pid: host" in joined
    assert "unconfined" in joined
    assert "non-internal network 'egress'" in joined
    assert "long-form host bind not read_only" in joined


def test_controller_is_a_range_controller() -> None:
    assert isinstance(DockerLabController(), RangeController)


def test_controller_fails_closed_when_daemon_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dl, "docker_daemon_up", lambda *a, **k: False)
    c = DockerLabController()
    for call in (lambda: c.health("m"), lambda: c.snapshot("m"), lambda: c.capture_state("m")):
        with pytest.raises(IntegrationBlocked, match="BLOCKED_INTEGRATION"):
            call()


def test_stateful_ops_blocked_even_if_daemon_up(monkeypatch: pytest.MonkeyPatch) -> None:
    # Snapshot/restore/capture must stay blocked pending an authorized lab, daemon notwithstanding.
    monkeypatch.setattr(dl, "docker_daemon_up", lambda *a, **k: True)
    c = DockerLabController()
    with pytest.raises(IntegrationBlocked, match="authorized lab"):
        c.snapshot("m")
    from saber.range.ports import SnapshotRef

    with pytest.raises(IntegrationBlocked, match="authorized lab"):
        c.restore(SnapshotRef(machine_id="m", snapshot_id="s", content_hash="h"))


def test_bring_up_and_reset_are_plan_only() -> None:
    c = DockerLabController()
    assert c.bring_up_command()[:3] == ["docker", "compose", "-f"]
    assert c.reset_command()[-1] == "-v"  # reset wipes the telemetry volume


def test_lab_status_shape() -> None:
    st = lab_status()
    assert st["plan_valid"] is True
    assert st["status"] in ("READY_TO_LAUNCH", "BLOCKED_DAEMON_DOWN")
    assert isinstance(st["docker_daemon_up"], bool)
