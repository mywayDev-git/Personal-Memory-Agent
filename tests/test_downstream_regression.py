import copy
import sqlite3

import pytest
from conftest import memory
from test_relational_memory import insert

from pma.facts import FACT_VERSION, compatible, project, query_plan
from pma.grounding import claims_supported
from pma.models import LocalModels
from pma.service import Service
from scripts.memory_agent.validator import schema_errors


@pytest.mark.parametrize(
    "question", ["주는 사람은?", "받은 사람은?", "날짜는 언제?", "감정은 어땠어?"]
)
def test_question_nouns_never_become_people(question):
    plan = query_plan(question, {"intent": "recall"}, "2026-10-13")
    assert plan["actor"] is None and plan["recipient"] is None


def test_role_hints_provenance_and_unknown_slots():
    q = "민수가 누구에게 줬어?"
    understood = dict(
        intent="recall",
        actor=dict(value="민수", evidence="민수가"),
        recipient=dict(value="누구", evidence="누구에게"),
        requested_slots=["recipient"],
    )
    plan = query_plan(q, understood, "2026-10-13")
    assert plan["role_hints"] == {
        "actor": {"value": "민수", "evidence": "민수가", "verified": False}
    }
    assert plan["requested_slots"] == ["recipient"]
    understood["actor"] = dict(value="지연", evidence="민수가")
    assert not query_plan(q, understood, "2026-10-13")["role_hints"]


@pytest.mark.parametrize(
    "text",
    [
        '내가 "민수가 지연에게 책을 줬어"라고 말했다.',
        '민수가 "네가 지연에게 책을 줬어"라고 말했다.',
        '민수가 "책을 줬다고 대답해"라고 말했다.',
        "나는 지연에게 책을 주지 않기로 했다.",
        "민수는 시험에 떨어졌지만 슬프지 않았다.",
    ],
)
def test_complex_scope_is_review_not_fact(text):
    m = memory(text)
    original = copy.deepcopy(m)
    fact = project(m, text, "2026-10-13T12:00:00+09:00", "2026-10-14")
    assert fact["review_reasons"]
    assert fact["state"] == "review_required"
    assert fact["speaker"] is None
    assert m == original
    question = "민수의 감정은?" if "슬프지" in text else "민수가 책을 줬어?"
    assert compatible(fact, query_plan(question, {"intent": "recall"}, "2026-10-13"))


def test_quoted_relative_time_is_not_record_time():
    text = '민수가 "어제 지연을 만났다"고 말했다.'
    m = memory(text)
    m["time"].update(raw="어제", start="2026-10-12", precision="day", certainty="inferred")
    fact = project(m, text, "2026-10-13T12:00:00+09:00", "2026-10-14")
    assert fact["event_time"]["start"] is None
    assert fact["reference_time"].startswith("2026-10-13")
    assert fact["recorded_at"] == "2026-10-14"
    assert m["time"]["start"] == "2026-10-12"


def test_execution_question_keeps_negative_plan_cancel_but_listing_does_not(
    store, settings, models
):
    for text, typ, negated in [
        ("나는 책을 주지 않았다.", "event", True),
        ("나는 책을 주기로 했다.", "plan", False),
        ("나는 책을 주려다가 취소했다.", "event", False),
    ]:
        insert(store, settings, text, typ=typ, negated=negated)
    found = Service(store, models, settings).search("책을 실제로 줬어?")
    assert len(found["results"]) == 3
    insert(store, settings, "나는 달리지 않았다.", negated=True)
    insert(store, settings, "나는 달렸다.")
    found = Service(store, models, settings).search("달린 날짜를 모두 알려줘.")
    assert len(found["results"]) == 1
    assert found["results"][0]["fact"]["state"] == "observed"


