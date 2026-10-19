"""B002: SubtaskSpecV1 built from the frozen catalog validates per environment."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from saber.catalog import load_catalog
from saber.domain.subtask import (
    Environment,
    GateSemantics,
    SubmissionEnvelope,
    SubtaskSpecV1,
    ToolPolicy,
    spec_from_catalog,
)

VM_POLICY = ToolPolicy(allow=["read_fixture", "approved_lab_action"], state_mutation=True)


def test_spec_from_every_catalog_record(repo_root: Path) -> None:
    cat = load_catalog(repo_root)
    built = 0
    for rec in cat.subtasks:
        spec = spec_from_catalog(
            rec,
            output_schema_ref=f"schemas/{rec.id}.output.schema.json",
            scorer_ref=f"grader:{rec.id}@1",
            tool_policy=VM_POLICY if rec.environment == "vm" else None,
        )
        assert spec.id == rec.id
        assert spec.environment.value == rec.environment
        assert len(spec.inputs) == len(rec.input_hv_ids)
        assert spec.source_sha256 == rec.source_sha256
        built += 1
    assert built == 175


def test_file_defaults_and_gate_semantics(repo_root: Path) -> None:
    cat = load_catalog(repo_root)
    spec = spec_from_catalog(cat.subtask("T1349.003"), output_schema_ref="s", scorer_ref="g")
    assert spec.gate_semantics["channel"] is GateSemantics.ZERO
    assert spec.gate_semantics["no_cross_customer"] is GateSemantics.ZERO
    assert "missing_required_evidence" in spec.invalidity
    assert spec.timeouts.source == "default_by_environment"


def test_invalid_specs_rejected(repo_root: Path) -> None:
    cat = load_catalog(repo_root)
    good = spec_from_catalog(
        cat.subtask("T1389.001"), output_schema_ref="s", scorer_ref="g", tool_policy=VM_POLICY
    )
    assert good.environment is Environment.VM
    data = good.model_dump()
    data["invalidity"] = ["missing_required_evidence"]
    with pytest.raises(ValidationError):
        SubtaskSpecV1.model_validate(data)
    data = good.model_dump()
    data["nice_id"] = "T1112"
    with pytest.raises(ValidationError):
        SubtaskSpecV1.model_validate(data)
    data = good.model_dump()
    data["tool_policy"] = {"default": "deny", "allow": ["read_fixture"], "state_mutation": True}
    with pytest.raises(ValidationError):
        SubtaskSpecV1.model_validate(data)
    data = good.model_dump()
    data["weights_total"] = 2
    with pytest.raises(ValidationError):
        SubtaskSpecV1.model_validate(data)


def test_weighted_sum_total_enforced(repo_root: Path) -> None:
    cat = load_catalog(repo_root)
    spec = spec_from_catalog(cat.subtask("T1112.002"), output_schema_ref="s", scorer_ref="g")
    data = spec.model_dump()
    data["score_items"][0]["weight"] = 0.9
    with pytest.raises(ValidationError):
        SubtaskSpecV1.model_validate(data)


def test_submission_envelope() -> None:
    env = SubmissionEnvelope(
        episode_id=uuid4(),
        subtask_id="T1112.001",
        agent_id="stub",
        answer={"verdict": "TP"},
        submitted_at=datetime.now(UTC),
    )
    assert env.evidence_refs == []
    with pytest.raises(ValidationError):
        SubmissionEnvelope(
            episode_id=uuid4(),
            subtask_id="T001",
            agent_id="stub",
            answer={},
            submitted_at=datetime.now(UTC),
        )
