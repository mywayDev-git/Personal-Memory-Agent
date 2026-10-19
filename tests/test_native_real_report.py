import json

from evaluation.native_real_report import summarize


def test_timeouts_and_warmups_do_not_become_success_medians(tmp_path):
    rows = []
    for sample, seconds, status in ((0, 1000, "ok"), (1, 3, "ok"), (2, 5, "ok"), (3, 300, "error")):
        rows.append(
            dict(
                mode="cpu",
                backend="cpp",
                scenario="search",
                sample=sample,
                seconds=seconds,
                status=status,
                error_code="CHAT_TIMEOUT" if status == "error" else None,
                warmup=sample == 0,
                native_calls=1,
                http_calls=[],
                ram_peak_mib=10,
            )
        )
    (tmp_path / "results.json").write_text(json.dumps(dict(samples=5, runs=rows)), encoding="utf-8")
    report = summarize(tmp_path)
    summary = next(
        r
        for r in report["summary"]
        if r["mode"] == "cpu" and r["scenario"] == "search" and r["backend"] == "cpp"
    )
    assert summary["median_seconds"] == 4
    assert summary["max_seconds"] == 5
    assert summary["measured"] == 3 and summary["succeeded"] == 2
    assert summary["failed_seconds"] == [300]


def test_failed_request_memory_can_be_recovered_without_success(tmp_path):
    row = dict(
        mode="cpu",
        backend="cpp",
        scenario="memory_chat",
        sample=1,
        seconds=300,
        status="error",
        error_code="CHAT_TIMEOUT",
        warmup=False,
    )
    (tmp_path / "results.json").write_text(
        json.dumps(dict(samples=5, runs=[row])), encoding="utf-8"
    )
    entry = {**row, "ram_peak_mib": 123, "gpu_total_peak_mib": 12}
    (tmp_path / "memory-journal.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    report = summarize(tmp_path)
    summary = next(
        r
        for r in report["summary"]
        if r["mode"] == "cpu" and r["scenario"] == "memory_chat" and r["backend"] == "cpp"
    )
    assert summary["succeeded"] == 0 and "median_seconds" not in summary
    assert summary["ram_peak_mib"] == 123
