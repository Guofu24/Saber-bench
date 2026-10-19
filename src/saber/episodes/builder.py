"""Build one episode: a public (agent-visible) manifest and a separately stored sealed truth.

The split is physical: `write_episode` writes `public/manifest.json` + `public/inputs.json` and
`sealed/truth.sealed.json` under different directories, so a Blue code path that only has the
public directory cannot reach the truth. The builder asserts no forbidden key leaks into the
public payload before returning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from saber.domain.base import deterministic_uuid
from saber.subtasks import load_subtask
from saber.subtasks._framework import (
    DEV_FIXTURE_LABEL,
    FixtureBundle,
    ManifestInput,
    PublicManifest,
    SubtaskBase,
    assert_no_leak,
    canonical_json,
    sha256_of,
)


@dataclass(frozen=True)
class BuiltEpisode:
    subtask: SubtaskBase
    bundle: FixtureBundle
    manifest: PublicManifest
    truth_sha256: str
    evidence_ids: list[str]

    @property
    def episode_id(self) -> str:
        return str(self.bundle.episode_id)

    def public_payload(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.model_dump(mode="json"),
            "inputs": self.bundle.public_inputs,
        }

    def sealed_payload(self) -> dict[str, Any]:
        return {
            "_notice": "EVALUATOR-ONLY sealed truth. Never mount into a Blue agent runtime.",
            "subtask_id": self.subtask.SUBTASK_ID,
            "episode_id": self.episode_id,
            "seed": self.bundle.seed,
            "variant": self.bundle.variant,
            "truth": self.bundle.sealed_truth,
            "truth_sha256": self.truth_sha256,
            "evidence_ids": self.evidence_ids,
            "labels": self.bundle.labels,
        }


def build_episode(
    subtask_id: str, seed: int = 42, variant: str = "default", *, episode_seconds: int | None = None
) -> BuiltEpisode:
    subtask = load_subtask(subtask_id)
    bundle = subtask.build_fixture(seed, variant)
    if str(bundle.episode_id) != str(subtask.episode_id_for(seed, variant)):
        raise ValueError("fixture episode_id is not the deterministic id for (seed, variant)")
    spec = subtask.spec()
    # Build the agent-visible manifest. Inputs are materialised as one JSON blob per HV input.
    inputs: list[ManifestInput] = []
    for art in spec.inputs:
        payload = _input_payload(bundle.public_inputs, art.hv_id)
        inputs.append(
            ManifestInput(
                hv_id=art.hv_id,
                description=art.description,
                path=f"inputs/{art.hv_id}.json",
                sha256=sha256_of(payload),
            )
        )
    deadline = _deadline(
        bundle, spec.timeouts.episode_seconds if episode_seconds is None else episode_seconds
    )
    manifest = PublicManifest(
        episode_id=bundle.episode_id,
        subtask_id=subtask.SUBTASK_ID,
        service=spec.service.value,
        environment=spec.environment.value,
        task_version=spec.task_version,
        instructions=bundle.public_inputs.get("objective")
        or bundle.subtask_id + ": " + spec.scenario_source,
        inputs=inputs,
        output_schema_ref=spec.output_schema_ref,
        output_schema=subtask.output_schema(),
        tool_policy=spec.tool_policy,
        budget_tool_calls=spec.timeouts.tool_calls,
        deadline_at=deadline,
        provenance_tags=[DEV_FIXTURE_LABEL],
    )
    # Leak guards: neither the manifest nor the public inputs may carry evaluator-only keys.
    assert_no_leak(manifest.model_dump(mode="json"))
    assert_no_leak(bundle.public_inputs)
    truth_sha = sha256_of(bundle.sealed_truth)
    return BuiltEpisode(
        subtask=subtask,
        bundle=bundle,
        manifest=manifest,
        truth_sha256=truth_sha,
        evidence_ids=list(bundle.evidence_ids),
    )


def _deadline(bundle: FixtureBundle, episode_seconds: int) -> Any:
    from saber.subtasks._hv.common import BASE_TIME

    anchor = deterministic_uuid(
        bundle.subtask_id, str(bundle.seed)
    )  # unused value; keep import-free determinism
    _ = anchor
    return BASE_TIME + timedelta(days=1, seconds=episode_seconds)


def _input_payload(public_inputs: dict[str, Any], hv_id: str) -> Any:
    """Pick the portion of public inputs corresponding to one HV input, else the whole blob."""
    for value in public_inputs.values():
        if isinstance(value, dict) and value.get("hv") == hv_id:
            return value
    return public_inputs


def write_episode(episode: BuiltEpisode, root: Path) -> dict[str, Path]:
    public_dir = root / "public"
    sealed_dir = root / "sealed"
    inputs_dir = public_dir / "inputs"
    for d in (public_dir, sealed_dir, inputs_dir):
        d.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    manifest_path = public_dir / "manifest.json"
    manifest_path.write_bytes(canonical_json(episode.manifest.model_dump(mode="json")))
    paths["manifest"] = manifest_path
    for art in episode.manifest.inputs:
        payload = _input_payload(episode.bundle.public_inputs, art.hv_id)
        p = public_dir / art.path
        p.write_bytes(canonical_json(payload))
        paths[art.hv_id] = p
    sealed_path = sealed_dir / "truth.sealed.json"
    sealed_path.write_text(
        json.dumps(episode.sealed_payload(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    paths["sealed"] = sealed_path
    return paths
