import json
import subprocess
import sys

from evaluation.first_response_cases import DEVELOPMENT, HOLDOUT, manifest
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


def test_review_gold_is_independent_and_contains_required_corruptions():
    assert len(PAIRS) == 8
    assert all(source and question and valid != altered for source, question, valid, altered in PAIRS)
