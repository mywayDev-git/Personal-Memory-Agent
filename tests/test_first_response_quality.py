from copy import deepcopy

from evaluation.first_response_cases import DEVELOPMENT, manifest
from evaluation.first_response_quality import compare


def observation():
    return {"configuration": {"fixture_split": "development", "fixture_manifest_sha256": manifest()["sha256"],
                               "cases": list(DEVELOPMENT)}, "execution_completed": True,
            "runs": [{"case": case, "variant": variant, "quality": {"passed": True}}
                     for case in DEVELOPMENT for variant in ("current", "candidate")]}


def test_missing_or_changed_evidence_cannot_pass_quality_gate():
    original = observation()
    assert compare(original)["automated_nonregression_gate"]
    for change in ("candidate_failure", "missing", "manifest", "source_changed"):
        data = deepcopy(original)
        if change == "candidate_failure": data["runs"][1]["quality"]["passed"] = False
        if change == "missing": data["runs"].pop()
        if change == "manifest": data["configuration"]["fixture_manifest_sha256"] = "wrong"
        if change == "source_changed": data["execution_completed"] = False
        assert not compare(data)["automated_nonregression_gate"]


def test_unchanged_baseline_failures_are_visible_and_never_counted_as_correct():
    data = observation()
    data["runs"][0]["quality"]["passed"] = False
    data["runs"][1]["quality"]["passed"] = False
    result = compare(data)
    assert result["automated_nonregression_gate"]
    assert result["unchanged_failures"] == ["dev_fact"]
    assert result["manual_semantic_review"] == "PENDING"


def test_shared_false_approval_blocks_adoption_even_without_a_relative_regression():
    data = observation()
    for row in data["runs"][:2]:
        row["quality"].update(passed=False, validation="model_checked", source_scope_valid=False)
    result = compare(data)
    assert result["automated_nonregression_gate"] is True
    assert result["candidate_scope_guard_passed"] is False
    assert result["adoption"] == "NOT_ELIGIBLE_SCOPE_FALSE_APPROVAL"
    assert len(result["approved_scope_errors"]) == 2


def test_new_confirmation_requires_absolute_quality_not_only_nonregression():
    from evaluation.identity_followup_cases import CASES, manifest as identity_manifest
    data = {'configuration': {'fixture_split': 'identity_confirmation',
        'fixture_manifest_sha256': identity_manifest()['sha256'], 'cases': list(CASES)},
        'execution_completed': True, 'runs': [{'case': name, 'variant': variant, 'quality': {'passed': True}}
            for name in CASES for variant in ('current', 'candidate')]}
    assert compare(data)['candidate_absolute_quality_passed'] is True
    data['runs'][0]['quality']['passed'] = False
    data['runs'][1]['quality']['passed'] = False
    result = compare(data)
    assert result['automated_nonregression_gate'] is True
    assert result['candidate_absolute_quality_passed'] is False


def test_candidate_only_independent_confirmation_never_claims_paired_nonregression():
    from evaluation.identity_search_cases import CASES, manifest as search_manifest
    data = {'configuration': {'fixture_split': 'identity_search_confirmation',
        'fixture_manifest_sha256': search_manifest()['sha256'], 'cases': list(CASES)},
        'execution_completed': True, 'runs': [{'case': name, 'variant': 'candidate', 'quality': {'passed': True}}
                                             for name in CASES]}
    result = compare(data)
    assert result['candidate_complete_split'] and result['candidate_absolute_quality_passed']
    assert result['candidate_scope_guard_passed']
    assert not result['complete_split'] and not result['automated_nonregression_gate']
    data['runs'].pop()
    assert compare(data)['candidate_absolute_quality_passed'] is False
