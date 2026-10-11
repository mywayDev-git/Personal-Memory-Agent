
"""Custom exceptions for the Personal Memory Agent."""


class MemoryAgentError(Exception):
    """Base exception for application-level errors."""


class LLMClientError(MemoryAgentError):
    """Raised when the LLM API request or response fails."""


class ExtractionError(MemoryAgentError):
    """Raised when extraction output cannot be parsed or processed."""


class SchemaValidationError(MemoryAgentError):
    """Raised when data fails JSON Schema validation."""


class EvidenceValidationError(MemoryAgentError):
    """Raised when extracted evidence does not match the source text."""


class ConfigurationError(MemoryAgentError):
    """Raised when application configuration is invalid."""
