"""Real-model benchmark using only synthetic text and disposable SQLite databases."""

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

import requests

from config.settings import Settings
from pma.diagnostics import start_trace
from pma.models import LocalModels
from pma.settings import AppSettings
from pma.store import Store

SHORT = "2026년 10월 12일 민수에게 파란색 책을 선물했다."
LONG = (
    SHORT + " 민수는 책을 받고 고맙다고 말했다. 2026년 10월 13일에는 지연과 도서관에 갔다."
    " 지연에게는 선물을 주지 않았다. 도서관에서 데이터베이스 책을 빌렸다."
    " 책은 2026년 10월 20일까지 반납할 계획이다."
    " 2026년 10월 14일에는 회사에서 검색 기능 회의를 했다."
    " 회의에서 검색 캐시를 도입하기로 결정했다. 구현 담당자는 나다."
    " 구현은 아직 시작하지 않았다."
)
QUESTION = "2026년 10월 12일 민수에게 무엇을 선물했어?"


def accelerator_available(output, exit_code=0):
    return exit_code == 0 and bool(re.search(
        r"(?im)^\s*(?:CUDA|Vulkan|SYCL|Metal|ROCm|HIP)\d*\s*:", output))


def frozen_implementation(root):
    """Pin scheduling code across modes even if optimization work continues."""
    directory = root / "source-snapshot"
    directory.mkdir(exist_ok=True)
    classes = []
    hashes = {}
    for source, name, symbol in (
        (Path("pma/chat/router.py"), "pma.chat.router", None),
        (Path("pma/chat/automatic.py"), "pma.chat.automatic", None),
        (Path("pma/processing.py"), "pma.processing", None),
        (Path("pma/service.py"), "pma._benchmark_service", "Service"),
        (Path("pma/chat/engine.py"), "pma.chat._benchmark_engine", "ChatEngine"),
    ):
        target = directory / source.name
        if not target.exists():
            shutil.copy2(source, target)
        hashes[source.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
        spec = importlib.util.spec_from_file_location(name, target)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        if symbol:
            classes.append(getattr(module, symbol))
    return (*classes, hashes)


class Counters(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
        (key, ctypes.c_size_t) for key in (
            "peak_working", "working", "peak_paged", "paged", "peak_nonpaged",
            "nonpaged", "pagefile", "peak_pagefile", "private")
    ]


def memory_usage(pids):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    total = private = faults = observed = 0
    for pid in pids:
        handle = kernel.OpenProcess(0x410, False, pid)
        if handle:
            try:
                data = Counters()
                data.cb = ctypes.sizeof(data)
                if psapi.GetProcessMemoryInfo(handle, ctypes.byref(data), data.cb):
                    total += data.working
                    private += data.private
                    faults += data.faults
                    observed += 1
            finally:
                kernel.CloseHandle(handle)
    return {"working_mb": total / 1024**2, "private_commit_mb": private / 1024**2,
            "page_faults": faults, "observed_processes": observed}


def memory_mb(pids):
    return memory_usage(pids)["working_mb"]


def available_memory_mb():
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
            (name, ctypes.c_uint64) for name in ("total", "available", "page_total", "page_available",
                                               "virtual_total", "virtual_available", "extended")]
    status = Status()
    status.length = ctypes.sizeof(status)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return status.available / 1024**2
    return None


class MemorySampler:
    def __init__(self, pids):
        self.pids = pids
        self.stop = threading.Event()
        self.ram = []
        self.vram = []
        self.private_commit = []
        self.available_ram = []
        self.page_faults = []
        self.observed_processes = []

    def sample(self):
        while not self.stop.is_set():
            usage = memory_usage(self.pids)
            self.ram.append(usage["working_mb"])
            self.private_commit.append(usage["private_commit_mb"])
            self.page_faults.append(usage["page_faults"])
            self.observed_processes.append(usage["observed_processes"])
            available = available_memory_mb()
            if available is not None:
                self.available_ram.append(available)
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3, creationflags=0x08000000,
                )
                if result.returncode == 0:
                    self.vram.append(sum(float(v) for v in result.stdout.splitlines()))
            except (OSError, subprocess.TimeoutExpired, ValueError):
                pass
            self.stop.wait(1)

    def __enter__(self):
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(5)


@contextmanager
def instrument_http():
    original = requests.Session.send
    calls = []

    def send(session, request, **kwargs):
        started = time.perf_counter()
        row = {"endpoint": request.url.rsplit("/", 1)[-1]}
        try:
            response = original(session, request, **kwargs)
            row["status"] = response.status_code
            try:
                payload = response.json()
                row["usage"] = payload.get("usage", {})
                row["timings"] = payload.get("timings", {})
            except (ValueError, AttributeError):
                pass
            return response
        finally:
            row["seconds"] = time.perf_counter() - started
            calls.append(row)

    requests.Session.send = send
    try:
        yield calls
    finally:
        requests.Session.send = original


