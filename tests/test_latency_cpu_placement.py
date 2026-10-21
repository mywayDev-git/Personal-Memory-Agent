from types import SimpleNamespace

import pytest

from evaluation import response_latency


@pytest.mark.parametrize("placement,expected_cpu", [("cpu", [True, True]), ("gpu", [False, False]),
                                                   ("hybrid", [False, True])])
def test_owned_cpu_servers_disable_device_operations_and_kv(tmp_path, monkeypatch, placement, expected_cpu):
    calls, processes = [], []
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def bind(self, address): pass
    class Process:
        stopped = False
        def poll(self): return None if not self.stopped else 0
        def terminate(self): self.stopped = True
        def wait(self, **kwargs): return 0
    def spawn(command, **kwargs):
        calls.append(command)
        process = Process()
        processes.append(process)
        return process
    monkeypatch.setattr(response_latency.socket, "socket", Socket)
    monkeypatch.setattr(response_latency.subprocess, "Popen", spawn)
    monkeypatch.setattr(response_latency, "wait_ready", lambda *a: None)
    args = SimpleNamespace(output=tmp_path, port=18581, placement=placement, server=tmp_path / "fake.exe",
                           flash="auto", embedding="bge", embedding_batch=4096, threads=8, reset_prompt_cache=True)
    with response_latency.servers(args, tmp_path / "gen.gguf", tmp_path / "emb.gguf"):
        for command, cpu in zip(calls, expected_cpu):
            assert ("--no-op-offload" in command) == cpu
            assert ("--no-kv-offload" in command) == cpu
            assert ("--device" in command) == cpu
            if cpu:
                assert command[command.index("--device") + 1] == "none"
                assert command[command.index("-ngl") + 1] == "0"
    assert all(process.stopped for process in processes)
