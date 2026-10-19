"""Detection content proposals. Blue agents never publish directly."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from saber.domain.base import Sha256Hex, StrictModel, UtcDatetime


class RuleKind(StrEnum):
    SIGMA = "sigma"
    QUERY = "query"
    REGEX = "regex"
    YARA_SUBSET = "yara_subset"
    SURICATA = "suricata"


class RuleStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    REJECTED = "rejected"
    APPROVED = "approved"
    PUBLISHED = "published"


class DetectionRuleProposal(StrictModel):
    schema_version: Literal[1] = 1
    rule_version_id: UUID
    rule_kind: RuleKind
    content: str = Field(min_length=1, max_length=65536)
    content_sha256: Sha256Hex
    author_agent: str = Field(min_length=1, max_length=64)
    status: RuleStatus = RuleStatus.DRAFT
    field_mapping_version: str = Field(default="1.0.0", max_length=32)
    compiler_backend_version: str = Field(default="saber-regex-1", max_length=64)
    evidence_ids: list[UUID] = Field(default_factory=list)
    test_suite_id: str | None = Field(default=None, max_length=128)
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _hash_matches(self) -> DetectionRuleProposal:
        digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if digest != self.content_sha256:
            raise ValueError("content_sha256 does not match content")
        return self
