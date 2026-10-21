import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_failed_owned_start_keeps_memory_and_cleans_process_without_raw_exception(tmp_path, monkeypatch):
    from evaluation import response_latency as runner

    class Probe:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): pass

    class Memory:
        ram = [1234]
        private_commit = [2345]
        vram = [0]
        available_ram = [55]
        def __init__(self, pids): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

    class Process:
        pid = 123
        alive = True
        def poll(self): return None if self.alive else 0
        def terminate(self): self.alive = False
        def wait(self, timeout): return 0

    process = Process()
    started = []
    def popen(command, **kwargs):
        started.append(command)
        return process
    def failed(*args): raise RuntimeError("untrusted exception contents")
    monkeypatch.setattr(runner.socket, "socket", lambda: Probe())
    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    monkeypatch.setattr(runner, "MemorySampler", Memory)
    monkeypatch.setattr(runner, "wait_ready", failed)
    args = SimpleNamespace(output=tmp_path, port=18581, server=Path("test-only-server"),
                           placement="cpu", flash="auto", embedding="bge", embedding_batch=4096,
                           threads=8, reset_prompt_cache=False, startup_memory=True)
    with pytest.raises(RuntimeError):
        with runner.servers(args, tmp_path / "generation.gguf", tmp_path / "embedding.gguf"):
            pytest.fail("Failed startup must not yield a live experiment")
    data = (tmp_path / "server-failure.json").read_text(encoding="utf-8")
    report = json.loads(data)
    assert report["startup_memory"]["ram_peak_mb"] == 1234
    assert report["startup_memory"]["system_available_ram_min_mb"] == 55
    assert report["owned_experiment_server"] is True and report["port"] == 18581
    assert len(started) == 1 and not process.alive
    assert "untrusted exception contents" not in data
