from copy import deepcopy

import pytest

from pma.chat.source_fact import source_date_draft


def evidence():
    return [{"id": "a", "source_text": "2026년 10월 12일 민수에게 파란색 책을 선물했다.",
             "memory_type": "event", "assertion_polarity": "affirmed",
             "fact": {"state": "observed", "object": "파란색 책", "action_relation": "give",
                      "event_time": {"start": "2026-10-12", "end": None, "precision": "day", "certainty": "explicit"},
                      "time_validation": {"status": "verified"}}}]


def test_explicit_event_date_is_quoted_without_inventing_or_normalizing_a_date():
    rows = evidence()
    result = source_date_draft("민수에게 책을 선물한 날짜는?", rows)
    assert rows[0]["source_text"] in result["items"][0]["text"]
    assert result["items"][0]["citations"] == ["a"]


@pytest.mark.parametrize("change", ["unknown", "unverified", "plan", "negation", "warning", "mismatch", "multiple"])
def test_ambiguous_or_unverified_dates_use_the_existing_generator(change):
    rows = evidence()
    fact = rows[0]["fact"]
    if change == "unknown": fact["event_time"]["certainty"] = "uncertain"
    if change == "unverified": fact["time_validation"]["status"] = "unresolved"
    if change == "plan": fact["state"] = "planned"
    if change == "negation": rows[0]["assertion_polarity"] = "negated"
    if change == "warning": fact["review_reasons"] = ["command_scope"]
    if change == "mismatch": fact["event_time"]["start"] = "2026-10-13"
    if change == "multiple": rows.append({**deepcopy(rows[0]), "id": "b"})
    assert source_date_draft("민수에게 책을 선물한 날짜는?", rows) is None


@pytest.mark.parametrize("question", ["이 기록은 언제 작성됐어?", "책을 받은 날짜는?", "책을 선물한 마지막 날짜는?", "양말을 선물한 날짜는?"])
def test_record_time_direction_and_scope_are_not_inferred(question):
    assert source_date_draft(question, evidence()) is None


def test_background_records_are_kept_and_a_second_undated_target_prevents_shortcut():
    rows = evidence()
    rows.append({"id": "background", "source_text": "공원에서 산책했다.", "fact": {}})
    original = deepcopy(rows)
    assert source_date_draft("민수에게 책을 선물한 날짜는?", rows)
    assert rows == original
    rows.append({"id": "unknown", "source_text": "책을 선물하지 않았다.", "fact": {}})
    assert source_date_draft("민수에게 책을 선물한 날짜는?", rows) is None
