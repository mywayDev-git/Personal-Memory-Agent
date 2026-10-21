import json
import subprocess
import sys
import pytest

from evaluation.first_response_cases import DEVELOPMENT, HOLDOUT, BASE_DOCUMENTS, EXTRA_DOCUMENTS, HOLDOUT_DOCUMENTS, manifest
from evaluation.review_bank import PAIRS


def test_plan_does_not_start_models_or_import_real_runner():
    result = subprocess.run([sys.executable, "-m", "evaluation.first_response"],
                            capture_output=True, text=True, encoding="utf-8", timeout=10, check=True)
    plan = json.loads(result.stdout)
    assert plan["status"] == "PLAN_ONLY" and plan["models_started"] is False
    assert len(DEVELOPMENT) == len(HOLDOUT) == 16
    assert not set(DEVELOPMENT) & set(HOLDOUT)
    assert len(manifest()["sha256"]) == 64
    assert len({case["question"] for case in [*DEVELOPMENT.values(), *HOLDOUT.values()]}) == 32
    assert not {d[1] for d in [*BASE_DOCUMENTS, *EXTRA_DOCUMENTS]} & {d[1] for d in HOLDOUT_DOCUMENTS}


def test_review_gold_is_independent_and_contains_required_corruptions():
    assert len(PAIRS) == 8
    assert all(source and question and valid != altered for source, question, valid, altered in PAIRS)


def test_changed_fixtures_cannot_execute_under_the_old_manifest(monkeypatch):
    from evaluation import first_response
    monkeypatch.setattr(first_response, "manifest", lambda: {"sha256": "changed"})
    monkeypatch.setattr(sys, "argv", ["first_response", "--execute"])
    with pytest.raises(SystemExit) as exc:
        first_response.main()
    assert exc.value.code == 2
