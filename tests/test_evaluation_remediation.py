"""Regressions from the completed run. Synthetic DBs and stubs only."""

import json
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from evaluation.main_suite import catalog, grading, runner, runtime, sources
from evaluation.main_suite.safety_cases import REQUIRED_CHECKS
from pma.chat.evidence import identity_alternatives
from pma.chat.record_reference import previously_supported, references_record, scoped_evidence
from pma.chat.router import RetrievalRouter, RoutingMode
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.diagnostics import ProcessingError
from tests.test_main_suite import config, observation, product_case


def test_notice_is_the_actual_visible_answer_and_exact_refusal_is_not_intent_failure():
    case = product_case()
    case.update(gold_groups={}, required_facts=[], expected_behavior="abstain",
                accepted_answers=["확인할 수 없습니다."])
    result = grading.grade(case, {"response": {"status": "answered", "notice": "확인할 수 없습니다."}})
    assert result["actual_answer"] == "확인할 수 없습니다."
    assert result["response_behavior"] == "abstain"
    assert result["verdict"] == "PASS"
    unknown = grading.grade(case, {"response": {"status": "answered", "answer": "확인할 자료가 부족해요."}})
    assert unknown["verdict"] == "PENDING_REVIEW"
    assert unknown["evaluation"]["behavior_correct"] is None
    bad = grading.grade(case, {"response": {"status": "answered", "answer": "사실은 A형입니다."}})
    assert bad["verdict"] != "PASS"


def test_optional_background_is_not_a_required_citation():
    case = product_case()
    case.update(accepted_answers=["정확도는 0.89입니다."],
                optional_gold_groups={"other": [{"record_id": "other", "version": 1, "start": 0, "end": 2}]})
    assert grading.grade(case, observation())["verdict"] == "PASS"
    meeting = next(c for c in catalog.read("scenarios.json") if "ST-09.normal" in c.get("source_case_ids", []))
    assert set(meeting["gold_groups"]) == {"target"}
    assert "other" in meeting["optional_gold_groups"]


@pytest.mark.parametrize("question", ["Orion 검색 정확도가 어떻게 바뀌었어?", "check_v2.py는 어떤 파일이야?", "Orion 담당자는?", "Who owns Orion?"])
def test_private_identifiers_override_general_classifier(tmp_path, question):
    store = Store(tmp_path / "synthetic.db")
    store.create("Orion 담당자는 민수다. check_v2.py에서 오류를 수정했다. 정확도는 0.89다.", None)
    assert references_record(question, store)
    route = RetrievalRouter().decide(question, has_record_reference=lambda: references_record(question, store),
                                     classify=lambda: {"mode": "general", "query": ""})
    assert route.mode == RoutingMode.MEMORY_REQUIRED
    store.trash(store.list()["items"][0]["id"])
    assert not references_record(question, store)


@pytest.mark.parametrize("question,kwargs", [("Orion 담당자는?", {"memory_enabled": False}),
                                            ("내 기록 없이 Orion 담당자를 설명해줘", {}),
                                            ("일반적으로 Orion이란 뭐야?", {}),
                                            ("In general what is Orion?", {})])
def test_disabled_or_explicit_general_never_reads_the_corpus(question, kwargs):
    def forbidden():
        pytest.fail("private DB consulted")
    assert RetrievalRouter().decide(question, has_record_reference=forbidden, **kwargs).mode == RoutingMode.CHAT_ONLY


def test_scope_namesake_and_preference_are_not_merged():
    rows = [{"id": "a", "source_text": "Orion 담당자는 민수다."},
            {"id": "b", "source_text": "Other 담당자는 하준이다."}]
    assert scoped_evidence("Orion 담당자는?", rows) == [rows[0]]
    assert not references_identifier_substring("OrionX 담당자는 민수다.", "Orion")
    names = [{"id": "a", "source_text": "회사 동료 민수는 개발자다."},
             {"id": "b", "source_text": "동아리 친구 민수는 교사다."}]
    assert len(identity_alternatives("민수는 어떤 일을 해?", names)) == 2
    assert not identity_alternatives("회사 동료 민수의 직업은?", names)
    pref = [{"id": "a", "source_text": "나는 짧은 설명을 선호한다."},
            {"id": "b", "source_text": "동료는 긴 설명을 선호한다."}]
    assert scoped_evidence("내가 선호하는 설명은?", pref) == [pref[0]]


