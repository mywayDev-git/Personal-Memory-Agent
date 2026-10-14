import copy
import json

import pytest

from evaluation import retrieval_audit as audit
from evaluation.query_tree import digest


def test_rejection_mechanism_separates_code_and_model(monkeypatch):
    arm = dict(
        selected=[{}],
        response=dict(status="insufficient_evidence", items=[]),
        answer_trace=[
            dict(stage="draft", response=dict(status="answered", items=[{}])),
            dict(stage="verify", supported=False),
        ],
    )
    monkeypatch.setattr(audit, "claims_supported", lambda *_: False)
    assert audit.mechanism(arm) == "code_attribute_rejection"
    monkeypatch.setattr(audit, "claims_supported", lambda *_: True)
    assert audit.mechanism(arm) == "model_verification_rejection"


def fixture_run(tmp_path):
    def save(name, value):
        p = tmp_path / name
        p.parent.mkdir(exist_ok=True, parents=True)
        p.write_text(json.dumps(value), encoding="utf-8")

    save("manifest.json", dict(files={}))
    response = dict(status="answered", items=[dict(text="답", citations=["m"])])
    arm = dict(
        response=response,
        selected=[],
        answer_trace=[],
        total_seconds=1,
        metrics=dict(delivered=dict(all_required=True)),
    )
    case = dict(
        status="complete",
        case="qt-phrasing-4",
        scale=0,
        question="질문",
        expected="답",
        arms={k: copy.deepcopy(arm) for k in "ABCDEF"},
        calls=[],
        analysis=dict(status="ok"),
    )
    save("results/case.json", case)
    reviews = [
        dict(
            case=case["case"],
            scale=0,
            condition=k,
            response_hash=digest(response),
            judgment="correct",
            reason="원문 대조",
        )
        for k in "ABCDEF"
    ]
    return save, reviews


def test_review_hash_must_match_current_answer(tmp_path):
    save, reviews = fixture_run(tmp_path)
    reviews[0]["response_hash"] = "wrong hash"
    save("reviews.json", reviews)
    with pytest.raises(ValueError, match="does not match"):
        audit.build(tmp_path)


def test_strict_report_cannot_pass_with_missing_cases(tmp_path):
    save, reviews = fixture_run(tmp_path)
    save("reviews.json", reviews)
    with pytest.raises(ValueError, match="Not all 24"):
        audit.build(tmp_path, strict=True)


def test_unreviewed_answers_are_not_counted_as_correct(tmp_path):
    fixture_run(tmp_path)
    result = audit.build(tmp_path)
    assert all(s["correct"] == 0 and s["needs_review"] == 1 for s in result["summaries"])


def test_direct_quote_is_distinguished_from_surrounding_context():
    arm = dict(
        response=dict(items=[dict(citations=["m"])]),
        selected=[
            dict(
                id="m",
                record_no=0,
                spans=[dict(record=0, start=0, end=20)],
                evidence=[dict(start=10, end=20)],
            )
        ],
    )
    gold = [[dict(record=0, start=0, end=5)]]
    assert audit.context_only_support(arm, gold)
    arm["selected"][0]["evidence"].append(dict(start=0, end=5))
    assert not audit.context_only_support(arm, gold)
