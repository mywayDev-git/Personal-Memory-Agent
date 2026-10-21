"""Read-only synthetic inventory, no model processes or real evaluations."""

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from evaluation.main_suite.catalog import read, select_cases
from tests.test_evaluation_cases import fixture


def request(**query):
    return Request({"type": "http", "query_string": urlencode(query).encode(), "headers": []})


def test_all_synthetic_cases_are_readable_before_execution(tmp_path):
    routes, *_ = fixture(tmp_path, False)
    endpoint = routes["/api/eval/plan/dataset"].endpoint
    expected = read("scenarios.json")
    ids = []
    for offset in range(0, len(expected), 100):
        data = endpoint(request(limit=100, offset=offset))
        assert data["total"] == len(expected) and data["executed"] is False
        ids.extend(c["id"] for c in data["items"])
    assert ids == [c["id"] for c in expected]
    assert len(set(ids)) == len(ids)
    full = routes["/api/eval/plan/dataset/{case_id}"].endpoint(ids[0])
    assert full["case"] == expected[0]
    exported = routes["/api/eval/plan/dataset/export"].endpoint()
    assert json.loads(exported.body)["cases"] == expected
    assert "attachment" in exported.headers["content-disposition"]
    assert routes["/evaluation/{page:path}"].endpoint("datasets").path.name == "evaluation-datasets.html"


def test_inventory_filters_pagination_and_unknown_cases(tmp_path):
    routes, *_ = fixture(tmp_path, False)
    endpoint = routes["/api/eval/plan/dataset"].endpoint
    data = endpoint(request(category="EX", split="final", limit=100))
    assert all(c["split"] == "final" and any(v.startswith("EX-") for v in c["variables"]) for c in data["items"])
    assert endpoint(request(profile="core", limit=1))["total"] == len(select_cases("core"))
    assert endpoint(request(q="no-such-case-xyz"))["total"] == 0
    for query in ({"profile": "invalid"}, {"limit": 0}, {"offset": -1}):
        with pytest.raises(HTTPException):
            endpoint(request(**query))
    with pytest.raises(HTTPException) as exc:
        routes["/api/eval/plan/dataset/{case_id}"].endpoint("missing")
    assert exc.value.status_code == 404


def test_refresh_does_not_reset_selection_or_open_details():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    result = subprocess.run([node, str(Path(__file__).with_name("evaluation_refresh_ui.mjs"))],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_question_view_groups_before_pagination_without_losing_conditions(tmp_path):
    routes, *_ = fixture(tmp_path, False)
    endpoint = routes["/api/eval/plan/dataset"].endpoint
    questions, ids = [], []
    total = endpoint(request(view="questions", limit=1))["total"]
    for offset in range(0, total, 20):
        page = endpoint(request(view="questions", limit=20, offset=offset))
        for group in page["items"]:
            questions.append(group["question"])
            ids.extend(group["case_ids"])
            assert group["condition_count"] == len(group["case_ids"])
    assert len(questions) == len(set(questions)) == total
    assert set(ids) == {c["id"] for c in read("scenarios.json")}
    first = endpoint(request(view="questions", q="PMA에서 어떤 작업을 했어?"))["items"][0]
    assert "IN-01.normal" in first["case_ids"] and "IN-01.boundary" in first["case_ids"]
    detail = routes["/api/eval/plan/dataset/{case_id}"].endpoint("IN-01.boundary")
    assert detail["case"]["id"] == "IN-01.boundary"
    assert {"IN-01.normal", "IN-01.boundary"} <= {c["id"] for c in detail["conditions"]}
    category = endpoint(request(view="questions", category="EX", limit=100))
    assert all(any(v.startswith("EX-") for v in c["variables"]) for c in category["items"])


def test_grouped_questions_and_condition_selection_in_browser():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    result = subprocess.run([node, str(Path(__file__).with_name("evaluation_dataset_groups_ui.mjs"))],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
