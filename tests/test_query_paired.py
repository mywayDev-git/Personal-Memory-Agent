import copy

import numpy as np

from evaluation.query_paired import ARMS, PairedIndex


def memory(key, actor, recipient, obj, text):
    return dict(
        id=key,
        record_no=int(key),
        content=text,
        source_text=text,
        subject={"value": actor},
        predicate="줬다",
        object={"value": obj},
        target={"value": recipient},
        evidence=[dict(quote=text, start=0, end=len(text))],
        fact=dict(actor=actor, recipient=recipient, object=obj, relation="give", state="completed"),
    )


def rows():
    return [
        memory("0", "민수", "지연", "책", "민수가 지연에게 책을 줬다."),
        memory("1", "지연", "민수", "책", "지연이 민수에게 책을 줬다."),
        memory("2", "수진", "진우", "우산", "수진이 진우에게 우산을 줬다."),
    ]


def analysis():
    return dict(
        status="ok",
        units=[
            dict(field="actor", text="지연", value="지연"),
            dict(field="action", text="준", value="주다"),
        ],
        relations=[],
    )


def test_graph_only_never_embeds_and_decomposition_preserves_roles():
    def forbidden(texts):
        raise AssertionError("Graph-only search must never embed")

    index = PairedIndex(None, None, rows(), [], forbidden)
    found, trace = index.search("지연이 준 것은?", analysis(), "G1")
    assert found[0]["id"] == "1"
    assert trace["decomposition_applied"]
    assert not index.vectors


def test_graph_missing_information_does_not_invent_an_edge():
    index = PairedIndex(None, None, rows(), [], None)
    found, trace = index.search("현우의 병원은?", analysis(), "G0")
    assert found == []
    assert trace["routes"]["graph"][0]["paths"] == []


def test_fallback_reproduces_whole_question_for_every_method():
    index = PairedIndex(None, None, rows(), [], lambda texts: np.array([[1.0, 0.0] for _ in texts]))
    for method in "VMGH":
        off, _ = index.search("민수가 준 책", analysis(), method + "0")
        on, trace = index.search("민수가 준 책", dict(status="fallback"), method + "1")
        assert [n["id"] for n in off] == [n["id"] for n in on]
        assert trace["fallback"] and trace["queries"] == ["민수가 준 책"]


def test_all_eight_arms_keep_source_and_original_query():
    source = rows()
    before = copy.deepcopy(source)
    index = PairedIndex(None, None, source, [], lambda texts: np.array([[1.0, 0.0] for _ in texts]))
    for arm in ARMS:
        result, trace = index.search("지연이 준 것은?", analysis(), arm)
        assert trace["queries"][0] == "지연이 준 것은?"
        assert len(result) <= 8
        assert all(
            n["source_text"][e["start"] : e["end"]] == e["quote"]
            for n in result
            for e in n["evidence"]
        )
    assert source == before


def test_graph_expansion_is_a_hint_and_keeps_provenance():
    source = rows()
    source[1]["fact"]["object"] = "색연필"
    index = PairedIndex(None, None, source, [], None)
    result, trace = index.search("책", {}, "G0")
    assert {n["id"] for n in result} == {"0", "1"}
    paths = trace["routes"]["graph"][0]["paths"]
    assert paths and all(p["identity_verified"] is False for p in paths)
