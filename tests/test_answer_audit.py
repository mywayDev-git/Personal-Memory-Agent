from copy import deepcopy
from types import SimpleNamespace

import pytest

import pma.chat.engine as module
from pma.search_explain import failed_condition


@pytest.mark.parametrize("mode", ["unused", "removed", "repaired", "rejected", "invalid"])
def test_generation_records_actual_citation_history(monkeypatch, mode):
    text = "민수와 점심을 먹었다."
    sources = [{"id": str(i), "record_id": "r" + str(i), "revision_id": "v1",
                "source_text": text} for i in range(3)]
    calls = []

    def answer(*args, **kwargs):
        calls.append(kwargs)
        citations = ["0", "1"] if mode == "removed" else ["1"] if mode == "repaired" and len(calls) == 1 else ["0"]
        return {"status": "answered", "items": [{"text": text, "citations": citations}]}

    def review(question, evidence, response):
        if mode == "invalid":
            return {}
        passed = mode != "rejected" and (mode != "repaired" or len(calls) > 1)
        return {"fulfillment": "direct" if passed else "missing", "abstention": "not_applicable",
                "reason": "PRIVATE REVIEW TEXT", "items": [{"index": 0, "support": "supported",
                "relevant": True, "issue": "none", "answer_quote": text,
                "evidence": [{"id": response["items"][0]["citations"][0], "quote": text}]}]}

    engine = module.ChatEngine.__new__(module.ChatEngine)
    engine.models = SimpleNamespace(answer=answer, review=review)
    engine.service = SimpleNamespace(trace=lambda *a, **kw: None)
    engine.resolve = lambda *a, **kw: ({"needs_clarification": False, "question": "뭐 했어?"}, 0)
    monkeypatch.setattr(module, "direct_statement", lambda *a: None)
    monkeypatch.setattr(module, "claims_supported", lambda *a: True)
    monkeypatch.setattr(module, "causal_claims_supported", lambda *a: True)
    original = deepcopy(sources)
    result = engine.generate("뭐 했어?", {"evidence": sources}, "2026-10-19")
    audit = result["answer_audit"]
    usage = {row["id"]: row["reason"] for row in audit["usage"]}
    assert sources == original
    assert text not in str(audit) and "PRIVATE REVIEW TEXT" not in str(audit)
    assert len(calls) == (2 if mode in {"repaired", "rejected"} else 1)
    assert len(audit["attempts"]) == (2 if mode in {"repaired", "rejected", "invalid"} else 1)
    if mode == "invalid":
        assert [a["generation"] for a in audit["attempts"]] == [1, 1]
    if mode in {"rejected", "invalid"}:
        assert set(usage.values()) == {"answer_rejected"}
        assert audit["status"] == "rejected"
        assert ("invalid_review" if mode == "invalid" else "answer_incomplete") in audit["attempts"][-1]["reasons"]
    else:
        assert usage["0"] == "cited"
        assert usage["1"] == ("citation_removed" if mode == "removed" else "draft_not_cited")
        assert usage["2"] == "draft_not_cited"
    if mode == "repaired":
        assert audit["attempts"][0]["draft_citations"] == ["1"]
        assert audit["attempts"][1]["draft_citations"] == ["0"]


@pytest.mark.parametrize("reason,key,expected", [
    ("explicit_named_person", "person", ["지연"]),
    ("unknown_filtered_date", "time", {"start": "2026-01-01", "end": None}),
    ("date_range", "time", {"start": "2026-01-01", "end": None}),
])
def test_failed_conditions_preserve_requested_constraint(reason, key, expected):
    result = failed_condition(reason, {"relation": "other"}, {"date_from": "2026-01-01"}, {"지연"}, [], set())
    assert result == [{"condition": key, "status": "failed", "expected": expected, "reason": reason}]


def test_answer_metadata_updates_only_observed_candidates():
    from pma.chat.answer_audit import attach_answer_audit

    candidates = [{"id": "used", "stages": {"answer": {"status": "not_run"}}},
                  {"id": "excluded", "stages": {"answer": {"status": "not_run"}}},
                  {"id": "old"}]
    metadata = {"searches": [{"audit": {"candidates": candidates}}]}
    audit = {"usage": [{"id": "used", "status": "used", "reason": "cited"},
                       {"id": "old", "status": "unused", "reason": "draft_not_cited"}]}
    attach_answer_audit(metadata, audit)
    assert metadata["answer_audit"] == audit
    assert candidates[0]["stages"]["answer"] == {"status": "used", "reason": "cited"}
    assert candidates[1]["stages"]["answer"] == {"status": "not_run"}
    assert "stages" not in candidates[2]
