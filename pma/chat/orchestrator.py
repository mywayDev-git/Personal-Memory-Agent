"""The existing engine remains the single implementation of orchestration."""

from .engine import ChatEngine


class ChatOrchestrator(ChatEngine):
    """Authenticated, idempotent, bounded multi-turn generation and persistence."""