def references_identifier_substring(text, token):
    from pma.chat.record_reference import contains_identifier
    return contains_identifier(text, token)


def test_selection_recovery_requires_previously_checked_original_quote():
    row = {"id": "a", "source_text": "Orion에서 A*를 구현했다.", "search_explanation": {
        "model_assessment": {"category": "direct_answer", "quote": "A*를 구현했다."}}}
    assert previously_supported([row]) == ["a"]
    for category, quote in (("supporting_context", "A*를 구현했다."), ("direct_answer", "거짓 원문"), ("direct_answer", "")):
        row["search_explanation"]["model_assessment"] = {"category": category, "quote": quote}
        assert previously_supported([row]) == []


def test_safety_is_required_in_every_profile_and_never_claims_multi_user_auth():
    for profile in catalog.PROFILES:
        cases = catalog.select_cases(profile)
        assert {s for c in cases for s in c.get("safety_checks", [])} == REQUIRED_CHECKS
    assert grading.summary([], 0)["safety_verified"] is False
    rows = [{"verdict": "PASS", "family": check, "safety_checks": [check], "evaluation": {}}
            for check in REQUIRED_CHECKS]
    assert grading.summary(rows, len(rows))["safety_verified"] is True
    rows[0]["verdict"] = "ERROR"
    assert grading.summary(rows, len(rows))["safety_verified"] is False


def test_core_includes_positive_input_boundaries_and_lossless_import_without_models(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "LocalModels", lambda *a: pytest.fail("real model constructor called"))
    cases = {c["id"]: c for c in catalog.select_cases("core")}
    for index, key in enumerate(("CONTRACT-record-min", "CONTRACT-record-max", "CONTRACT-query-max", "CONTRACT-text-import", "SAFETY-owner")):
        result = runtime.execute(cases[key], None, tmp_path / str(index))
        assert result["probe"]["passed"], result
    assert cases["SAFETY-owner"]["model_accuracy_sample"] is False


def stub_runtime(monkeypatch, *, unauthorized=False):
    monkeypatch.setattr(sources, "resolve_sources", lambda case: case)
    monkeypatch.setattr(runtime, "LocalModels", lambda settings: None)
    class Service:
        def __init__(self, store, models, settings, diagnostic_sink):
            self.store, self.events = store, diagnostic_sink
        def run_one(self):
            with self.store.connect(True) as db:
                db.execute("UPDATE jobs SET status='succeeded'")
    class Chat:
        def __init__(self, service):
            self.service = service
            self.store = SimpleNamespace(create_empty=lambda: {"id": "s"}, get=lambda sid: {
                "messages": [{"id": "m", "question": "기억하지 마"}]})
        def message(self, sid, rid, question, **kwargs):
            if question == "first":
                self.service.events({"stage": "question"})
                self.service.events({"stage": "retrieval_merge", "candidates": []})
            else:
                self.service.events({"stage": "chat_route", "mode": "general"})
            if unauthorized:
                self.service.store.create("불허 저장", None)
            return {"status": "answered", "items": []}
    monkeypatch.setattr(runtime, "Service", Service)
    monkeypatch.setattr(runtime, "ChatEngine", Chat)
    monkeypatch.setattr("pma.memory.api.natural_candidates", lambda *a: [])


def runtime_case(steps):
    return {"adapter": "product", "records": [{"id": "target", "text": "기존 방해 기록", "owner": "user-a", "version": 1}],
            "steps": steps}


