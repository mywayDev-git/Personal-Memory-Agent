"""Regression contracts for E01-E10; no model server or personal DB required."""

import itertools
import json
import sqlite3
from copy import deepcopy

import numpy as np
import pytest
from test_search_explain import row, service
from test_search_expressions import BASE, edit, expanded_service

from pma.facts import FACT_VERSION, project, query_plan, relation
from pma.models import UNEXPANDED_SCHEMA, LocalModels
from pma.search_expressions import TOKEN, build_expansion
from pma.settings import AppSettings
from pma.store import Store


def memory(text, topic="머신러닝"):
    return {"content": text, "predicate": "공부했다", "subject": {"kind": "self"},
            "object": {"value": topic}, "memory_type": "event", "assertion_polarity": "affirmed",
            "evidence": [{"quote": text}], "time": {"raw": None, "start": None,
            "end": None, "precision": "unknown", "certainty": "uncertain"}}


@pytest.mark.parametrize("topic", ["머신러닝", "머신러닝이란", "머신러닝과는", "딥러닝입문", "기계 학습", "머신러닝과는 달리 딥러닝"])
def test_e01_query_and_persisted_projection_share_topic_protection(topic):
    text = topic + " 공부 기록"
    assert query_plan(text, BASE, "2026-10-19")["relation"] == "other"
    fact = project(memory(text), text, None, "2026-10-19")
    assert (fact["relation"], fact["action_relation"], fact["object_key"]) == ("other", "other", "머신러닝")
    record = row(1, text)
    record["fact"].update(relation="other", object_key="머신러닝")
    assert service([record])._search(text)[1]["results"]
    assert relation(text + " 이후 실제로 달렸다") == "run"


@pytest.mark.parametrize("suffix", ["를", "은", "으로도", "에서는", "과는"])
def test_e02_stem_and_whole_word_keep_original_particles(suffix):
    q = "😀 쿠버네티스" + suffix + " 공부"
    variants = [edit("쿠버네티스", "Kubernetes", start=2),
                edit("쿠버네티스" + suffix, "Kubernetes", start=2),
                edit("쿠버네티스" + suffix, "Kubernetes" + suffix, start=2)]
    for change in variants:
        result = build_expansion(q, [change], [], BASE)
        assert result["queries"][0]["query"] == "😀 kubernetes" + suffix + " 공부"
        accepted = result["edits"][0]
        assert q[accepted["start"]:accepted["end"]] == accepted["before"]


def test_e03_unrelated_name_does_not_change_receipt_expansion():
    q = "영수증 기록"
    change = edit("영수증", "receipt")
    plain = build_expansion(q, [change], [], BASE)
    known = build_expansion(q, [change], [{"fact": {"actor": "영수"}}], BASE)
    assert plain["queries"] == known["queries"] and known["status"] == "applied"
    assert build_expansion("영수는", [edit("영수는", "receipt")],
                           [{"fact": {"actor": "영수"}}], BASE)["rejected"][0]["reason"] == "protected_entity"


@pytest.mark.parametrize("before,after,kind,reason", [
    ("학습", "notebook", "translation", "verification_required"),
    ("학습", " ", "similar", "empty_expression"),
    ("학습", "...", "similar", "empty_expression"),
    ("학습", "___", "similar", "empty_expression"),
    ("민수", "Minsu", "translation", "verification_required"),
    ("서울", "Seoul", "translation", "verification_required"),
    ("고양이", "cat", "translation", "verification_required"),
    ("자바섬", "Java", "translation", "verification_required"),
])
def test_e04_e05_e09_unverified_candidates_never_run(before, after, kind, reason):
    result = build_expansion(before, [edit(before, after, kind)], [], BASE)
    assert result["queries"] == []
    assert result["rejected"][0]["reason"] == reason
    svc, calls = expanded_service([row(1)], [edit(before, after, kind)])
    found = svc._search(before)[1]
    assert len(calls) == 1 and len(calls[0]) == 1
    assert found["results"] and not found["query_expansion"]["searched"]


@pytest.mark.parametrize("q,before,after", [
    ("C++ 자료", "C", "씨"), ("C#12 자료", "C", "씨"),
    ("api_key 자료", "api", "에이피아이"), ("Node.js 자료", "Node", "노드"),
    ("Ｃ＋＋ 자료", "Ｃ", "씨"), ("C++ 자료", "C++", "씨플러스플러스"),
    ("API-key 자료", "API", "에이피아이"), ("api/v1 자료", "api", "에이피아이"),
])
def test_e06_identifier_spans_cannot_be_edited(q, before, after):
    result = build_expansion(q, [edit(before, after)], [], BASE)
    assert result["rejected"][0]["reason"] == "protected_identifier"
    assert result["queries"] == []


def test_versioned_identifiers_remain_whole_tokens():
    assert TOKEN.findall("C++17 C#12 api_key") == ["C++17", "C#12", "api_key"]


def test_shared_context_does_not_bypass_ambiguous_word_validation():
    wrong = build_expansion("코드 리뷰", [edit("코드 리뷰", "chord 리뷰")], [], BASE)
    assert wrong["rejected"][0]["reason"] == "ambiguous_expression"
    valid = build_expansion("코드 리뷰", [edit("코드 리뷰", "code 리뷰")], [], BASE)
    assert valid["status"] == "applied"
    assert build_expansion("refrigerator 자료", [edit("refrigerator 자료", "냉장고 자료")], [], BASE)["status"] == "applied"
    assert build_expansion("Java 여행", [edit("Java", "자바")], [], BASE)["status"] == "rejected"


