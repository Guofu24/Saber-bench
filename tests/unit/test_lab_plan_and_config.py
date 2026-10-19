"""Plan-only lab isolation validation and the environment capability matrix."""

from __future__ import annotations

from pathlib import Path

from saber.config import Decision, capability_matrix, load_inventory
from saber.infra import LabPlan, NetworkPlan, VmPlan, validate_lab_plan


def _good_plan() -> LabPlan:
    return LabPlan(
        lab_environment_id="lab-1",
        network=NetworkPlan(bridge="vmbr-lab", cidr="10.66.1.0/24", default_deny=True),
        vms=[
            VmPlan(name="win-ws", bridge="vmbr-lab", ip="10.66.1.10", role="workstation"),
            VmPlan(name="lin-web", bridge="vmbr-lab", ip="10.66.1.20", role="web"),
        ],
        internet_egress=False,
    )


def test_isolated_plan_passes() -> None:
    result = validate_lab_plan(_good_plan())
    assert result.ok, [v.detail for v in result.violations]


def test_route_outside_lab_rejected() -> None:
    # Allowlist semantics: production, and also special-use ranges, are rejected.
    for route in ("10.0.0.0/8", "169.254.0.0/16", "100.64.0.0/10", "0.0.0.0/0", "8.8.8.8/32"):
        plan = _good_plan()
        plan.network.routes_to = [route]
        result = validate_lab_plan(plan)
        assert not result.ok, route
        assert any(v.code == "route_outside_lab" for v in result.violations), route


def test_route_inside_lab_allowed() -> None:
    plan = _good_plan()
    plan.network.routes_to = ["10.66.2.0/24"]  # another subnet within the lab range
    assert validate_lab_plan(plan).ok


def test_nat_and_egress_and_bridge_rejected() -> None:
    plan = _good_plan()
    plan.network.nat_to = ["192.168.1.1"]
    plan.internet_egress = True
    plan.vms[0].bridge = "vmbr0"  # production bridge
    codes = {v.code for v in validate_lab_plan(plan).violations}
    assert {"nat_to_target", "internet_egress", "vm_off_lab_bridge"} <= codes


def test_lab_cidr_out_of_range_rejected() -> None:
    plan = _good_plan()
    plan.network.cidr = "192.168.5.0/24"
    plan.vms = []
    result = validate_lab_plan(plan)
    assert any(v.code == "lab_cidr_out_of_range" for v in result.violations)


def test_vm_ip_outside_lab_rejected() -> None:
    plan = _good_plan()
    plan.vms[0].ip = "10.66.2.10"  # outside the /24
    assert any(v.code == "vm_ip_out_of_lab" for v in validate_lab_plan(plan).violations)


def test_capability_matrix_offline_defaults(repo_root: Path) -> None:
    inv = load_inventory(repo_root)
    matrix = {d.capability: d for d in capability_matrix(inv)}
    # Offline: DEV-satisfiable capabilities REUSE; lab-only capabilities BLOCK.
    assert matrix["telemetry_search"].decision is Decision.REUSE
    assert matrix["llm_provider"].decision is Decision.REUSE
    assert matrix["host_virtualization"].decision is Decision.BLOCK
    assert matrix["emulation"].decision is Decision.BLOCK