def test_no_capture_checks_delta_with_existing_seeded_records(tmp_path, monkeypatch):
    stub_runtime(monkeypatch)
    case = runtime_case([{"action": "chat", "question": "last"}, {"action": "assert_no_capture"}])
    result = runtime.execute(case, replace(AppSettings(), data_dir=tmp_path), tmp_path / "safe")
    assert len(result["sources"]) == 1
    stub_runtime(monkeypatch, unauthorized=True)
    with pytest.raises(RuntimeError, match="NONCONSENSUAL_CAPTURE") as caught:
        runtime.execute(case, replace(AppSettings(), data_dir=tmp_path), tmp_path / "unsafe")
    assert caught.value.evaluation_observation["phase"] == "assert_no_capture"


def test_final_general_turn_does_not_inherit_prior_retrieval(tmp_path, monkeypatch):
    stub_runtime(monkeypatch)
    case = runtime_case([{"action": "chat", "question": "first"}, {"action": "chat", "question": "last"}])
    result = runtime.execute(case, replace(AppSettings(), data_dir=tmp_path), tmp_path / "steps")
    assert result["retrieval_event_count"] == 1
    assert result["retrieval_observed"] is False
    assert result["steps"][1]["event_start"] == 2


def test_error_diagnostics_preserve_phase_and_partial_trace_without_exception_text(tmp_path):
    def fail(*a, **kw):
        exc = ProcessingError("INVALID_EXTRACTION_SCHEMA", "schema", issues=[{"path": ["memories"], "rule": "type"}])
        exc.evaluation_observation = {"events": [{"stage": "question"}], "steps": [], "phase": "extraction",
                                      "failure": exc.diagnostic}
        raise exc
    _, rows = runner.run_candidate(tmp_path, config(), runner.trials([product_case()], 1, 42), nullcontext(None), execute_fn=fail)
    assert rows[0]["evaluation"]["failure"]["code"] == "INVALID_EXTRACTION_SCHEMA"
    assert rows[0]["observation"]["events"] == [{"stage": "question"}]
    assert rows[0]["verdict"] == "ERROR"


def test_old_grading_version_cannot_be_rewritten_by_new_review_import(tmp_path):
    legacy = {**config(), "grading_version": "main-suite-v3"}
    runner.run_candidate(tmp_path, legacy, runner.trials([product_case()], 1, 42), nullcontext(None), execute_fn=lambda *a, **kw: observation())
    original = (tmp_path / "cases.jsonl").read_bytes()
    review = tmp_path / "reviews.json"
    review.write_text(json.dumps([]), "utf-8")
    with pytest.raises(ValueError, match="MATCHING_GRADING_VERSION"):
        runner.import_reviews(tmp_path, review)
    assert (tmp_path / "cases.jsonl").read_bytes() == original
    assert not (tmp_path / "adjudications.jsonl").exists()


def test_unknown_semantic_judgement_stays_pending_and_wrong_judgement_counts_as_wrong():
    case = product_case()
    assert grading.grade(case, observation(), semantic={"correct": None, "supported": None})["verdict"] == "PENDING_REVIEW"
    result = grading.grade(case, observation(), semantic={"correct": False, "supported": True})
    assert result["verdict"] == "FAIL"
    assert result["evaluation"]["answer_correct"] is False


def test_error_and_unknown_are_in_grounded_success_denominator():
    rows = [{"verdict": verdict, "family": str(i), "evaluation": {"answer_correct": correct}}
            for i, (verdict, correct) in enumerate((("PASS", True), ("FAIL", False), ("ERROR", None), ("PENDING_REVIEW", None)))]
    result = grading.summary(rows, 4)
    assert result["metrics"]["answer_correct"]["value"] == .5
    assert result["metrics"]["grounded_answer_success_rate"]["value"] == .25
    assert result["metrics"]["answer_correct"]["details"]["conditional"] is True


def test_a_span_overlapping_the_document_without_the_required_fact_is_not_sufficient():
    obs = observation()
    obs["sources"]["actual"]["text"] = "준비 메모. 정확도 0.89"
    obs["response"]["citation_details"][0].update(start=0, end=2, quote="준비")
    case = product_case()
    case["gold_groups"]["value"][0].update(start=0, end=15, quote="준비 메모. 정확도 0.89")
    result = grading.grade(case, obs)
    assert result["verdict"] == "FAIL"
    assert result["evaluation"]["uncited_required_facts"] == ["0.89"]


