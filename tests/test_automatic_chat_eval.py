import copy

from evaluation.automatic_chat_eval import valid_citations


def test_citation_evaluation_rejects_missing_span_and_wrong_revision():
    sources = [{"id": "m", "record_id": "r", "revision_id": "v", "source_text": "😊 서울숲"}]
    response = {"items": [{"text": "서울숲", "citations": ["m"]}]}
    assert not valid_citations(response, sources)
    response["citation_details"] = [
        {
            "item_index": 0,
            "memory_id": "m",
            "record_id": "r",
            "revision_id": "v",
            "start": 2,
            "end": 5,
            "quote": "서울숲",
        }
    ]
    assert valid_citations(response, sources)
    forged = copy.deepcopy(response)
    forged["citation_details"][0]["revision_id"] = "another-version"
    assert not valid_citations(forged, sources)
