import pytest
from conftest import memory

from evaluation.scenario_contract import load
from evaluation.scenario_runner import execute
from pma.facts import project


@pytest.mark.parametrize("case_id", ["T01", "T02", "T03", "T04", "T05"])
def test_source_constrains_projected_state(store, settings, models, case_id):
    case = next(c for c in load()[1] if c["case_id"] == case_id)
    result = execute(case, store, settings, models)
    assert not result["projection_mismatch"], result


def test_intention_is_not_an_extractive_execution_answer(store, settings, models):
    case = next(c for c in load()[1] if c["case_id"] == "T03")
    result = execute(case, store, settings, models)
    assert result["actual_projection_state"] == "planned"
    assert all(not t.get("structured") for t in result["trace"] if t["stage"] == "answer")


def test_intention_followed_by_explicit_delivery_remains_observed():
    text = "민수는 책을 주려고 했다가 실제로 줬다."
    m = memory(text)
    m.update(
        memory_type="event",
        predicate="줬다",
        subject=dict(kind="entity", value="민수", value_type="string"),
    )
    assert project(m, text, None, None)["state"] == "observed"


def test_broad_quote_does_not_replace_focused_delivery_with_later_intention():
    text = "민수는 책을 줬다. 지호는 책을 주려고 했다."
    m = memory(text)
    m.update(
        content="민수는 책을 줬다.",
        memory_type="event",
        predicate="줬다",
        subject=dict(kind="entity", value="민수", value_type="string"),
    )
    assert project(m, text, None, None)["state"] == "observed"
