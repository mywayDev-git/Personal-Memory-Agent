import copy
import json

import numpy as np
import pytest

from evaluation.query_tree import (
    Index,
    analyze,
    coverage,
    expand,
    instrumented_service,
    merge_spans,
    pack,
    query_texts,
)
from evaluation.query_tree_data import build
from evaluation.query_tree_run import populate
from pma.models import LocalModels
from pma.store import Store


class Models:
    compact_evidence = staticmethod(LocalModels.compact_evidence)

    def count_tokens(self, text):
        return len(text)

    def structured(self, *args, **kwargs):
        return copy.deepcopy(self.analysis)


def node(text="민수는 먹지 않았다.", start=0, end=None):
    end = len(text) if end is None else end
    return dict(
        id="one",
        record_no=0,
        source_text=text,
        evidence=[dict(quote=text[start:end], start=start, end=end)],
        spans=[dict(record=0, start=start, end=end)],
        content=text[start:end],
        fact={},
        time={},
    )


def test_question_expansion_preserves_original_and_negation():
    question = "민수가 먹지 않았어?"
    model = Models()
    model.analysis = dict(
        units=[
            dict(text="민수", field="actor", value="민수"),
            dict(text="먹지 않았어", field="action", value="먹었다"),
        ],
        relations=[],
        unknown=[],
    )
    result = analyze(model, question)
    assert query_texts(question, result) == [question, "먹지 않았어"]
    assert result["provenance_only"] is True


@pytest.mark.parametrize("malformed", ["span", "reference", "schema"])
def test_bad_analysis_falls_back_without_invented_roles(malformed):
    model = Models()
    model.analysis = dict(
        units=[dict(text="민수", field="actor", value="민수")], relations=[], unknown=[]
    )
    if malformed == "span":
        model.analysis["units"][0]["text"] = "영희"
    if malformed == "reference":
        model.analysis["relations"] = [dict(left=0, right=3, kind="and", text="민수")]
    if malformed == "schema":
        model.analysis = {}
    result = analyze(model, "민수는?")
    assert result["status"] == "fallback"
    assert query_texts("민수는?", result) == ["민수는?"]


def test_span_scoring_cannot_pass_on_record_id_only():
    n = node("민수는 먹었다. 영희는 달렸다.", 0, 8)
    gold = [[dict(record=0, start=9, end=18)]]
    assert coverage([n], gold)["recall"] == 0


def test_all_required_needs_both_independent_events():
    n = node("가나다라마바사", 0, 3)
    groups = [[dict(record=0, start=0, end=3)], [dict(record=0, start=3, end=7)]]
    assert coverage([n], groups)["recall"] == 0.5
    assert not coverage([n], groups)["all_required"]


def test_span_union_keeps_records_separate():
    assert merge_spans(
        [
            dict(record=0, start=0, end=4),
            dict(record=0, start=3, end=6),
            dict(record=1, start=0, end=4),
        ]
    ) == [dict(record=0, start=0, end=6), dict(record=1, start=0, end=4)]


def test_expansion_retains_far_heading_without_inventing_date():
    text = "2026-10-10\n" + "설명 " * 250 + '\n민수가 "어제 만났다"고 말했다.'
    n = node(text, text.index("민수가"))
    before = copy.deepcopy(n)
    expanded = expand(n)
    assert any(s["start"] == 0 for s in expanded)
    assert n == before


def test_context_budget_drops_whole_group():
    n = node()
    kept, dropped = pack([n], Models(), budget=1)
    assert kept == [] and dropped == [dict(id="one", reason="context_budget")]


@pytest.mark.parametrize("expanded", [False, True])
def test_scored_spans_equal_actual_transmitted_context(expanded):
    text = "2026-10-10\n\n" + "앞부분 " * 180 + "\n\n민수는 먹었다.\n\n뒷부분 " + "설명 " * 300
    original = node(text, text.index("민수"), text.index("민수") + 9)
    packed, _ = pack([original], Models(), expanded=expanded, budget=20000)
    payload = LocalModels.compact_evidence(packed)[0]
    position = packed[0]["evidence"][0]["start"]
    expected = [dict(record=0, start=e["start"], end=e["end"]) for e in payload["evidence"]]
    expected.append(
        dict(record=0, start=max(0, position - 200), end=min(len(text), position + 600))
    )
    assert packed[0]["spans"] == merge_spans(expected)
    assert original["evidence"][0]["start"] == text.index("민수")


def test_tree_keeps_global_route_even_when_actor_wrong(tmp_path):
    row = node()
    row.update(content=row["source_text"], fact=dict(actor="민수"))

    def embed(texts):
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)

    idx = Index(
        tmp_path / "index.db",
        Models(),
        [row],
        [dict(text=row["source_text"], reference_time=None)],
        embed,
    )
    analysis = dict(units=[dict(field="actor", value="영희", text="영희")], relations=[])
    result, trace = idx.search("영희는?", analysis, "D")
    assert "one" in [r["id"] for r in result]
    assert len(idx.membership["one"]) == 2
    expanded_analysis = dict(
        units=[
            dict(field="action", value="먹다", text="먹다"),
            dict(field="target", value="음식", text="음식"),
        ],
        relations=[],
    )
    _, expanded_trace = idx.search("음식을 먹다", expanded_analysis, "D")
    topics = [r["topic"] for r in expanded_trace["routes"] if "topic" in r]
    assert len(topics) == len(set(topics))
    idx.close()


def test_frozen_repeated_evidence_positions_survive_publish(tmp_path, settings):
    text = "나는 달렸다. 나는 달렸다."
    m = dict(
        local_id="m1",
        content="달렸다",
        memory_type="event",
        subject=dict(kind="self", value="사용자", value_type="string"),
        predicate="달렸다",
        object=None,
        target=None,
        time=dict(raw=None, start=None, end=None, precision="unknown", certainty="uncertain"),
        assertion_polarity="affirmed",
        polarity="neutral",
        content_certainty="explicit",
        evidence=[dict(quote="나는 달렸다.")],
        _evidence_spans=[dict(quote="나는 달렸다.", start=8, end=15)],
    )
    store = Store(tmp_path / "test.db")
    raw = copy.deepcopy(m)
    rows = populate(
        store,
        [dict(text=text, reference_time=None)],
        [[m]],
        lambda ts: np.array([[1.0, 0.0] for _ in ts]),
        settings,
    )
    assert rows[0]["evidence"][0]["start"] == 8
    assert m == raw


def test_trace_instrumentation_leaves_algorithm_executable():
    cls = instrumented_service()
    assert cls._search.__name__ == "_search"


def test_fixed_dataset_gold_spans_and_splits():
    cases = build()
    assert len(cases) == 118
    assert sum(c["split"] == "development" for c in cases) == 24
    assert sum(c["split"] == "holdout" for c in cases) == 24
    for c in cases:
        for alternatives in c["gold"]:
            for g in alternatives:
                assert c["records"][g["record"]]["text"][g["start"] : g["end"]] == g["quote"]
    json.dumps(cases, ensure_ascii=False)