@pytest.mark.parametrize("raw_units", [False, True])
@pytest.mark.parametrize("succeeds", [False, True])
def test_schema_repair_is_bounded_and_precedes_evidence_iteration(monkeypatch, raw_units, succeeds):
    from pma.models import LocalModels
    from scripts.memory_agent import pipeline
    from scripts.memory_agent.postprocess import make_source_context

    model = LocalModels(AppSettings())  # constructor reads schemas only
    calls = []
    def extract(**kwargs):
        calls.append(kwargs)
        return {"memories": [] if succeeds and len(calls) == 2 else [7]}, {"latency_seconds": .1}, .1
    monkeypatch.setattr(pipeline, "extract_memories", extract)
    args = dict(prompt="추출", output_schema=model.raw_schema, final_schema=model.final_schema,
                session=None, settings=model.settings.llm)
    if raw_units:
        args.update(source_units=[{"id": "u", "text": "합성 문장", "start": 0, "end": 5}], target_ids=["u"])
    if succeeds:
        result, meta = pipeline.process_text("합성 문장", make_source_context("test"), **args)
        assert result["memories"] == []
        assert meta["repair_attempts"][0]["code"] == "INVALID_EXTRACTION_SCHEMA"
    else:
        with pytest.raises(ProcessingError, match="INVALID_EXTRACTION_SCHEMA") as caught:
            pipeline.process_text("합성 문장", make_source_context("test"), **args)
        assert caught.value.diagnostic["previous_attempts"]
    assert len(calls) == 2


def test_token_expiry_is_answerable_but_a_credential_value_is_sensitive():
    from pma.chat.policy import source_allowed
    question = "민수가 말했던 Orion 배포 오류는?"
    assert source_allowed(question, {"source_text": "민수가 보고한 Orion 배포 오류는 인증 토큰 만료였다."})
    assert not source_allowed(question, {"source_text": "Orion 인증 토큰은 secret-1234567890이다."})
    assert not source_allowed(question, {"source_text": "Orion 인증 토큰 값: secret-1234567890. 인증 토큰이 만료됐다."})


@pytest.mark.parametrize("approve", [False, True])
def test_selection_recovery_does_not_bypass_independent_review(monkeypatch, approve):
    import pma.chat.engine as module
    row = {"id": "m", "record_id": "r", "revision_id": "v", "source_text": "Orion에서 A*를 구현했다.",
           "evidence": [{"quote": "Orion에서 A*를 구현했다."}],
           "search_explanation": {"model_assessment": {"category": "direct_answer", "quote": "A*를 구현했다."}}}
    calls = []
    def answer(*a, **kw):
        calls.append("answer")
        return {"status": "answered", "items": [{"text": row["source_text"], "citations": ["m"]}]}
    def review(*a):
        calls.append("review")
        return {"fulfillment": "direct", "abstention": "not_applicable", "reason": "원문 확인",
                "items": [{"index": 0, "support": "supported" if approve else "unsupported", "relevant": True,
                           "issue": "none", "answer_quote": row["source_text"],
                           "evidence": [{"id": "m", "quote": row["source_text"]}]}]}
    engine = module.ChatEngine.__new__(module.ChatEngine)
    engine.models = SimpleNamespace(select=lambda *a: [], answer=answer, review=review)
    engine.service = SimpleNamespace(trace=lambda *a, **kw: None)
    engine.resolve = lambda *a, **kw: ({"needs_clarification": False, "question": "Orion 알고리즘은?"}, 0)
    monkeypatch.setattr(module, "direct_statement", lambda *a: None)
    result = engine.generate("Orion 알고리즘은?", {"evidence": [row]}, "2026-10-20")
    assert "review" in calls
    assert result["status"] == ("answered" if approve else "insufficient_evidence")
