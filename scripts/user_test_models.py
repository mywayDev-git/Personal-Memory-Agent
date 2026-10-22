"""Explicit manual-app startup only; never called by viewing or polling."""
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.3):
            return True
    except OSError:
        return False


def ready(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


class ManualModels:
    def __init__(self, root, work, files=None):
        self.root, self.work = root, work
        self.files = files or (Path("C:/llama.cpp/llama-server.exe"),
            Path("C:/models/Qwen3-8B-Q4_K_M.gguf"), Path("C:/models/bge-m3-Q8_0.gguf"))
        self.processes = []
        self.source = "not_started"

    def stop(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()  # Only Popen handles created by this instance.
        for process in self.processes:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        self.processes.clear()
        self.source = "not_started"

    def ensure(self):
        if ready(8081) and ready(8082):
            self.source = "existing"
            return 8081, 8082
        if listening(8081) or listening(8082):
            raise ValueError("일반 모델 서버가 일부만 준비됐습니다. 기존 서버 준비가 끝난 뒤 다시 열어 주세요.")
        if self.processes and all(p.poll() is None for p in self.processes) and ready(18781) and ready(18782):
            return 18781, 18782
        self.stop()
        if listening(18781) or listening(18782):
            raise ValueError("테스트 전용 포트가 사용 중입니다. 다른 프로세스는 종료하지 않았습니다.")
        server, *models = self.files
        reference = json.loads((self.root / ".local/latency-goal/source-completion-gpu-confirmation/gpu/results.json")
                               .read_text(encoding="utf-8"))["hashes"]
        for key, path in zip(("server", "generation", "embedding"), (server, *models), strict=True):
            if not path.is_file():
                raise ValueError("기존 모델 또는 실행 파일이 없습니다. 다운로드는 자동으로 하지 않습니다.")
            with path.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != reference[key]:
                    raise ValueError("검증 당시 모델·실행 파일과 다릅니다. 기존 파일을 확인해 주세요.")
        devices = subprocess.run([str(server), "--list-devices"], capture_output=True, text=True,
            errors="replace", timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        import re
        gpu = devices.returncode == 0 and re.search(r"(?im)^\s*(CUDA|Vulkan|SYCL|Metal|ROCm|HIP)\d*\s*:",
                                                    devices.stdout + devices.stderr)
        modes = ["gpu", "cpu"] if gpu else ["cpu"]
        folder = self.work / ("models-" + secrets.token_hex(5))
        folder.mkdir(parents=True)
        for mode in modes:
            try:
                for index, (port, model, alias) in enumerate(zip((18781, 18782), models, ("qwen3", "bge-m3"), strict=True)):
                    command = [str(server), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                        "-c", "16384" if index == 0 else "8192", "-ngl", "99" if mode == "gpu" else "0",
                        "--alias", alias, "--flash-attn", "auto", "--log-disable", "-t", "8"]
                    if index == 0:
                        command += ["-np", "1", "-tb", "24"]
                    else:
                        command += ["--embedding", "--pooling", "cls", "--embd-normalize", "2", "-b", "4096", "-ub", "4096"]
                    env = dict(os.environ)
                    if mode == "cpu":
                        command += ["--device", "none", "--no-op-offload", "--no-kv-offload"]
                        env["LLAMA_ARG_REPACK"] = "0"
                    with (folder / f"{mode}-{index}.log").open("wb") as log:
                        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                            env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    self.processes.append(process)
                    deadline = time.monotonic() + 120
                    while process.poll() is None and time.monotonic() < deadline:
                        if ready(port):
                            break
                        time.sleep(.25)
                    if process.poll() is not None or not ready(port):
                        raise ValueError("테스트 전용 모델 준비 실패 · 전용 프로세스를 정리했습니다.")
                self.source = "owned_" + mode
                return 18781, 18782
            except Exception:
                self.stop()
                if mode == modes[-1]:
                    raise
        raise ValueError("테스트 모델을 준비하지 못했습니다.")