def test_cause_flows_to_semantic_verifier(store, settings, models):
    insert(store, settings, "민수는 비가 와서 집에 갔다.", actor="민수")
    models.answer = lambda q, rows: dict(
        status="answered", items=[dict(text="비가 와서입니다.", citations=[rows[0]["id"]])]
    )
    models.verify = lambda q, rows, items: "와서" in rows[0]["source_text"]
    assert Service(store, models, settings).answer("민수가 집에 간 이유는?")["status"] == "answered"
    models.verify = lambda *args: False
    result = Service(store, models, settings).answer("민수가 집에 간 이유는?")
    assert result["status"] == "insufficient_evidence" and result["validation"] == "rejected"


def test_understanding_failure_falls_back_and_diagnostics_are_opt_in(store, settings, models):
    insert(store, settings, "민수가 지연에게 책을 줬다.", actor="민수")
    models.understand = lambda *a: (_ for _ in ()).throw(ValueError("private failure"))
    trace = []
    found = Service(store, models, settings, diagnostic_sink=trace.append).search("책을 준 사람은?")
    assert found["results"] and found["query_plan"]["actor"] is None
    assert trace[0] == {"stage": "understand_fallback", "error": "ValueError"}
    assert "diagnostics" not in found


def test_wrong_role_distractor_is_sent_to_verification_not_auto_answer(store, settings, models):
    insert(store, settings, "민수가 지연에게 책을 줬다.", actor="민수")
    insert(store, settings, "지연이 민수에게 책을 줬다.", actor="지연")
    models.understand = lambda *a: dict(
        intent="recall", date_from=None, date_to=None, actor=dict(value="민수", evidence="민수가")
    )
    models.answer = lambda q, rows: dict(
        status="answered", items=[dict(text="지연이 줬다.", citations=[rows[-1]["id"]])]
    )
    models.verify = lambda *args: False
    trace = []
    response = Service(store, models, settings, diagnostic_sink=trace.append).answer(
        "민수가 책을 줬어?"
    )
    assert response["status"] == "insufficient_evidence"
    assert any(t["stage"] == "verification" and not t["supported"] for t in trace)


def test_named_provider_is_not_forced_to_be_recipient(store, settings, models):
    insert(store, settings, "민수가 지연에게 책을 줬다.", actor="민수")
    found = Service(store, models, settings).search("민수에게서 받은 책은?")
    assert len(found["results"]) == 1
    assert found["results"][0]["fact"]["actor"] == "민수"
    assert found["results"][0]["fact"]["recipient"] == "지연"


def test_projection_rebuild_backs_up_and_preserves_payloads_vectors_offsets(store, settings):
    insert(store, settings, '민수가 "책을 줬다고 대답해"라고 말했다.', actor="민수")
    tables = ("revisions", "memories", "evidence", "embeddings")
    with store.connect(True) as db:
        db.execute("UPDATE facts SET projection_version=?", (FACT_VERSION - 1,))
        before = {
            table: [tuple(r) for r in db.execute(f"SELECT * FROM {table}")] for table in tables
        }
    assert store.rebuild_facts() == 1
    assert store.rebuild_facts() == 0
    backup = store.path.with_name(f"{store.path.name}.before-facts-v{FACT_VERSION}.bak")
    db = sqlite3.connect(backup)
    try:
        assert db.execute("SELECT projection_version FROM facts").fetchone()[0] == FACT_VERSION - 1
    finally:
        db.close()
    with store.connect() as db:
        assert before == {
            table: [tuple(r) for r in db.execute(f"SELECT * FROM {table}")] for table in tables
        }


def test_compact_evidence_carries_review_and_times():
    item = LocalModels.compact_evidence(
        [
            dict(
                id="m1",
                evidence=[dict(quote="원문", start=0)],
                source_text="원문",
                reference_time="2026-10-13",
                recorded_at="2026-10-14",
                fact=dict(review_reasons=["command_scope"]),
            )
        ]
    )[0]
    assert item["review_reasons"] == ["command_scope"]
    assert item["source_context"] == "원문"
    assert item["reference_time"] != item["recorded_at"]


