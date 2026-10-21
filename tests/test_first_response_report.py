from copy import deepcopy

from evaluation.first_response_report import compare


def observation():
    runs = []
    for sample in range(1, 6):
        for variant, seconds in (("current", 16), ("candidate", 9)):
            runs.append({"case": "dev_fact", "sample": sample, "variant": variant, "seconds": seconds,
                         "quality": {"passed": True}, "ram_peak_mb": 100,
                         "private_commit_peak_mb": 110, "gpu_total_peak_mb": 120})
    return {"configuration": {"placement": "gpu", "cases": ["dev_fact"], "cold_interpretations": True,
                               "reset_prompt_cache": True}, "execution_completed": True, "runs": runs}


def test_fast_errors_wrong_answers_or_memory_regression_never_pass():
    source = observation()
    assert compare(source)["cases"]["dev_fact"]["status"] == "SCREEN_PASS"
    for change in ("wrong", "error", "memory", "source_changed", "few_samples"):
        data = deepcopy(source)
        row = data["runs"][1]
        if change == "wrong": row["quality"]["passed"] = False
        if change == "error": row["error_code"] = "TIMEOUT"
        if change == "memory": row["private_commit_peak_mb"] = 116
        if change == "source_changed": data["execution_completed"] = False
        if change == "few_samples": data["runs"] = data["runs"][:-2]
        assert compare(data)["cases"]["dev_fact"]["status"] == "NOT_ADOPTED"


def test_first_request_and_warm_repeat_have_distinct_targets():
    data = observation()
    for row in data["runs"]:
        row["seconds"] = 20 if row["variant"] == "current" else 21
    assert compare(data)["cases"]["dev_fact"]["status"] == "NOT_ADOPTED"
    data["configuration"]["cold_interpretations"] = False
    assert compare(data)["cases"]["dev_fact"]["status"] == "SCREEN_PASS"


def test_unfinished_trials_are_readable_without_timing_values():
    data = observation()
    for row in data["runs"]:
        row["error_code"] = "TIMEOUT"
    result = compare(data)["cases"]["dev_fact"]
    assert result["status"] == "NOT_ADOPTED"
