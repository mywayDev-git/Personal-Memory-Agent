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


def temporal_followup(question, session, today):
    """Replace explicit calendar constraints, retaining the user's prior topic."""
    import calendar
    import re
    from datetime import date

    match = re.fullmatch(r"\s*(이번|지난|다음)\s*달(?:로|만|은|을)?\s*(?:바꿔|변경해|보여줘|알려줘)[.!?\s]*", question)
    messages = [m for m in session.get("messages", []) if m.get("state") == "completed" and not m.get("error_code")]
    if not match or not messages:
        return None
    previous = messages[-1]
    response = previous.get("response") or {}
    if response.get("conversation_mode", response.get("conversation_type")) not in {"memory", "mixed", "hybrid"}:
        return None
    offset = {"이번": 0, "지난": -1, "다음": 1}[match[1]]
    current = date.fromisoformat(str(today)[:10])
    month_index = current.year * 12 + current.month - 1 + offset
    year, month = divmod(month_index, 12)
    month += 1
    start, end = date(year, month, 1).isoformat(), date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    topic_question = previous['question']
    for message in reversed(messages):
        if not re.fullmatch(r"\s*(?:이번|지난|다음)\s*달(?:로|만|은|을)?\s*(?:바꿔|변경해|보여줘|알려줘)[.!?\s]*", message['question']):
            topic_question = message['question']
            break
    topic = re.sub(r"(?:이번|지난|다음)\s*달|\d{4}-\d{2}-\d{2}|\d{4}년\s*\d{1,2}월", "", topic_question)
    return {"question": f"{year}년 {month}월 {topic.strip()}", "filters": {"date_from": start, "date_to": end}}
