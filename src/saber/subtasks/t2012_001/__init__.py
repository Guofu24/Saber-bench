"""T2012.001 (HUNT, file) — list abnormal network connections from netstat output.

Source scenario: given netstat output with N connections, M of which are abnormal, list the
abnormal connections. Source scorer: `abnormal[]` (set/(ip,port)) with aggregate
`max(0, M'/M - N'/(N'+M'))`.

Abnormal = outbound to an external (TEST-NET) address on an unusual port from a process that
should not open external sockets. Benign connections include internal RFC 1918 traffic and
expected SaaS/update endpoints. All synthetic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from saber.domain.base import StrictModel
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng, iso

_BENIGN_PROCS = (
    "chrome.exe",
    "msedge.exe",
    "outlook.exe",
    "teams.exe",
    "OneDrive.exe",
    "svchost.exe",
)
_UNEXPECTED_PROCS = (
    "notepad.exe",
    "calc.exe",
    "mspaint.exe",
    "rundll32.exe",
    "regsvr32.exe",
    "write.exe",
)
_BENIGN_PORTS = (80, 443, 445, 139, 53, 123, 389)
_UNUSUAL_PORTS = (4444, 8443, 1337, 6667, 9001, 53413, 8081)


class Connection(StrictModel):
    proto: str
    local_addr: str
    remote_ip: str
    remote_port: int
    state: str
    process: str


class T2012Output(StrictModel):
    abnormal: list[dict[str, Any]] = Field(default_factory=list)


def _elem(ip: str, port: int) -> dict[str, Any]:
    return {"ip": ip, "port": port}


class Subtask(SubtaskBase):
    SUBTASK_ID = "T2012.001"
    OutputModel = T2012Output
    VARIANTS = ("default", "benign_only", "dense")

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        n_total = {"benign_only": rng.randint(16, 22), "dense": rng.randint(22, 28)}.get(
            variant, rng.randint(18, 25)
        )
        m_target = (
            0
            if variant == "benign_only"
            else (rng.randint(4, 6) if variant == "dense" else rng.randint(2, 4))
        )
        host = rng.hostname("ws")
        local_ip = rng.internal_ip()
        conns: list[dict[str, Any]] = []
        abnormal: list[dict[str, Any]] = []
        for _ in range(n_total - m_target):
            if rng.chance(0.5):
                remote, port = rng.internal_ip(), rng.pick(_BENIGN_PORTS)
            else:
                remote, port = rng.external_ip(), rng.pick((80, 443))
            conns.append(
                {
                    "proto": "TCP",
                    "local_addr": f"{local_ip}:{rng.randint(49152, 65535)}",
                    "remote_ip": remote,
                    "remote_port": port,
                    "state": "ESTABLISHED",
                    "process": rng.pick(_BENIGN_PROCS),
                }
            )
        for _ in range(m_target):
            remote, port = rng.external_ip(), rng.pick(_UNUSUAL_PORTS)
            conns.append(
                {
                    "proto": "TCP",
                    "local_addr": f"{local_ip}:{rng.randint(49152, 65535)}",
                    "remote_ip": remote,
                    "remote_port": port,
                    "state": "ESTABLISHED",
                    "process": rng.pick(_UNEXPECTED_PROCS),
                }
            )
            abnormal.append(_elem(remote, port))
        conns = rng.shuffle(conns)
        netstat = {
            "hv": "HV-17",
            "captured_at": iso(rng.time()),
            "host": host,
            "connections": conns,
        }
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs={"netstat": netstat},
            sealed_truth={"abnormal": abnormal, "m": m_target, "n": n_total},
            evidence_ids=[f"conn-{i}" for i in range(len(conns))],
            notes="Abnormal = external remote on an unusual port from an unexpected process.",
        )

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        return {"abnormal": list(truth["abnormal"])}

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        comp = self.delta_item("abnormal", answer.abnormal, truth["abnormal"], subtype="(ip,port)")
        return ScoreParts(
            components=[comp],
            raw_score=comp.score,
            trace=[f"abnormal set-delta -> {comp.score:.4f} ({comp.detail})"],
        )

    def reference_solve(
        self, public_inputs: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]] | None:
        conns = public_inputs["netstat"]["connections"]
        found = []
        for c in conns:
            external = c["remote_ip"].split(".")[0] in {"192", "198", "203"} and not c[
                "remote_ip"
            ].startswith("10.")
            if (
                external
                and c["remote_port"] in _UNUSUAL_PORTS
                and c["process"] in _UNEXPECTED_PROCS
            ):
                found.append(_elem(c["remote_ip"], c["remote_port"]))
        return {"abnormal": found}, [f"conn-{i}" for i in range(len(conns))]

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        truth = bundle.sealed_truth["abnormal"]
        cases = [
            GoldenCase("empty_answer", {"abnormal": []}, expected_score=1.0 if not truth else 0.0)
        ]
        if truth:
            cases.append(
                GoldenCase(
                    "fp_added", {"abnormal": truth + [_elem("10.20.1.5", 443)]}, expected_max=0.99
                )
            )
        return cases
