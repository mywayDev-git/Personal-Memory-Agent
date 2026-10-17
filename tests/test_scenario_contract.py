from copy import deepcopy

from evaluation.scenario_contract import load, validate


def test_catalog_contract():
    variables, cases = load()
    assert len(variables) == 235 and len(cases) >= 48
    assert validate(variables, cases) == []


def test_bad_span_rejected():
    variables, cases = deepcopy(load())
    cases[0]["gold_evidence_spans"][0]["start"] = 1
    assert any("EVIDENCE_SPAN_INVALID" in e for e in validate(variables, cases))


def test_cross_split_source_leakage_rejected():
    variables, cases = deepcopy(load())
    cases[1]["records"] = deepcopy(cases[0]["records"])
    cases[1]["split"] = "holdout"
    assert any("split leakage" in e for e in validate(variables, cases))


def test_registration_cannot_claim_verified():
    variables, cases = deepcopy(load())
    variables[0]["current_support"] = "verified"
    assert any("execution evidence required" in e for e in validate(variables, cases))
