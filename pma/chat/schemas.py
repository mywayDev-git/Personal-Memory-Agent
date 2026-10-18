"""Information source policy, independent of retrieval/context actions."""

from enum import StrEnum


class ConversationMode(StrEnum):
    AUTO = "auto"
    GENERAL = "general"
    MEMORY = "memory"
    HYBRID = "hybrid"
