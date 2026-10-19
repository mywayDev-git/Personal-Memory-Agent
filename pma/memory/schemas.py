from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MemoryType = Literal[
    "user_statement",
    "preference",
    "event",
    "project_decision",
    "plan",
    "proposal",
    "hypothesis",
    "correction",
    "conversation_summary",
]
SourceType = Literal[
    "user_message",
    "assistant_message",
    "conversation_summary",
    "existing_record",
    "imported_document",
]


class MemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    owner_id: str
    content: str = Field(min_length=1, max_length=3500)
    memory_type: MemoryType
    epistemic_status: Literal["user_reported", "ai_proposed", "unverified"]
    lifecycle_status: Literal[
        "candidate", "pending", "active", "superseded", "archived", "rejected", "deleted"
    ] = "pending"
    source_type: SourceType
    conversation_mode: Literal["auto", "general", "memory", "hybrid"] = "general"
    session_id: str | None = None
    message_ids: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)
    project_scope: str | None = None
    event_time: str | None = None
    created_at: str
    expires_at: str
    candidate_version: int = 1
    supersedes_memory_id: str | None = None
    expected_version: int | None = None
    source_snapshots: list[dict] = Field(default_factory=list)
    reference_time: str | None = None
    capture_request_id: str | None = None

    @field_validator("content")
    @classmethod
    def nonempty(cls, text):
        if not text.strip():
            raise ValueError("empty content")
        return text


class MemoryRecord(MemoryCandidate):
    memory_id: str
    record_id: str
    record_version: int = Field(ge=1)
    provenance: dict
    updated_at: str
    valid_at: str | None = None
    job_id: str
    related_memories: list[dict] = Field(default_factory=list)