def wait_ready(process, port):
    deadline = time.monotonic() + 300
    with requests.Session() as session:
        session.trust_env = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"server on {port} exited: {process.returncode}")
            try:
                if session.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.5)
    raise TimeoutError(f"server on {port} not ready")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["cpu", "gpu"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--embedding-mode", choices=["cpu", "gpu"],
                        help="Override embedding placement for a mixed CPU/GPU experiment")
    parser.add_argument("--concurrent-short", action="store_true",
                        help="Use one short background record for a focused scheduling check")
    parser.add_argument("--timeout", type=float, default=180,
                        help="Per-model-call timeout; changing it is a separate experiment")
    parser.add_argument("--no-warmup", action="store_true",
                        help="Diagnostic only: seed initialization is the sole warmup")
    parser.add_argument("--scenarios", nargs="+", choices=[
        "short_record", "multi_chunk_record", "search", "memory_chat", "concurrent"],
        default=["short_record", "multi_chunk_record", "search", "memory_chat", "concurrent"])
    args = parser.parse_args()
    if args.mode == "cpu" and args.embedding_mode == "gpu":
        parser.error("CPU-only measurement cannot offload embeddings to GPU")
    if args.output.exists() or args.samples < 1 or args.timeout <= 0:
        parser.error("use a fresh output directory and positive sample count")
    args.output.mkdir(parents=True)
    service_class, engine_class, source_hashes = frozen_implementation(args.output.parent)
    models = [Path("C:/models/Qwen3-8B-Q4_K_M.gguf"), Path("C:/models/bge-m3-Q8_0.gguf")]
    with models[1].open("rb") as model_file:
        revision = hashlib.file_digest(model_file, "sha256").hexdigest()
    settings = AppSettings(
        data_dir=args.output, embedding_revision=revision,
        embedding_endpoint="http://127.0.0.1:18082/v1/embeddings", answer_validation=True,
        llm=Settings(endpoint="http://127.0.0.1:18081/v1/chat/completions", model="qwen3", timeout=args.timeout),
    )
    result = {"mode": args.mode, "samples": args.samples, "threads": args.threads,
              "embedding_mode": args.embedding_mode or args.mode,
              "model_timeout": args.timeout,
              "warmup_policy": "seed_only" if args.no_warmup else "per_scenario",
              "scenarios": args.scenarios,
              "source_hashes": source_hashes,
              "concurrent_fixture": "short" if args.concurrent_short else "multi_chunk",
              "cpu_only_on_gpu_machine": args.mode == "cpu", "runs": [], "summary": {}}
    processes = []
    logs = []
    try:
        if args.mode == "gpu":
            devices = subprocess.run(["C:/llama.cpp/llama-server.exe", "--list-devices"],
                                     capture_output=True, text=True, timeout=30,
                                     creationflags=0x08000000)
            if not accelerator_available(devices.stdout + devices.stderr, devices.returncode):
                raise RuntimeError("GPU measurement requested but no supported GPU device is available")
        for index, model in enumerate(models):
            placement = (args.embedding_mode or args.mode) if index else args.mode
            log = (args.output / f"server-{index}.log").open("w", encoding="utf-8")
            logs.append(log)
            command = ["C:/llama.cpp/llama-server.exe", "-m", str(model), "--host", "127.0.0.1",
                       "--port", str(18081 + index), "-c", "16384" if index == 0 else "8192",
                       "-ngl", "0" if placement == "cpu" else "99", "--alias", "qwen3" if index == 0 else "bge-m3"]
            command += ["-np", "1"] if index == 0 else ["-b", "8192", "-ub", "8192", "--embedding", "--pooling", "cls"]
            if args.threads:
                command += ["-t", str(args.threads)]
            process = subprocess.Popen(command, stdout=log, stderr=log, creationflags=0x08000000)
            processes.append(process)
            wait_ready(process, 18081 + index)
        result["server_pids"] = [p.pid for p in processes]

        def make_service(path):
            service = service_class(Store(path), LocalModels(settings), settings)
            service.metrics = {}
            metric = service.processing_metric

            def capture(stage, seconds=0, **counts):
                metric(stage, seconds, **counts)
                if service.processing_status:
                    service.metrics = dict(service.processing_status.get("performance", {}))

            service.processing_metric = capture
            return service

        seed = make_service(args.output / "seed.db")
        seed_record = seed.store.create(SHORT, "2026-10-19T09:00:00+09:00")
        seed.run_one()
        if seed.store.job(seed_record["job_id"])["status"] != "succeeded":
            raise RuntimeError("synthetic seed extraction failed")
        seed.store.checkpoint()
        for scenario in args.scenarios:
            previous_fatal = None
            for sample in range(1 if args.no_warmup else 0, args.samples + 1):
                db = args.output / f"{scenario}-{sample}.db"
                shutil.copy2(args.output / "seed.db", db)
                service = make_service(db)
                row = {"scenario": scenario, "sample": sample, "warmup": sample == 0}
                started = time.perf_counter()
                with MemorySampler([os.getpid()] + [p.pid for p in processes]) as mem, instrument_http() as calls, start_trace(enabled=True) as trace:
                    try:
                        if scenario.endswith("record"):
                            record = service.store.create(SHORT if scenario == "short_record" else LONG, "2026-10-19T09:00:00+09:00")
                            service.run_one()
                            job = service.store.job(record["job_id"])
                            row["status"] = job["status"]
                            if job["error_code"]:
                                row["error_code"] = job["error_code"]
                        elif scenario == "search":
                            response = service.search(QUESTION, today="2026-10-19")
                            row.update(status=response["status"], results=len(response.get("results", [])))
                        elif scenario == "memory_chat":
                            engine = engine_class(service)
                            sid = engine.store.create_empty()["id"]
                            response = engine.message(sid, "benchmark", QUESTION, today="2026-10-19", mode="memory")
                            row.update(status=response["status"], phases=response.get("phase_timings", {}),
                                       items=len(response.get("items", [])), validation=response.get("validation"))
                        else:
                            engine = engine_class(service)
                            sid = engine.store.create_empty()["id"]
                            record = service.store.create(SHORT if args.concurrent_short else LONG,
                                                          "2026-10-19T09:00:00+09:00")
                            worker = threading.Thread(target=service.run_one)
                            worker.start()
                            # Request after background inference begins, not an arbitrary sleep.
                            deadline = time.monotonic() + 30
                            while not (service.gate.locked() and service.metrics.get("extract_calls", 0)) and worker.is_alive() and time.monotonic() < deadline:
                                time.sleep(0.01)
                            row["arrival_during_extract"] = bool(service.gate.locked() and
                                                                 service.metrics.get("extract_calls", 0))
                            chat_started = time.perf_counter()
                            try:
                                response = engine.message(sid, "benchmark", QUESTION, today="2026-10-19", mode="memory")
                                row.update(status=response["status"], phases=response.get("phase_timings", {}))
                            finally:
                                row["chat_seconds"] = time.perf_counter() - chat_started
                                worker.join()
                                job = service.store.job(record["job_id"])
                                row["record_status"] = job["status"]
                                row["record_error_code"] = job["error_code"]
                    except Exception as exc:
                        row.update(status="error", error_code=getattr(exc, "code", type(exc).__name__))
                    if scenario in {"memory_chat", "concurrent"}:
                        snapshot = engine.store.get(sid)["messages"][-1].get("snapshot") or {}
                        row["lock_wait_seconds"] = snapshot.get("performance", {}).get("lock_wait_seconds")
                    row["seconds"] = time.perf_counter() - started
                    row["processing"] = service.metrics
                    row["http_calls"] = calls
                    row["stages"] = [{k: e[k] for k in ("stage", "duration_ms", "status") if k in e}
                                     for e in trace.events if "duration_ms" in e]
                row["ram_peak_mb"] = max(mem.ram, default=0)
                row["gpu_total_peak_mb"] = max(mem.vram, default=None)
                result["runs"].append(row)
                print(json.dumps({k: row.get(k) for k in ("scenario", "sample", "status", "seconds", "ram_peak_mb", "gpu_total_peak_mb")}), flush=True)
                (args.output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                fatal = row.get("record_error_code") or row.get("error_code")
                if fatal in {"MODEL_TIMEOUT", "CHAT_TIMEOUT", "MODEL_UNAVAILABLE", "MODEL_HTTP_ERROR"}:
                    retried_failure = row.get("processing", {}).get("retries", 0) > 0
                    if retried_failure or (sample > 0 and fatal == previous_fatal):
                        result.setdefault("incomplete_scenarios", {})[scenario] = {
                            "reason": "repeated_" + fatal, "measured": sample,
                            "requested": args.samples, "warmup_failed": sample == 0,
                        }
                        break
                    previous_fatal = fatal
                else:
                    previous_fatal = None
        grouped = defaultdict(list)
        for row in result["runs"]:
            if not row["warmup"]:
                grouped[row["scenario"]].append(row)
        for scenario, rows in grouped.items():
            result["summary"][scenario] = {
                "median_seconds": statistics.median(r["seconds"] for r in rows),
                "max_seconds": max(r["seconds"] for r in rows),
                "peak_ram_mb": max(r["ram_peak_mb"] for r in rows),
                "statuses": [r["status"] for r in rows],
            }
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
        for log in logs:
            log.close()
        (args.output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
