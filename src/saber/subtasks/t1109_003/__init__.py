"""T1109.003 (IR, vm) — eradicate 6 components while keeping the web service serving.

Source scorer: `Π[4 điều kiện]` — all_6_removed AND clean_intact AND config_restored AND
service_alive. Full credit only when every malicious component is gone (by content hash, so
relocation does not count), every clean file is byte-identical, config matches the clean
baseline, and the web service still serves.

Offline DEV: the machine is an in-memory snapshot and `service_alive` is verified from state
(web config + document root intact), not from a self-asserted flag. Real hypervisor eradication
with a live HTTP probe is a BLOCKED_INTEGRATION adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from saber.domain.base import StrictModel
from saber.domain.subtask import ToolPolicy
from saber.grading.state import (
    MachineSnapshot,
    all_removed,
    clean_intact,
    config_restored,
    service_alive,
)
from saber.subtasks._framework import (
    FixtureBundle,
    GoldenCase,
    GradeContext,
    ScoreParts,
    SubtaskBase,
)
from saber.subtasks._hv.common import Rng
from saber.subtasks._vm import (
    GuestAction,
    apply_actions,
    file_state,
    now_iso,
    snapshot_from_files,
    snapshot_to_public,
)

_WEB_CONFIG = "/etc/nginx/nginx.conf"
_WEB_INDEX = "/var/www/html/index.php"
_CLEAN_FILES = ("/var/www/html/app.php", "/var/www/html/style.css", "/etc/hosts")


class ActionItem(StrictModel):
    op: str
    path: str
    to: str | None = None


class T1109Output(StrictModel):
    # The agent declares the eradication actions it took; the evaluator applies them to the sealed
    # before-snapshot and verifies the derived state. A fabricated after-snapshot is not accepted.
    actions: list[ActionItem] = Field(default_factory=list)


class Subtask(SubtaskBase):
    SUBTASK_ID = "T1109.003"
    OutputModel = T1109Output
    TOOL_POLICY = ToolPolicy(allow=["read_fixture", "approved_lab_action"], state_mutation=True)
    VARIANTS = ("default",)

    def build_fixture(self, seed: int, variant: str = "default") -> FixtureBundle:
        rng = Rng(seed, self.SUBTASK_ID, variant)
        mid = rng.hostname("web")
        taken = now_iso(rng)
        files = {}
        # Clean files + web config/index that the service needs.
        for path in (_WEB_CONFIG, _WEB_INDEX, *_CLEAN_FILES):
            files[path] = file_state(rng, path, tag=f"clean:{path}")
        # Six malicious components to remove (webshells, a cron backdoor, an attacker account marker).
        malicious = [
            "/var/www/html/.synth1.php",
            "/var/www/html/uploads/.synth2.php",
            "/opt/.synth/loader",
            "/etc/cron.d/synthjob",
            "/usr/local/bin/synthbeacon",
            "/home/synthuser/.profile_hook",
        ]
        for p in malicious:
            files[p] = file_state(rng, p, tag=f"mal:{p}")
        before = snapshot_from_files(mid, files, taken_at=taken, users=["root", "www", "synthuser"])
        public = {
            "machine": snapshot_to_public(before),
            "clean_baseline_paths": [_WEB_CONFIG, *_CLEAN_FILES],
            "objective": "Remove all malicious components; keep clean files and config intact and the web service serving.",
        }
        return FixtureBundle(
            subtask_id=self.SUBTASK_ID,
            seed=seed,
            variant=variant,
            episode_id=self.episode_id_for(seed, variant),
            public_inputs=public,
            sealed_truth={
                "malicious_paths": malicious,
                "clean_paths": [_WEB_CONFIG, _WEB_INDEX, *_CLEAN_FILES],
                "config_paths": [_WEB_CONFIG],
                "machine_before": before.model_dump(mode="json"),
                "taken_at": taken,
            },
            evidence_ids=list(malicious),
        )

    def _before(self, truth: Mapping[str, Any]) -> MachineSnapshot:
        return MachineSnapshot.model_validate(truth["machine_before"])

    def answer_from_truth(self, truth: Mapping[str, Any]) -> dict[str, Any]:
        # Correct eradication: remove each malicious component.
        return {"actions": [{"op": "remove", "path": p} for p in truth["malicious_paths"]]}

    def _after(self, answer: Any, truth: Mapping[str, Any]) -> MachineSnapshot:
        actions = [GuestAction.model_validate(a.model_dump()) for a in answer.actions]
        return apply_actions(self._before(truth), actions, taken_at=truth["taken_at"])

    def score_parts(self, answer: Any, truth: Mapping[str, Any], ctx: GradeContext) -> ScoreParts:
        before = self._before(truth)
        after = self._after(answer, truth)
        removed_gate, detail = all_removed(before, after, truth["malicious_paths"])
        clean_gate = clean_intact(before, after, truth["clean_paths"])
        config_gate = config_restored(before, after, truth["config_paths"])

        def probe() -> bool:
            cfg = after.files.get(_WEB_CONFIG)
            idx = after.files.get(_WEB_INDEX)
            base_cfg = before.files.get(_WEB_CONFIG)
            return (
                cfg is not None
                and idx is not None
                and base_cfg is not None
                and cfg.sha256 == base_cfg.sha256
            )

        alive_gate = service_alive(probe)
        gates = [
            self.gate("all_6_removed", removed_gate.passed, removed_gate.reason),
            self.gate("clean_intact", clean_gate.passed, clean_gate.reason),
            self.gate("config_restored", config_gate.passed, config_gate.reason),
            self.gate("service_alive", alive_gate.passed, alive_gate.reason),
        ]
        return ScoreParts(
            components=[],
            gates=gates,
            raw_score=1.0,
            trace=[f"removal_detail={detail}"] + [f"{g.name}={g.passed}" for g in gates],
        )

    def golden_cases(self, bundle: FixtureBundle) -> list[GoldenCase]:
        t = bundle.sealed_truth
        malicious = t["malicious_paths"]
        # Relocate one malicious file instead of deleting -> content hash still present -> fails.
        relocated = [{"op": "move", "path": malicious[0], "to": "/var/www/html/.backup_blob"}]
        relocated += [{"op": "remove", "path": p} for p in malicious[1:]]
        # Delete every malicious file but also delete the web index -> service_alive fails.
        killed = [{"op": "remove", "path": p} for p in malicious] + [
            {"op": "remove", "path": _WEB_INDEX}
        ]
        return [
            GoldenCase(
                "relocated_not_removed",
                {"actions": relocated},
                expected_score=0.0,
                expect_trace_contains="all_6_removed=False",
            ),
            GoldenCase(
                "service_killed",
                {"actions": killed},
                expected_score=0.0,
                expect_trace_contains="service_alive=False",
            ),
        ]
