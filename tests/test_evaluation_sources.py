"""Synthetic source browsing must never insert into the personal database."""

import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import HTTPException

from evaluation.main_suite.catalog import read
from evaluation.main_suite.sources import resolve_sources, source_dataset
from evaluation.main_suite.sources import test_sources as synthetic_sources
from tests.test_evaluation_cases import fixture
from tests.test_evaluation_dataset_browser import request


def test_sources_keep_full_original_versions_and_chat_provenance():
    sources = synthetic_sources(read("scenarios.json"))
    assert len({s["id"] for s in sources}) == len(sources)
    assert all(s["text"] and s["cases"] for s in sources)
    assert any("수정 전 원문" in s["kinds"] for s in sources)
    assert any("저장 요청 대화" in s["kinds"] for s in sources)
    assert any("비저장 요청 대화" in s["kinds"] for s in sources)
    record = {"id": "target", "text": "현재 지연", "initial_text": "이전 민수", "owner": "user-a", "version": 2}
    case = {"id": "one", "records": [record], "steps": [], "question": "담당자는?", "variant": "normal", "split": "development", "variables": ["ST-05"]}
    assert {(s["text"], s["version"]) for s in synthetic_sources([case])} == {("현재 지연", 2), ("이전 민수", 1)}


def test_read_only_sources_are_complete_searchable_and_do_not_create_personal_records(tmp_path):
    routes, *_ = fixture(tmp_path, False)
    expected = synthetic_sources(read("scenarios.json"))
    listing = routes["/api/eval/plan/memories"].endpoint
    ids = []
    for offset in range(0, len(expected), 100):
        page = listing(request(limit=100, offset=offset))
        assert page["read_only"] and page["synthetic_only"] and not page["executed"]
        ids.extend(s["id"] for s in page["items"])
    assert ids == [s["id"] for s in expected]
    detail = routes["/api/eval/plan/memories/{source_id}"].endpoint
    assert detail(ids[0])["source"] == expected[0]
    assert listing(request(q="no-such-source-xyz"))["total"] == 0
    assert listing(request(q="SYNTH-DELETE-872"))["total"] > 0
    assert not (tmp_path / "memory.db").exists()
    with pytest.raises(HTTPException) as exc:
        detail("unknown")
    assert exc.value.status_code == 404


def test_source_reader_lazy_loading_raw_text_and_no_mutations():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node unavailable")
    result = subprocess.run([node, str(Path(__file__).with_name("test_memory_view_ui.mjs"))], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_registered_corpus_matches_existing_sentences_and_all_input_links():
    dataset = source_dataset()
    cases = read("scenarios.json")
    assert dataset["records"] == synthetic_sources(cases)
    for case in cases:
        assert all(r.get("source_id") for r in case["records"])
        assert resolve_sources(case, dataset) == case
    case = next(c for c in cases if c["records"])
    corrupt = deepcopy(case)
    corrupt["records"][0]["text"] = "unregistered replacement"
    with pytest.raises(ValueError, match="CASE_SOURCE_MISMATCH"):
        resolve_sources(corrupt, dataset)
    corrupt = deepcopy(case)
    corrupt["records"][0]["source_id"] = "missing-source"
    with pytest.raises(ValueError, match="CASE_SOURCE_MISMATCH"):
        resolve_sources(corrupt, dataset)


def test_corpus_export_is_the_registered_source_dataset(tmp_path):
    routes, *_ = fixture(tmp_path, False)
    exported = routes["/api/eval/plan/memories/export"].endpoint()
    assert json.loads(exported.body) == source_dataset()
    assert "attachment" in exported.headers["content-disposition"]
    assert not (tmp_path / "memory.db").exists()
