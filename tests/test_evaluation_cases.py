"""Offline checks for compact list projection and selected case details."""

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from evaluation.repository import Repository
from evaluation.schema import Case, Dataset, Result
from pma.evaluation_api import EvaluationDisplay, install
from pma.settings import AppSettings


def fixture(tmp_path, details):
    settings = replace(AppSettings(), data_dir=tmp_path, evaluation_enabled=True, evaluation_details=details)
    repo = Repository(tmp_path / "evaluation/evaluation.db")
    question = "질문 원문\n" + "긴 질문 🙂 " * 60
    expected = "정답 " * 100
    answer = "실제 답변\n" + "처리 결과 " * 100
    repo.create_dataset(Dataset(id="case-view", name="case-view", version="1", cases=[
        Case(id="one", question=question, expected_answer=json.dumps([expected], ensure_ascii=False),
             expected_behavior="answer", metadata={"scenario":{"steps":[{"action":"chat","question":question}]}})]))
    rid = repo.create_run("case-view")
    repo.save_case_result(rid, Result(case_id="one", verdict="fail", actual_answer=answer,
        response_behavior="abstain", latency_ms=12, error_type="F-CITATION",
        evaluation={"suite_verdict":"FAIL", "observation":{"sources":{"private":{"text":"원문-private-source"}}}}))
    app = FastAPI()
    install(app, settings, Path("pma/static"))
    installed = []
    for route in app.routes:
        installed.extend(route.original_router.routes if hasattr(route, "original_router") else [route])
    routes = {r.path:r for r in installed if hasattr(r, "path")}
    for route in installed:
        if hasattr(route, "path"):
            for method in getattr(route, "methods", None) or []:
                routes[route.path, method] = route
    return routes, rid, question, expected, answer


def test_compact_list_contains_previews_without_heavy_detail_payload(tmp_path):
    routes, rid, question, expected, answer = fixture(tmp_path, True)
    request = Request({"type":"http", "query_string":b"view=compact&limit=20", "headers":[]})
    value = routes["/api/eval/runs/{run_id}/cases"].endpoint(rid, request)
    row = value["items"][0]
    assert row["expected_behavior"] == "answer" and row["response_behavior"] == "abstain"
    assert row["suite_verdict"] == "FAIL"
    assert all(len(row[key]) <= 89 for key in ("question_preview", "expected_preview", "actual_preview"))
    assert "\n" not in row["question_preview"] and row["question_preview"].endswith("…")
    assert not {"question", "expected_answer", "actual_answer", "evaluation", "metadata"} & row.keys()
    full = routes["/api/eval/runs/{run_id}/cases/{case_id}"].endpoint(rid, "one")
    assert full["question"] == question
    assert full["actual_answer"] == answer
    assert full["metadata"]["scenario"]["steps"][0]["question"] == question


def test_compact_list_cannot_bypass_detail_masking(tmp_path):
    routes, rid, question, expected, answer = fixture(tmp_path, False)
    request = Request({"type":"http", "query_string":b"view=compact", "headers":[]})
    row = routes["/api/eval/runs/{run_id}/cases"].endpoint(rid, request)["items"][0]
    assert row["text_masked"] is True
    assert all(row[key] is None for key in ("question_preview", "expected_preview", "actual_preview"))
    full = routes["/api/eval/runs/{run_id}/cases/{case_id}"].endpoint(rid, "one")
    assert full["question"] is None and full["actual_answer"] is None
    assert "evaluation" not in full and "metadata" not in full
    assert question not in json.dumps(row, ensure_ascii=False)


def test_original_list_contract_is_unchanged_without_compact_option(tmp_path):
    routes, rid, question, expected, answer = fixture(tmp_path, True)
    request = Request({"type":"http", "query_string":b"", "headers":[]})
    row = routes["/api/eval/runs/{run_id}/cases"].endpoint(rid, request)["items"][0]
    assert row["question"] == question and row["actual_answer"] == answer
    assert "observation" in row["evaluation"]


def test_user_can_choose_originals_for_this_app_session_then_hide_them(tmp_path):
    from fastapi import HTTPException

    routes, rid, question, expected, answer = fixture(tmp_path, False)
    assert routes["/api/eval/display", "GET"].endpoint()["show_originals"] is False
    setter = routes["/api/eval/display", "PUT"].endpoint
    assert setter(EvaluationDisplay(show_originals=True))["show_originals"] is True
    full = routes["/api/eval/runs/{run_id}/cases/{case_id}"].endpoint(rid, "one")
    assert full["question"] == question and full["actual_answer"] == answer
    assert routes["/api/eval/runs/{run_id}/cases/{case_id}/trace"].endpoint(rid, "one")["case_id"] == "one"
    setter(EvaluationDisplay(show_originals=False))
    assert routes["/api/eval/runs/{run_id}/cases/{case_id}"].endpoint(rid, "one")["question"] is None
    with pytest.raises(HTTPException) as error:
        routes["/api/eval/runs/{run_id}/cases/{case_id}/trace"].endpoint(rid, "one")
    assert error.value.status_code == 403
    # A fresh app returns to the configured default, without changing environment/files.
    fresh, *_ = fixture(tmp_path / "fresh", False)
    assert fresh["/api/eval/display", "GET"].endpoint()["show_originals"] is False


def test_display_preference_requires_an_explicit_boolean():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EvaluationDisplay(show_originals="true")


def test_case_selection_and_tabs_offline_dom():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable")
    result = subprocess.run([node, str(Path(__file__).with_name("evaluation_cases_ui.mjs"))],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_planned_synthetic_questions_are_readable_without_starting_a_test(tmp_path):
    routes, *_ = fixture(tmp_path, False)
    result = routes["/api/eval/plan/cases/{variable_id}"].endpoint("EX-03")
    assert result["synthetic_only"] and result["executed"] is False
    assert result["items"] and all(c["question"] and c["expected_answer"] for c in result["items"])
    # Plan previews contain no private observations, regardless of detail preference.
    assert not {"actual_answer", "observation", "evaluation"} & result["items"][0].keys()
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        routes["/api/eval/plan/cases/{variable_id}"].endpoint("unknown")
    assert error.value.status_code == 404
