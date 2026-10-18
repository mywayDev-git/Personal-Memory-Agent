import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from conftest import memory

from pma.facts import explicit_dates, project, query_plan, relation
from pma.service import Service
from pma.store import Store

WISH = "지연은 생일 선물로 파란색 머그컵을 받고 싶다고 말했다."
GIFT = "나는 지연이한테 생일선물로 빨간색 머그컵을 줬다."


def insert(
    store,
    settings,
    text,
    *,
    actor="self",
    obj="머그컵",
    typ="event",
    when="2026-10-03",
    negated=False,
):
    if when:
        text = when + " " + text
    rid = store.create(text, "2026-10-13T20:00:00+09:00")["record_id"]
    job = store.claim()
    m = memory(text)
    m.update(
        memory_type=typ,
        subject={
            "kind": "self" if actor == "self" else "entity",
            "value": "사용자" if actor == "self" else actor,
            "value_type": "string",
        },
        predicate=text,
        object={"kind": "literal", "value": obj, "value_type": "string"},
        assertion_polarity="negated" if negated else "affirmed",
    )
    m["time"].update(
        start=when,
        precision="day" if when else "unknown",
        certainty="explicit" if when else "uncertain",
    )
    store.publish(job, [m], np.array([[1, 0, 0]]), settings.embedding_key, {})
    return rid


def joined(response):
    return " ".join(item["text"] for item in response["items"])


@pytest.mark.parametrize("reverse", [False, True])
def test_wish_survives_gift_and_distractors(store, settings, models, reverse):
    service = Service(store, models, settings)
    records = [(WISH, "지연"), (GIFT, "self")]
    if reverse:
        records.reverse()
    for text, actor in records:
        insert(store, settings, text, actor=actor)
    for i in range(12):
        insert(store, settings, f"민수{i}는 빨간색 머그컵을 받고 싶다고 말했다.", actor=f"민수{i}")
    answer = service.answer("지연이가 받고 싶다고 한거")
    assert "파란색" in joined(answer) and "빨간색" not in joined(answer)
    assert "빨간색" in joined(service.answer("내가 지연이한테 준 선물은?"))
    assert "빨간색" in joined(service.answer("지연이 받은 선물은?"))
    assert "다릅니다" in joined(service.answer("지연이 원한 것과 내가 준 것이 같아?"))
    assert "판단할 수 없습니다" in joined(service.answer("지연의 취향이 바뀌었어?"))


def test_same_question_before_after_addition(store, settings, models):
    insert(store, settings, WISH, actor="지연")
    service = Service(store, models, settings)
    before = service.answer("지연이가 받고 싶다고 한거")
    insert(store, settings, GIFT)
    after = service.answer("지연이가 받고 싶다고 한거")
    assert joined(before) == joined(after)


@pytest.mark.parametrize(
    "question,expected,forbidden",
    [
        ("나 4km 달린적 있나", None, "5km"),
        ("나 4km 이상 달린적 있나", "5km", "3000m"),
        ("나 4km 미만 달린적 있나", "3000m", "5km"),
        ("나 3km 달린적 있나", "3000m", "5km"),
        ("민수는 몇 km 달렸어?", "4km", "5km"),
        ("나 몇 km 달릴 계획이야?", "4km", "5km"),
    ],
)
def test_distances_roles_and_plans(store, settings, models, question, expected, forbidden):
    insert(store, settings, "나는 한강에서 5km 달렸다.", obj="5km")
    insert(store, settings, "나는 운동장에서 3000m 달렸다.", obj="3000m")
    insert(store, settings, "민수는 4km 달렸다.", actor="민수", obj="4km")
    insert(store, settings, "나는 4km 달리기를 계획했다.", typ="plan", obj="4km")
    answer = Service(store, models, settings).answer(question)
    if expected:
        assert expected in joined(answer)
    else:
        assert answer["status"] == "insufficient_evidence"
    assert forbidden not in joined(answer)


def test_invented_dates_ignored_and_known_date_answered(store, settings, models):
    insert(store, settings, "친구와 다퉜다.", obj="친구", when="2026-10-12")
    models.understand = lambda *a: {
        "intent": "recall",
        "date_from": "2025-10-13",
        "date_to": "2026-10-13",
    }
    answer = Service(store, models, settings).answer("친구와 싸운 게 언제였지", today="2026-10-13")
    assert answer["filters"] == {"date_from": None, "date_to": None}
    assert "2026-10-12" in joined(answer)


def test_unknown_date_not_replaced_by_recording_time(store, settings, models):
    insert(store, settings, "형과 말다툼했다.", obj="형", when=None)
    answer = Service(store, models, settings).answer("형과 말다툼한 날짜는?")
    assert "확인되지 않습니다" in joined(answer)
    assert "2026" not in joined(answer)


def test_as_of_uses_event_time_not_insertion_order(store, settings, models):
    insert(
        store,
        settings,
        "지연은 이제 빨간색 머그컵을 더 좋아한다.",
        actor="지연",
        typ="preference",
        when="2026-10-10",
    )
    insert(
        store,
        settings,
        "지연은 파란색 머그컵을 좋아한다.",
        actor="지연",
        typ="preference",
        when="2026-10-01",
    )
    answer = Service(store, models, settings).answer(
        "10월 5일 기준 지연이 좋아한 컵은?", today="2026-10-13"
    )
    assert "파란색" in joined(answer) and "빨간색" not in joined(answer)
    assert store.links()[0]["kind"] == "preference_change"


