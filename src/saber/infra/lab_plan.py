"""Plan-only validation of an isolated lab topology (T015). Never provisions anything.

`validate_lab_plan` is static analysis: it proves a proposed topology is deny-by-default and has
no layer-3 route to production/enterprise/Internet ranges, rejects NAT to production, and requires
every VM to sit on a lab bridge. A passing plan is NOT proof of real isolation — that needs
on-host route/firewall tests at H2. `apply` does not exist here by design.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from pydantic import Field

from saber.domain.base import StrictModel

# Ranges a lab must never be able to route to (enterprise/private + any public address).
PRODUCTION_CIDRS = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)
# A dedicated lab range carved out explicitly; anything else private is treated as production.
LAB_CIDR = ipaddress.IPv4Network("10.66.0.0/16")


class NetworkPlan(StrictModel):
    bridge: str = Field(min_length=1)
    cidr: str
    default_deny: bool = True
    nat_to: list[str] = Field(default_factory=list)
    routes_to: list[str] = Field(default_factory=list)


class VmPlan(StrictModel):
    name: str = Field(min_length=1)
    bridge: str
    ip: str
    role: str


class LabPlan(StrictModel):
    lab_environment_id: str = Field(min_length=1)
    network: NetworkPlan
    vms: list[VmPlan] = Field(default_factory=list)
    internet_egress: bool = False


@dataclass
class IsolationViolation:
    code: str
    detail: str


@dataclass
class PlanResult:
    ok: bool
    violations: list[IsolationViolation] = field(default_factory=list)


def _in_production(addr: str) -> bool:
    try:
        net = ipaddress.IPv4Network(addr, strict=False)
    except ValueError:
        return True  # unparseable (or IPv6) -> treat as unsafe
    if net.subnet_of(LAB_CIDR):
        return False
    return any(net.overlaps(p) for p in PRODUCTION_CIDRS) or net.is_global


def validate_lab_plan(plan: LabPlan) -> PlanResult:
    violations: list[IsolationViolation] = []
    net = plan.network

    if not net.default_deny:
        violations.append(
            IsolationViolation("not_deny_by_default", "lab network must be deny-by-default")
        )

    try:
        lab_net = ipaddress.IPv4Network(net.cidr, strict=False)
    except ValueError:
        violations.append(
            IsolationViolation("lab_cidr_invalid", f"{net.cidr!r} is not a valid IPv4 network")
        )
        return PlanResult(ok=False, violations=violations)
    if not lab_net.subnet_of(LAB_CIDR):
        violations.append(
            IsolationViolation(
                "lab_cidr_out_of_range",
                f"{net.cidr} is not within the dedicated lab range {LAB_CIDR}",
            )
        )

    for target in net.nat_to:
        violations.append(
            IsolationViolation(
                "nat_to_target", f"NAT to {target!r} is forbidden for an isolated lab"
            )
        )

    for route in net.routes_to:
        if _in_production(route):
            violations.append(
                IsolationViolation(
                    "route_to_production", f"route to {route!r} reaches production/Internet"
                )
            )

    if plan.internet_egress:
        violations.append(
            IsolationViolation(
                "internet_egress", "default test execution must have no Internet egress"
            )
        )

    bridges = {net.bridge}
    for vm in plan.vms:
        if vm.bridge not in bridges:
            violations.append(
                IsolationViolation(
                    "vm_off_lab_bridge",
                    f"VM {vm.name!r} is on bridge {vm.bridge!r}, not the lab bridge",
                )
            )
        try:
            ip = ipaddress.IPv4Address(vm.ip)
            if ip not in lab_net:
                violations.append(
                    IsolationViolation(
                        "vm_ip_out_of_lab", f"VM {vm.name!r} IP {vm.ip} is outside the lab CIDR"
                    )
                )
        except ValueError:
            violations.append(
                IsolationViolation("vm_bad_ip", f"VM {vm.name!r} has invalid IP {vm.ip!r}")
            )

    return PlanResult(ok=not violations, violations=violations)
