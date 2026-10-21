from evaluation.latency_bottlenecks import analyze


def test_cli_uses_the_requested_device_target_and_marks_baseline_only(tmp_path, monkeypatch):
    import json
    import sys
    from evaluation.latency_bottlenecks import main
    for placement, target in (("cpu", 60), ("gpu", 10)):
        path = tmp_path / (placement + ".json")
        path.write_text(json.dumps({"configuration": {"placement": placement, "variants": ["current"]},
                                    "runs": []}), encoding="utf-8")
        output = tmp_path / (placement + "-report.json")
        monkeypatch.setattr(sys, "argv", ["report", str(path), "--output", str(output)])
        main()
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["target_seconds"] == target
        assert report["adoption"] == "BASELINE_REFERENCE_ONLY"
        assert len(report["source_sha256"]) == 64
    output = tmp_path / "both-report.json"
    monkeypatch.setattr(sys, "argv", ["report", str(tmp_path / "cpu.json"), str(tmp_path / "gpu.json"),
                                      "--output", str(output)])
    main()
    reports = json.loads(output.read_text(encoding="utf-8"))
    assert [r["target_seconds"] for r in reports] == [60, 10]
    assert [r["placement"] for r in reports] == ["cpu", "gpu"]


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
