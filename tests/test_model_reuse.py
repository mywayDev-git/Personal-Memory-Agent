from copy import deepcopy
from dataclasses import replace

import pytest

from pma.models import LocalModels
from pma.settings import AppSettings
from scripts.memory_agent.llm_client import (
    RequestDeadlineExceeded,
    model_phase,
    observe_phases,
    request_budget,
)


def model():
    gateway = LocalModels.__new__(LocalModels)
    gateway.settings = AppSettings(request_reuse=True)
    calls = []

    def structured(prompt, data, schema, **kw):
        calls.append(deepcopy(data))
        return {"items": [{"id": row["id"], "category": "direct_answer", "quote": "공부를 접었다."}
                          for row in data["evidence"]]}

    gateway.structured = structured
    return gateway, calls


def rows():
    return [{"id": "a", "revision_id": "r1", "version": 1,
             "source_text": "공부를 접었다." + " 긴 원문" * 200,
             "evidence": [{"quote": "공부를 접었다.", "start": 0, "end": 8}]}]


def test_reuses_only_same_request_and_returns_isolated_values():
    gateway, calls = model()
    with request_budget(30):
        result = gateway.select_explained("공부 기록", rows())
        result["a"]["category"] = "irrelevant"
        changed_rank = rows()
        changed_rank[0]["score"] = 999
        assert gateway.select_explained("공부 기록", changed_rank)["a"]["category"] == "direct_answer"
        assert len(calls) == 1
    with request_budget(30):
        gateway.select_explained("공부 기록", rows())
    assert len(calls) == 2


@pytest.mark.parametrize("change", ["question", "revision", "source_tail", "correction", "model", "policy"])
def test_question_full_revision_preprocessing_model_and_policy_invalidate(change, monkeypatch):
    gateway, calls = model()
    with request_budget(30):
        gateway.select_explained("공부 기록", rows())
        evidence = rows()
        question = "공부 기록"
        if change == "question":
            question = "공부 중단 기록"
        elif change == "revision":
            evidence[0]["revision_id"] = "r2"
        elif change == "source_tail":
            evidence[0]["source_text"] += " 수정"
        elif change == "correction":
            evidence[0]["search_explanation"] = {"query_correction": {"status": "applied", "after": "공부"}}
        elif change == "model":
            monkeypatch.setenv("PMA_GENERATION_REVISION", "new-model-revision")
        else:
            gateway.settings = replace(gateway.settings, selection_batch_size=8)
        gateway.select_explained(question, evidence)
    assert len(calls) == 2


def test_cache_never_bypasses_deadline_or_cancellation():
    gateway, calls = model()
    with request_budget(30) as budget:
        gateway.select_explained("공부 기록", rows())
        budget.deadline = 0
        with pytest.raises(RequestDeadlineExceeded):
            gateway.select_explained("공부 기록", rows())
    with request_budget(30):
        gateway.select_explained("공부 기록", rows())
        def cancelled(phase):
            raise RuntimeError("CANCELLED")
        with observe_phases(cancelled), pytest.raises(RuntimeError, match="CANCELLED"):
            gateway.select_explained("공부 기록", rows())
    assert len(calls) == 2


def test_invalid_quotes_and_model_errors_are_not_cached():
    gateway, calls = model()
    with request_budget(30):
        original = gateway.structured
        gateway.structured = lambda *a, **kw: {"items": [
            {"id": "a", "category": "direct_answer", "quote": "없는 원문"}]}
        assert gateway.select_explained("공부 기록", rows())["a"]["category"] == "unverified_selection"
        gateway.structured = original
        assert gateway.select_explained("공부 기록", rows())["a"]["category"] == "direct_answer"
    assert len(calls) == 1


def test_disabled_default_does_not_reuse():
    gateway, calls = model()
    gateway.settings = AppSettings()
    with request_budget(30), model_phase("search"):
        gateway.select_explained("공부 기록", rows())
        gateway.select_explained("공부 기록", rows())
    assert len(calls) == 2
