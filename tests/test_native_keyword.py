import sysconfig
from pathlib import Path

import pytest
from test_query_correction import TODAY, configured
from test_search_explain import row

from evaluation.native_keyword_benchmark import native, quality
from pma.search_explain import keyword_query, python_keyword_matches_batch


@pytest.fixture
def cpp_matcher():
    root = Path(__file__).resolve().parents[1]
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    path = root / ".local/native-pre-multilingual" / ("_keyword_native" + suffix)
    if not path.exists():
        pytest.skip("optional C++ matcher has not been built")
    return native(path)


def test_cpp_matches_python_for_unicode_negation_offsets_and_cache_boundary(cpp_matcher):
    assert quality(cpp_matcher)["exact_output_equality"]


def test_cpp_exact_precedes_normalized_per_field(cpp_matcher):
    rows = [row(1, "😀 제주에 제주 제주에 갔다. 취소하지 않았다.")]
    terms, vocabulary = keyword_query("제주 취소하지", rows)
    found = cpp_matcher(rows, terms, vocabulary)
    assert found == python_keyword_matches_batch(rows, terms, vocabulary)
    assert all(match["kind"] == "exact" for match in found[0] if match["term"] == "제주")






def test_cpp_corrected_query_and_date_filters_are_identical(monkeypatch, cpp_matcher):
    import pma.service as module
    records = [row(1, "😀 회의 내용. 취소하지 않았다."), row(2, "회의 내용")]
    records[1]["fact"]["event_time"]["start"] = "2025-01-01"
    svc, _ = configured(records)
    monkeypatch.setattr(module, "keyword_matches_batch", python_keyword_matches_batch)
    expected = svc._search("회의 내욜", {"date_from": "2026-01-01", "date_to": None}, TODAY)
    monkeypatch.setattr(module, "keyword_matches_batch", cpp_matcher)
    assert svc._search("회의 내욜", {"date_from": "2026-01-01", "date_to": None}, TODAY) == expected
    assert expected[1]["query_correction"]["status"] == "applied"


def test_cpp_does_not_retain_rows_across_requests(cpp_matcher):
    import gc
    import sys

    rows = [row(1, "😀 제주에 갔다. 취소하지 않았다.")]
    terms, vocabulary = keyword_query("제주 여행", rows)
    before = sys.getrefcount(rows[0])
    for _ in range(200):
        cpp_matcher(rows, terms, vocabulary)
    gc.collect()
    assert sys.getrefcount(rows[0]) == before


def test_auto_falls_back_and_explicit_cpp_reports_missing_binary(monkeypatch):
    import pma.search_explain as module
    rows = [row(1)]
    terms, vocabulary = keyword_query("제주 여행", rows)
    monkeypatch.setattr(module, "_native_matcher", lambda: None)
    monkeypatch.setenv("PMA_KEYWORD_BACKEND", "auto")
    assert module.keyword_matches_batch(rows, terms, vocabulary) == python_keyword_matches_batch(rows, terms, vocabulary)
    monkeypatch.setenv("PMA_KEYWORD_BACKEND", "cpp")
    with pytest.raises(RuntimeError, match="unavailable"):
        module.keyword_matches_batch(rows, terms, vocabulary)


def test_python_mode_never_loads_native_and_bad_mode_is_rejected(monkeypatch):
    import pma.search_explain as module
    def unexpected():
        raise AssertionError("native must not be loaded")
    monkeypatch.setattr(module, "_native_matcher", unexpected)
    monkeypatch.setenv("PMA_KEYWORD_BACKEND", "python")
    assert module.keyword_matches_batch([], [], set()) == []
    monkeypatch.setenv("PMA_KEYWORD_BACKEND", "bad")
    with pytest.raises(ValueError, match="PMA_KEYWORD_BACKEND"):
        module.keyword_matches_batch([], [], set())


def test_available_native_is_used_without_changing_results(monkeypatch, cpp_matcher):
    import pma.search_explain as module
    calls = []
    def invoke(rows, terms, vocabulary, normalize):
        calls.append(True)
        return cpp_matcher(rows, terms, vocabulary)
    monkeypatch.setenv("PMA_KEYWORD_BACKEND", "auto")
    monkeypatch.setattr(module, "_native_matcher", lambda: invoke)
    rows = [row(1)]
    terms, vocabulary = keyword_query("제주 여행", rows)
    assert module.keyword_matches_batch(rows, terms, vocabulary) == python_keyword_matches_batch(rows, terms, vocabulary)
    assert calls == [True]


def test_loader_handles_a_missing_extension(monkeypatch):
    import sys

    import pma.search_explain as module
    module._native_matcher.cache_clear()
    try:
        monkeypatch.setitem(sys.modules, "pma._keyword_native", None)
        monkeypatch.setitem(sys.modules, "pma._keyword_native_expressions", None)
        import pma
        monkeypatch.delattr(pma, "_keyword_native", raising=False)
        monkeypatch.delattr(pma, "_keyword_native_expressions", raising=False)
        assert module._native_matcher() is None
    finally:
        module._native_matcher.cache_clear()