def test_relation_dismissal_rebuild_delete_and_purge(store, settings):
    a = insert(store, settings, WISH, actor="지연")
    b = insert(store, settings, GIFT)
    links = store.links(a)
    assert len(links) == 1 and links[0]["basis"] == "inferred"
    assert links[0]["identity_uncertain"]
    store.dismiss_link(links[0]["id"])
    with store.connect(True) as db:
        db.execute("DELETE FROM facts")
    store.rebuild_facts()
    assert store.links() == []
    store.trash(a)
    store.purge(a)
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM dismissed_links").fetchone()[0] == 0
    store.trash(b)
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM facts").fetchone()[0] == 0


def test_edit_and_trash_invalidate_connections(store, settings):
    a = insert(store, settings, WISH, actor="지연")
    b = insert(store, settings, GIFT)
    assert store.links()
    store.update(b, 1, "선물을 아직 주지 않았다.")
    assert store.links() == []
    store.trash(a)
    assert store.links() == []


def test_plan_execution_and_conflict_links(store, settings):
    insert(store, settings, "나는 5km 달리기를 계획했다.", obj="5km", typ="plan")
    insert(store, settings, "나는 5km 달렸다.", obj="5km")
    insert(store, settings, "나는 5km 달리지 않았다.", obj="5km", negated=True)
    assert {r["kind"] for r in store.links()} == {"plan_action", "conflicting_claims"}


def test_old_action_is_not_fulfillment_of_later_plan(store, settings):
    insert(store, settings, "나는 5km 달렸다.", obj="5km", when="2026-10-01")
    insert(store, settings, "나는 5km 달리기를 계획했다.", obj="5km", typ="plan", when="2026-10-10")
    assert store.links() == []


def test_migration_backfills_without_rewriting_history(store, settings):
    rid = insert(store, settings, WISH, actor="지연")
    before = store.revisions(rid)
    with store.connect(True) as db:
        db.execute("DROP TABLE memory_links")
        db.execute("DROP TABLE dismissed_links")
        db.execute("DROP TABLE facts")
        db.execute("PRAGMA user_version=1")
    migrated = Store(store.path)
    assert migrated.get(rid)["facts_status"] == "pending"
    assert migrated.rebuild_facts() == 1
    assert migrated.revisions(rid) == before
    assert migrated.get(rid)["facts_status"] == "ready"
    assert migrated.rebuild_facts() == 0
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3


def test_relations_api_security(client, settings):
    store = client.app.state.store
    insert(store, settings, WISH, actor="지연")
    insert(store, settings, GIFT)
    link = client.get("/api/v1/relations").json()["items"][0]
    assert (
        client.delete("/api/v1/relations/" + link["id"], headers={"X-CSRF-Token": ""}).status_code
        == 403
    )
    assert client.delete("/api/v1/relations/" + link["id"]).status_code == 204
    assert client.get("/api/v1/relations").json()["items"] == []


def test_model_semantic_verification_rejects_supported_id_with_false_claim(store, settings, models):
    insert(store, settings, "담당자를 정했다.", obj="담당자")
    models.verify = lambda *args: False
    response = Service(store, models, settings).answer("어떻게 했지?")
    assert response["status"] == "insufficient_evidence"
    assert response["validation"] == "rejected"


def test_explicit_dates_never_guesses_when_question():
    assert explicit_dates("언제였지?", "2026-10-13")["date_from"] is None
    assert explicit_dates("지난달 무슨 영화?", "2026-10-13") == {
        "date_from": "2026-09-01",
        "date_to": "2026-09-30",
    }


def test_model_invented_event_time_is_removed():
    m = memory(WISH)
    m["time"].update(
        raw="2026-10-03T20:00:00+09:00", start="2026-10-03T20:00:00+09:00", precision="exact"
    )
    fact = project(m, WISH, "2026-10-03T20:00:00+09:00", "2026-10-13T20:00:00+09:00")
    assert fact["event_time"]["start"] is None
    assert fact["warnings"] == ["ungrounded_event_time_removed"]


def test_change_date_question_has_change_semantics():
    plan = query_plan("빨간 컵으로 취향이 바뀐 시점은?", {"intent": "recall"}, "2026-10-13")
    assert plan["kind"] == "change"


@pytest.mark.parametrize("text", ["나는 옆에서 응원했다", "채용에 지원했다"])
def test_support_verbs_are_not_desires(text):
    assert relation(text) == "other"


def test_why_cannot_be_answered_by_repeating_event(store, settings, models):
    insert(store, settings, "친구와 다퉜다.", obj="친구")
    assert (
        Service(store, models, settings).answer("친구랑 왜 싸웠지?")["status"]
        == "insufficient_evidence"
    )


def test_comparison_inference_label_and_dismissal(store, settings, models):
    insert(store, settings, WISH, actor="지연")
    insert(store, settings, GIFT)
    service = Service(store, models, settings)
    response = service.answer("지연이 원한 것과 내가 준 것이 같아?")
    assert response["items"][0]["claim_kind"] == "inference"
    store.dismiss_link(response["items"][0]["relation_ids"][0])
    after = service.answer("지연이 원한 것과 내가 준 것이 같아?")
    assert after["connections"] == []
    assert after["items"][0]["claim_kind"] == "record"
    assert "단정하지 않습니다" in joined(after)


def test_dismissed_evidence_survives_identical_new_revision(store, settings):
    insert(store, settings, WISH, actor="지연")
    rid = insert(store, settings, GIFT)
    saved = store.get(rid)
    store.dismiss_link(store.links()[0]["id"])
    store.update(rid, 1, saved["text"], saved["reference_time"])
    job = store.claim()
    store.publish(job, saved["memories"], np.array([[1, 0, 0]]), settings.embedding_key, {})
    assert store.links() == []


def test_diagnostics_corpus_has_sixty_unique_cases():
    data = json.loads(
        (Path(__file__).parents[1] / "data/relationship_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(data["questions"]) >= 60
    assert len({q["id"] for q in data["questions"]}) == len(data["questions"])
