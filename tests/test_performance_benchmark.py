import os

import pytest

from evaluation.performance_benchmark import accelerator_available, available_memory_mb, memory_mb, memory_usage
from evaluation.performance_report import summarize


@pytest.mark.parametrize("output,code,expected", [
    ("Available devices:\n  CUDA0: NVIDIA GPU", 0, True),
    ("Available devices:\n  Vulkan0: GPU", 0, True),
    ("CPU: processor", 0, False),
    ("CUDA error: no devices", 0, False),
    ("CUDA0: GPU", 1, False),
])
def test_cpu_only_device_messages_cannot_be_labeled_gpu(output, code, expected):
    assert accelerator_available(output, code) is expected


def test_sampler_reads_64_bit_process_handle():
    if os.name == "nt":
        assert memory_mb([os.getpid()]) > 0
        usage = memory_usage([os.getpid()])
        assert usage["working_mb"] > 0 and usage["private_commit_mb"] > 0
        assert usage["observed_processes"] == 1 and usage["page_faults"] >= 0
        assert available_memory_mb() is not None
        missing = memory_usage([0])
        assert missing["observed_processes"] == 0


def test_summary_excludes_warmup_and_keeps_failures():
    def row(seconds, **extra):
        return dict(scenario="search", warmup=False, seconds=seconds,
                    http_calls=[dict(endpoint="completions", seconds=seconds / 2)],
                    ram_peak_mb=10, gpu_total_peak_mb=None, status="ok", **extra)

    warmup = row(100)
    warmup["warmup"] = True
    failed = row(4)
    failed.update(status="error", error_code="MODEL_BUSY")
    result = summarize({"runs": [warmup, row(2), failed]})["search"]
    assert result["samples"] == 2
    assert result["median_seconds"] == 3
    assert result["errors"] == ["MODEL_BUSY"]
    assert result["max_gpu_total_mb"] is None


def test_warmup_timeout_is_visible_without_inventing_completed_samples():
    result = summarize({"runs": [], "incomplete_scenarios": {
        "multi_chunk_record": {"reason": "repeated_MODEL_TIMEOUT", "measured": 0,
                               "requested": 5, "warmup_failed": True}}})
    assert result["multi_chunk_record"]["samples"] == 0
    assert result["multi_chunk_record"]["incomplete"]["warmup_failed"]
