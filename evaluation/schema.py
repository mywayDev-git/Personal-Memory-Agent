"""Versioned dashboard contracts; unknown grades remain unknown."""

import hashlib
import json
import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def content_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Case(Contract):
    id: str = Field(min_length=1, max_length=200, pattern=r"^[\w.-]+$")
    question: str = Field(min_length=1)
    expected_answer: str | None = None
    question_type: str = "general"
    ambiguity_class: Literal["clear", "context_resolvable", "genuinely_ambiguous"] = "clear"
    answerability: Literal["answerable", "unanswerable"] = "answerable"
    expected_behavior: Literal["answer", "clarify", "abstain"] = "answer"
    gold_groups: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_metadata(self):
        reference = self.metadata.get("reference_time")
        if reference is not None and datetime.fromisoformat(reference).tzinfo is None:
            raise ValueError("reference_time requires a timezone")
        groups = self.metadata.get("required_evidence_groups")
        if groups and not self.gold_groups:
            self.gold_groups = {g["group_id"]: g["memory_ids"] for g in groups}
            self.nonempty_groups(self.gold_groups)
        return self

    @field_validator("gold_groups")
    @classmethod
    def nonempty_groups(cls, groups):
        if any(not k or not v or any(not x for x in v) for k, v in groups.items()):
            raise ValueError("Evidence groups must contain memory IDs")
        return groups


class Dataset(Contract):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    cases: list[Case]

    @model_validator(mode="after")
    def unique_cases(self):
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        return self


class Result(Contract):
    case_id: str
    actual_answer: str | None = None
    response_behavior: Literal["answer", "clarify", "abstain"] | None = None
    verdict: Literal["pass", "fail", "pending_review", "not_applicable", "error"]
    latency_ms: float | None = Field(default=None, ge=0)
    error_type: str | None = None
    evaluation: dict = Field(default_factory=dict)
    claims: list[dict] = Field(default_factory=list)

    @field_validator("latency_ms")
    @classmethod
    def finite(cls, value):
        if value is not None and not math.isfinite(value):
            raise ValueError("Finite latency required")
        return value

    @field_validator("evaluation")
    @classmethod
    def valid_grades(cls, value):
        for key in (
            "answer_correct",
            "final_evidence_complete",
            "claims_supported",
            "behavior_correct",
            "retrieval_complete",
        ):
            if value.get(key) is not None and type(value[key]) is not bool:
                raise ValueError(f"{key} must be boolean or null")
        json.dumps(value, allow_nan=False)
        return value

    @field_validator("claims")
    @classmethod
    def valid_claims(cls, value):
        if any(
            c.get("support_status") not in {"supported", "unsupported", "uncertain"} for c in value
        ):
            raise ValueError("Invalid claim support")
        return value