def test_mixed_event_evaluation_contract():
    from evaluation.search_accuracy import evaluate
    report = evaluate()
    assert report["summary"]["exact_sets"] == report["summary"]["cases"]
    for key in ("wrong_filter_questions", "wrong_expansion_approvals", "valid_expansion_rejections"):
        assert report["summary"][key] == 0
    assert {r["relation"] for r in report["records"]} >= {None, "run", "other"}


@pytest.mark.parametrize("before,after", [("plant", "식물"), ("planet", "행성"),
                                        ("식물", "plant"), ("행성", "planet")])
def test_e07_regular_words_are_not_planning_expressions(before, after):
    assert build_expansion(before, [edit(before, after)], [], BASE)["status"] == "applied"
    assert build_expansion("planned", [edit("planned", "식물")], [], BASE)["status"] == "rejected"


def test_e08_permutations_have_identical_weights_queries_and_cap():
    q = "학습 기록"
    changes = [edit("학습", "learning", "similar"), edit("학습", "learning"),
               edit("학습", "공부", "similar"), edit("학습", "studying")]
    signatures = []
    for variant in itertools.permutations(changes):
        result = build_expansion(q, list(variant), [], BASE)
        signatures.append((result["queries"], result["edits"], result["rejected"]))
    assert all(s == signatures[0] for s in signatures)
    assert signatures[0][0][0]["weight"] == 0.8


def test_e10_disabled_mode_controls_prompt_schema_and_legacy_gateways(monkeypatch):
    import pma.models as module
    seen = []
    local = LocalModels(AppSettings())
    local.budget = lambda *args: None
    def chat(*args, **kwargs):
        seen.append((args[2], kwargs["output_schema"]))
        return json.dumps(BASE), None, None
    monkeypatch.setattr(module, "chat", chat)
    svc = service([row(1)])
    svc.models.understand = local.understand
    found = svc._search("학습", correction_enabled=False)[1]
    assert seen[0][1] is UNEXPANDED_SCHEMA
    assert "expansions" not in str(seen[0])
    assert found["query_expansion"]["generation_control_supported"] is True
    legacy = service([row(1)])._search("학습", correction_enabled=False)[1]
    assert legacy["query_expansion"]["reason"] == "disabled"
    assert legacy["query_expansion"]["generation_control_supported"] is False


def test_internal_typeerror_does_not_retry_model():
    svc = service([row(1)])
    calls = []
    def understand(q, today, *, expand=True):
        calls.append(expand)
        raise TypeError("internal model failure")
    svc.models.understand = understand
    svc._search("학습", correction_enabled=False)
    assert calls == [False]


def test_original_top_eight_remain_in_24_candidate_review_pool():
    records = [row(i, ("공부 " if i < 20 else "learning ") + str(i)) for i in range(40)]
    for i, r in enumerate(records):
        r["fact"].update(relation="other", object_key="learning")
        r["vector"] = np.array([1, 0] if i < 20 else [0, 1], dtype="<f4").tobytes()
    svc, _ = expanded_service(records, [edit("학습", "learning")])
    svc.models.embed = lambda queries: [[1, 0] if q == "학습" else [0, 1] for q in queries]
    original = svc._search("학습", correction_enabled=False)[1]
    reviewed = []
    svc.models.select = lambda q, rows: reviewed.extend(deepcopy(rows)) or [r["id"] for r in rows]
    svc._search("학습")
    assert {r["id"] for r in original["results"]} <= {r["id"] for r in reviewed}
    assert len(reviewed) == 24
    assert sum(r["search_explanation"]["original_candidate_reserved"] for r in reviewed) == 8


def test_v8_facts_rebuild_without_losing_search_or_sources(tmp_path):
    store = Store(tmp_path / "memory.db")
    texts = ["머신러닝을 공부했다.", "딥러닝이란 무엇인지 공부했다.", "실제로 달렸다."]
    for i, text in enumerate(texts):
        created = store.create(text, None)
        m = memory(text)
        with store.connect(True) as db:
            rev = db.execute("SELECT id FROM revisions WHERE record_id=?", (created["record_id"],)).fetchone()[0]
            db.execute("INSERT INTO memories VALUES(?,?,?,?,?)", (str(i), rev, created["job_id"], "local", json.dumps(m, ensure_ascii=False)))
            db.execute("INSERT INTO evidence VALUES(?,?,?,?,?)", (str(i), 0, text, 0, len(text)))
            db.execute("INSERT INTO embeddings VALUES(?,?,?,?)", (str(i), "test", 1, b"\x00\x00\x80\x3f"))
            db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?)", (str(i), 8, "self", None, "달리기", "{}", "old"+str(i)))
            db.execute("UPDATE records SET status='ready' WHERE id=?", (created["record_id"],))
    before_generation, before = store.snapshot("test")
    assert {r["id"]: r["fact"]["relation"] for r in before} == {"0": "other", "1": "other", "2": "run"}
    assert store.rebuild_facts(limit=1) == 1
    assert len(store.snapshot("test")[1]) == 3
    assert store.rebuild_facts(limit=1) == 1
    assert store.rebuild_facts(limit=1) == 1
    assert store.rebuild_facts(limit=1) == 0
    generation, after = store.snapshot("test")
    assert generation > before_generation
    assert before == after
    assert all(r["fact"]["projection_version"] == FACT_VERSION for r in after)
    backup = tmp_path / f"memory.db.before-facts-v{FACT_VERSION}.bak"
    assert backup.exists()
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT count(*) FROM facts WHERE projection_version=8").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM evidence").fetchone()[0] == 3
