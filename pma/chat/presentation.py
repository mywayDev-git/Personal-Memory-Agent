"""Render only explicitly reviewed presentation metadata, never guess from prose."""
from copy import deepcopy
from datetime import date

from scripts.memory_agent.validator import schema_errors

from ..models import ANSWER_SCHEMA

DISPLAY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["kind", "items"],
    "properties": {
        "kind": {"enum": ["plain", "partial", "conflict", "same_event", "events"]},
        "items": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["index", "state", "event", "event_date"],
            "properties": {
                "index": {"type": "integer", "minimum": 0},
                "state": {"enum": ["confirmed", "unknown"]},
                "event": {"type": "string", "maxLength": 80},
                "event_date": {"type": "string", "maxLength": 10},
            },
        }},
    },
}
CHAT_ANSWER_SCHEMA = deepcopy(ANSWER_SCHEMA)
CHAT_ANSWER_SCHEMA["properties"]["display"] = DISPLAY_SCHEMA
DISPLAY_POLICY = (
    " display는 표시 제안이다. kind=plain/partial/conflict/same_event/events 중 선택한다. "
    "확인된 사실과 미확인 사항은 별도 답변 items로 분리하고 각각 confirmed/unknown으로 표시한다. "
    "명시적 부정은 confirmed이며 unknown이 아니다. 같은 사건을 여러 원문이 뒷받침할 때만 same_event, "
    "서로 다른 사건이면 events다. 같은 인물이나 장소만으로 같은 사건으로 묶지 않는다. "
    "conflict는 서로 양립하지 않는 주장에만 사용하고, 변경 검토를 확정으로 바꾸지 않는다. "
    "각 display.items에는 답변 index, state, 사건 식별자 event, 사건 날짜 event_date를 넣는다. "
    "사건 식별자는 같은 사건에만 동일하게 쓴다. 해당 없으면 빈 문자열이다. "
    "event_date는 원문으로 확인된 사건 날짜 YYYY-MM-DD만 쓰고 불명이면 빈 문자열이다. "
    "저장일/작성일을 사건 날짜로 대신하지 않는다. 모든 답변 항목을 정확히 한 번 포함한다. "
)


def reviewed_display(response, review):
    display = response.get("display")
    if review.get("presentation_valid") is not True or schema_errors(display, DISPLAY_SCHEMA):
        return None
    rows = display["items"]
    if sorted(r["index"] for r in rows) != list(range(len(response["items"]))):
        return None
    for row in rows:
        if row["event_date"]:
            try:
                if date.fromisoformat(row["event_date"]).isoformat() != row["event_date"]:
                    return None
            except ValueError:
                return None
    events = {r["event"] for r in rows if r["event"]}
    if display["kind"] in {"same_event", "conflict"} and len({
        cid for item in response["items"] for cid in item.get("citations", [])
    }) < 2:
        return None
    for event in events:
        if len({r["event_date"] for r in rows if r["event"] == event and r["event_date"]}) > 1:
            return None
    if display["kind"] == "same_event" and (len(events) != 1 or any(not r["event"] for r in rows)):
        return None
    if display["kind"] == "events" and (len(events) < 2 or any(not r["event"] for r in rows)):
        return None
    if display["kind"] == "partial" and {r["state"] for r in rows} != {"confirmed", "unknown"}:
        return None
    return {**deepcopy(display), "verified": True}


def presentation(response):
    indices = list(range(len(response.get("items", []))))
    if response.get("status") == "needs_clarification":
        return [{"type": "clarification_choices", "item_indices": indices}]
    display = response.get("display", {})
    if display.get("verified") is not True:
        return [{"type": "text", "item_indices": indices}]
    kind = display["kind"]
    if kind == "events":
        groups = {}
        for row in display["items"]:
            groups.setdefault(row["event"], []).append(row)
        ordered = sorted(groups.values(), key=lambda rows: min((r["event_date"] for r in rows if r["event_date"]), default="9999"))
        blocks = [{"type": "event_timeline", "item_indices": [r["index"] for r in rows],
                   "event_date": next((r["event_date"] for r in rows if r["event_date"]), "")} for rows in ordered]
    else:
        blocks = [{"type": {"partial": "claim_coverage", "conflict": "evidence_comparison",
                           "same_event": "evidence_group"}.get(kind, "text"),
                   "item_indices": [r["index"] for r in display["items"]]}]
    shown = {i for b in blocks for i in b["item_indices"]}
    if missing := [i for i in indices if i not in shown]:
        blocks.append({"type": "text", "item_indices": missing})
    return blocks
