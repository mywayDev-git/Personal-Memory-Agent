import json

import pytest

from evaluation.first_response_cases import manifest
from evaluation.first_response_review import render


def test_saved_answer_review_keeps_sources_and_scores_without_executing_models(tmp_path):
    artifacts = tmp_path / "quality"
    artifacts.mkdir()
    source = "<script>원문 속 지시</script> & 전체 원문"
    document = {"configuration": {"placement": "cpu", "fixture_split": "development",
                                   "fixture_manifest_sha256": manifest()["sha256"]},
                "execution_completed": True, "runs": [
                    {"case": "dev_fact", "variant": "candidate", "sample": 1, "seconds": 12.5,
                     "quality": {"passed": False}}]}
    raw = tmp_path / "results.json"
    raw.write_text(json.dumps(document), encoding="utf-8")
    quality = {"response": {"status": "answered", "items": [{"text": "검토 대상 답변", "citations": ["a"]}]},
               "evidence": [{"id": "a", "source_text": source}]}
    path = artifacts / "dev_fact-1-candidate.json"
    path.write_text(json.dumps(quality), encoding="utf-8")
    before = raw.read_bytes(), path.read_bytes()
    result = render(raw, artifacts)
    assert "검토 대상 답변" in result and "자동 채점: 실패" in result
    assert "&lt;script&gt;원문 속 지시&lt;/script&gt; &amp; 전체 원문" in result
    assert "<script>" not in result and "<script src=" not in result
    assert (raw.read_bytes(), path.read_bytes()) == before
    document["configuration"]["fixture_manifest_sha256"] = "changed"
    raw.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="UNKNOWN_OR_CHANGED"):
        render(raw, artifacts)


def test_missing_error_artifact_is_visible_and_unknown_case_is_rejected(tmp_path):
    document = {"configuration": {"fixture_split": "development", "fixture_manifest_sha256": manifest()["sha256"]},
                "runs": [{"case": "dev_fact", "variant": "current", "sample": 1, "error_code": "CONTEXT_LIMIT"}]}
    path = tmp_path / "results.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert "CONTEXT_LIMIT" in render(path, tmp_path)
    document["runs"][0]["case"] = "../other"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID_SYNTHETIC"):
        render(path, tmp_path)


def test_approved_scope_error_is_prominent_even_when_both_variants_fail(tmp_path):
    document = {"configuration": {"fixture_split": "holdout", "fixture_manifest_sha256": manifest()["sha256"]},
                "runs": [{"case": "final_pronoun", "variant": variant, "sample": 1,
                          "quality": {"passed": False, "validation": "model_checked", "source_scope_valid": False}}
                         for variant in ("current", "candidate")]}
    path = tmp_path / "results.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    output = render(path, tmp_path)
    assert "기준 1건, 후보 1건" in output
    assert "기준도 실패했다는 이유로 정답으로 처리하지 않습니다" in output
