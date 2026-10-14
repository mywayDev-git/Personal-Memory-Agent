import numpy as np
import pytest
from conftest import memory

from pma.facts import connection, explicit_dates
from pma.service import Service


@pytest.mark.parametrize(
    "question,start,end",
    [
        ("작년 10월 3일에 무슨 일 있었지?", "2025-10-03", "2025-10-03"),
        ("올해 2월 3일에 뭐 했어?", "2026-02-03", "2026-02-03"),
        ("작년 2월 기록", "2025-02-01", "2025-02-28"),
        ("2024년 2월 기록", "2024-02-01", "2024-02-29"),
        ("어제부터 오늘까지 달린 기록", "2026-10-12", "2026-10-13"),
        ("10월 3일부터 10월 5일까지", "2026-10-03", "2026-10-05"),
        ("2026-02-30 기록", None, None),
        ("10월 5일부터 10월 3일까지", None, None),
    ],
)
def test_specific_calendar_constraints(question, start, end):
    assert explicit_dates(question, "2026-10-13") == {"date_from": start, "date_to": end}


@pytest.mark.parametrize("state", ["planned", "negated", "uncertain"])
@pytest.mark.parametrize("reverse", [False, True])
def test_wish_links_require_actual_gift(state, reverse):
    wish = dict(
        object_key="머그컵",
        relation="desire",
        state="desire",
        actor="지연",
        recipient=None,
        identity="name_only",
    )
    gift = dict(wish, relation="give", state=state, actor="self", recipient="지연")
    pair = (gift, wish) if reverse else (wish, gift)
    assert connection(*pair) is None
    gift["state"] = "observed"
    assert connection(*pair)["kind"] == "desire_action"
    gift["warnings"] = ["role_conflict"]
    assert connection(*pair) is None


def test_repeated_quote_keeps_its_own_date_after_storage_and_rebuild(store, settings):
    text = "2026-10-01\n나는 달렸다.\n2026-10-03\n나는 달렸다."
    quote = "나는 달렸다."
    start = text.rfind(quote)
    store.create(text, None)
    job = store.claim()
    item = dict(memory(quote), memory_type="event")
    store.publish(
        job,
        [item],
        np.array([[1, 0, 0]]),
        settings.embedding_key,
        {"provenance": [{"evidence": [{"start": start, "end": start + len(quote)}]}]},
    )
    for rebuild in (False, True):
        if rebuild:
            with store.connect(True) as db:
                db.execute("UPDATE facts SET projection_version=0")
            store.rebuild_facts()
        row = store.snapshot(settings.embedding_key)[1][0]
        assert row["fact"]["event_time"]["start"] == "2026-10-03"
        assert row["fact"]["evidence"][0]["start"] == start


def test_comparison_does_not_describe_planned_gift_as_actual(store, settings, models):
    from test_relational_memory import insert, joined

    insert(store, settings, "지연은 파란색 머그컵을 받고 싶다고 말했다.", actor="지연")
    insert(store, settings, "나는 지연에게 빨간색 머그컵을 주기로 했다.", typ="plan")
    answer = Service(store, models, settings).answer("지연이 원한 것과 내가 준 것이 같아?")
    assert not answer["connections"]
    assert "실제 선물 기록은 있지만" not in joined(answer)
    assert "색상이 다릅니다" not in joined(answer)
    assert "계획·결정 기록" in joined(answer)
