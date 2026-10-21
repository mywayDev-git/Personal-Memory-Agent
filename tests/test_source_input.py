from copy import deepcopy

from pma.chat.source_input import deduplicate_sources


def test_lossless_whole_source_references_preserve_original_storage_and_warnings():
    text = "민수에게 책을 주지 않았다. " * 300
    refs = [{"quote": text, "start": 0, "end": len(text)}]
    row = {"id": "a", "source_text": text, "content": text, "evidence": refs,
           "fact": {"evidence": deepcopy(refs), "review_reasons": ["command_scope"], "state": "review_required"}}
    original = deepcopy(row)
    result = deduplicate_sources([row])[0]
    assert row == original
    assert result["source_text"] == text
    assert result["evidence"] == [{"start": 0, "end": len(text), "quote_from": "source_text"}]
    assert result["fact"]["review_reasons"] == ["command_scope"]
    assert deduplicate_sources([result]) == [result]


def test_partial_quotes_and_distinct_paraphrases_remain_verbatim():
    row = {"source_context": "주지 않았다. 예정만 있다.", "content": "계획은 있으나 전달하지 않음",
           "evidence": [{"quote": "주지 않았다.", "start": 0, "end": 7}]}
    assert deduplicate_sources([row]) == [row]
