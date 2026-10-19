"""Bounded conversation hints, never a substitute for source evidence."""

from .schemas import ConversationState


def advance(state, question, rows, response, message_id):
    result = state.model_copy(deep=True)
    result.version += 1
    result.active_topic = question[:1000]
    result.active_evidence = [r["id"] for r in rows]
    result.pending_clarification = (
        message_id if response.get("status") == "needs_clarification" else None
    )
    return result


def summarize(messages, limit=2000):
    """Extractive topic history; deliberately excludes assistant factual assertions."""
    return "\n".join(m["question"][:200] for m in messages[-16:])[-limit:]


def merge_filters(state_filters, explicit):
    return {**state_filters, **(explicit or {})}


def state_from(value):
    return ConversationState.model_validate(value or {})
