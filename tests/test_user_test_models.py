import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import user_test_models as runtime


def manager(tmp_path):
    files = tuple(tmp_path / name for name in ("server.exe", "generation.gguf", "embedding.gguf"))
    for f in files:
        f.write_bytes(f.name.encode())
    path = tmp_path / ".local/latency-goal/source-completion-gpu-confirmation/gpu"
    path.mkdir(parents=True)
    (path / "results.json").write_text(json.dumps({"hashes": {
        name: hashlib.sha256(f.read_bytes()).hexdigest()
        for name, f in zip(("server", "generation", "embedding"), files, strict=True)}}), encoding="utf-8")
    return runtime.ManualModels(tmp_path, tmp_path / "work", files)


def test_existing_models_are_reused_and_never_stopped(tmp_path, monkeypatch):
    m = manager(tmp_path)
    monkeypatch.setattr(runtime, "ready", lambda port: port in {8081, 8082})
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *a, **kw: pytest.fail("No startup"))
    assert m.ensure() == (8081, 8082)
    assert m.source == "existing"
    m.stop()


@pytest.mark.parametrize("occupied", [8081, 18781])
def test_partial_or_unowned_servers_are_never_terminated_or_overlaid(tmp_path, monkeypatch, occupied):
    m = manager(tmp_path)
    monkeypatch.setattr(runtime, "ready", lambda port: False)
    monkeypatch.setattr(runtime, "listening", lambda port: port == occupied)
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *a, **kw: pytest.fail("No startup"))
    with pytest.raises(ValueError):
        m.ensure()
    assert not m.processes


def test_changed_model_does_not_launch_or_download(tmp_path, monkeypatch):
    m = manager(tmp_path)
    m.files[1].write_bytes(b"different weights")
    monkeypatch.setattr(runtime, "ready", lambda port: False)
    monkeypatch.setattr(runtime, "listening", lambda port: False)
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *a, **kw: pytest.fail("No startup"))
    with pytest.raises(ValueError, match="검증 당시"):
        m.ensure()


def test_gpu_start_failure_cleans_owned_processes_before_one_cpu_retry(tmp_path, monkeypatch):
    m = manager(tmp_path)
    processes = []
    monkeypatch.setattr(runtime, "listening", lambda port: False)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout="CUDA0: test", stderr=""))
    class Process:
        def __init__(self, command, **kwargs):
            self.command, self.env = command, kwargs["env"]
            self.port = int(command[command.index("--port") + 1])
            self.gpu = command[command.index("-ngl") + 1] == "99"
            self.dead = self.gpu
            self.waited = False
            if not self.gpu:
                assert all(p.dead and p.waited for p in processes if p.gpu)
            processes.append(self)
        def poll(self): return 1 if self.dead else None
        def terminate(self): self.dead = True
        def wait(self, **kwargs): self.waited = True; return 0
    monkeypatch.setattr(runtime.subprocess, "Popen", Process)
    monkeypatch.setattr(runtime, "ready", lambda port: any(p.port == port and not p.dead for p in processes))
    assert m.ensure() == (18781, 18782)
    assert m.source == "owned_cpu"
    assert len(processes) == 3
    for p in processes[1:]:
        assert p.command[p.command.index("--device") + 1] == "none"
        assert "--no-op-offload" in p.command and "--no-kv-offload" in p.command
        assert p.env["LLAMA_ARG_REPACK"] == "0"
    m.stop()
    assert all(p.dead and p.waited for p in processes)


def test_both_gpu_models_are_cleaned_after_second_start_fails(tmp_path, monkeypatch):
    m = manager(tmp_path)
    processes = []
    monkeypatch.setattr(runtime, "listening", lambda port: False)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout="CUDA0: test", stderr=""))
    class Process:
        def __init__(self, command, **kwargs):
            self.port = int(command[command.index("--port") + 1])
            self.gpu = command[command.index("-ngl") + 1] == "99"
            self.dead = self.port == 18782
            processes.append(self)
        def poll(self): return 1 if self.dead else None
        def terminate(self): self.dead = True
        def wait(self, **kwargs): return 0
    monkeypatch.setattr(runtime.subprocess, "Popen", Process)
    monkeypatch.setattr(runtime, "ready", lambda port: any(p.port == port and not p.dead for p in processes))
    with pytest.raises(ValueError):
        m.ensure()
    assert not m.processes
    assert all(p.dead for p in processes)