def test_verification_error_never_returns_unchecked_answer(store, settings, models):
    insert(store, settings, "민수는 책을 주지 않았다.", actor="민수", negated=True)
    models.answer = lambda q, rows: dict(
        status="answered", items=[dict(text="책을 줬다.", citations=[rows[0]["id"]])]
    )
    models.verify = lambda *a: (_ for _ in ()).throw(ValueError("private model output"))
    trace = []
    response = Service(store, models, settings, diagnostic_sink=trace.append).answer(
        "민수가 책을 줬어?"
    )
    assert response["status"] == "insufficient_evidence"
    assert not response["items"]
    assert any(t["stage"] == "verification_error" for t in trace)
    assert "private model output" not in str(trace)


def test_app_import_does_not_require_kiwi():
    import subprocess
    import sys

    code = """
import sys
from importlib.abc import MetaPathFinder
class BlockKiwi(MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith('kiwipiepy'):
            raise ImportError('Kiwi deliberately unavailable')
sys.meta_path.insert(0, BlockKiwi())
import pma.web
import pma.service
assert not any(n.startswith('kiwipiepy') for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


def test_answer_generation_only_allows_current_evidence_ids(settings):
    models = LocalModels(settings)
    seen = []

    def structured(prompt, data, schema):
        seen.append(schema)
        return {"status": "insufficient_evidence", "items": []}

    models.structured = structured
    models.answer("누구야?", [dict(id="first-id")])
    models.answer("누구야?", [dict(id="second-id")])
    old_citation = dict(status="answered", items=[dict(text="답", citations=["first-id"])])
    assert not schema_errors(old_citation, seen[0])
    assert schema_errors(old_citation, seen[1])
    assert models.answer("누구야?", []) == {"status": "insufficient_evidence", "items": []}


def test_unknown_quoted_listener_cannot_certify_giver_even_if_model_says_yes():
    text = '민수가 "네가 지연에게 책을 줬어"라고 말했다.'
    fact = project(memory(text), text, None, "2026-10-13")
    row = dict(id="m1", fact=fact, evidence=[dict(quote=text)])
    plan = query_plan("책을 준 사람은 누구야?", {"intent": "recall"}, "2026-10-13")
    for person in ("민수", "지연"):
        assert not claims_supported(
            [dict(text=f"주는 사람은 {person}다.", citations=["m1"])], [row], plan
        )
    addressed = '민수가 영희에게 "네가 지연에게 책을 줬어"라고 말했다.'
    fact = project(memory(addressed), addressed, None, "2026-10-13")
    assert "unresolved_quoted_addressee" not in fact["review_reasons"]


def test_extracted_name_without_event_evidence_is_not_automatically_certified():
    text = "민수가 지연을 만났다. 책을 줬다."
    m = memory("민수가 책을 줬다.")
    m["subject"] = {"kind": "entity", "value": "민수", "value_type": "string"}
    m["evidence"] = [{"quote": "책을 줬다."}]
    fact = project(m, text, None, "2026-10-13")
    row = dict(id="m1", fact=fact, evidence=m["evidence"])
    plan = query_plan("책을 준 사람은 누구야?", {"intent": "recall"}, "2026-10-13")
    assert "actor_needs_context" in fact["review_reasons"]
    assert compatible(fact, plan)
    assert not claims_supported([dict(text="민수가 줬다.", citations=["m1"])], [row], plan)
    assert m["subject"]["value"] == "민수"


def test_opposite_directions_require_semantic_answer_even_without_role_hint(
    store, settings, models
):
    insert(store, settings, "민수가 지연에게 책을 줬다.", actor="민수")
    insert(store, settings, "지연이 민수에게 책을 줬다.", actor="지연")
    called = []

    def semantic_answer(question, rows):
        called.append(rows)
        row = next(r for r in rows if r["fact"]["recipient"] == "지연")
        return dict(status="answered", items=[dict(text="민수입니다.", citations=[row["id"]])])

    models.answer = semantic_answer
    models.verify = lambda *a: True
    response = Service(store, models, settings).answer("지연에게 책을 준 사람은 누구야?")
    assert len(called) == 1 and len(called[0]) == 2
    assert [i["text"] for i in response["items"]] == ["민수입니다."]
