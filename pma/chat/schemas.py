"""Information source policy, independent of retrieval/context actions."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ConversationMode(StrEnum):
    AUTO = "auto"
    GENERAL = "general"
    MEMORY = "memory"
    HYBRID = "hybrid"


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(default=0, ge=0)
    active_topic: str = ""
    summary: str = ""
    active_evidence: list[str] = Field(default_factory=list)
    pending_clarification: str | None = None
    filters: dict[str, str | None] = Field(default_factory=dict)


class ChatSession(BaseModel):
    id: str
    title: str
    state: str
    created_at: str
    updated_at: str


class ChatMessage(BaseModel):
    id: str
    session_id: str
    request_id: str
    question: str
    state: str


class RetrievalRun(BaseModel):
    message_id: str
    searches: list[dict] = Field(default_factory=list)


class Citation(BaseModel):
    memory_id: str
    record_id: str
    revision_id: str
    quote: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class Clarification(BaseModel):
    message_id: str
    question: str
    alternatives: list[str] = Field(default_factory=list)
