from evaluation.latency_bottlenecks import analyze


def test_failures_and_warmups_are_not_ten_second_successes():
    rows = [dict(variant="current", case="search", warmup=True, seconds=1, quality={"passed": True}),
            dict(variant="current", case="search", seconds=2, error_code="TIMEOUT"),
            dict(variant="current", case="search", seconds=9, quality={"passed": True}),
            dict(variant="current", case="search", seconds=11, quality={"passed": False})]
    result = analyze({"runs": rows})["cases"]["current/search"]
    assert result["requested"] == 3
    assert result["completed"] == 2
    assert result["latency_seconds"]["median"] == 10
    assert result["latency_seconds"]["maximum"] == 11
    assert result["target_successes"] == 1


def test_stages_are_exclusive_and_calls_sum_within_each_request():
    call = {"phase": "review", "operation": "/chat", "seconds": 3,
            "timings": {"prompt_ms": 1000, "predicted_ms": 2000, "predicted_n": 8}}
    result = analyze({"runs": [{"variant": "candidate", "case": "answer", "seconds": 7,
        "performance": {"profile": {"stages": {"review": {"exclusive_seconds": 6, "inclusive_seconds": 7}}},
                        "model_http_calls": [call, call]}}]})["cases"]["candidate/answer"]
    assert result["exclusive_stages_seconds"]["review"]["median"] == 6
    phase = result["http_phases"]["review:/chat"]
    assert phase["calls"]["median"] == 2
    assert phase["decode_seconds"]["median"] == 4
    assert phase["output_tokens"]["median"] == 16
    assert "PENDING_REVIEW" in str(analyze({"runs": []}))
