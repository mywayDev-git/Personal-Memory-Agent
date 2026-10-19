"""Paired Python/C++ full search/chat benchmark with real CPU/GPU models.

Only synthetic records are opened. Model servers owned by this run are cleaned
up even on errors. Models use the same budgets and validation on both backends.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from config.settings import Settings
from evaluation.database_benchmark import digest
from evaluation.performance_benchmark import (
    QUESTION,
    SHORT,
    MemorySampler,
    instrument_http,
    wait_ready,
)
from pma.chat.engine import ChatEngine
from pma.models import LocalModels
from pma.search_explain import _native_matcher
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store


def expand_seed(path, records):
    """Repeat identical synthetic source+actual embeddings with fresh identities."""
    store = Store(path)
    with store.connect(True) as db:
        record = dict(db.execute("SELECT * FROM records LIMIT 1").fetchone())
        revision = dict(
            db.execute("SELECT * FROM revisions WHERE record_id=?", (record["id"],)).fetchone()
        )
        memories = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM memories WHERE revision_id=? ORDER BY local_id", (revision["id"],)
            )
        ]
        for index in range(1, records):
            rid, vid, jid = (f"synthetic-{prefix}-{index:06d}" for prefix in "rvj")
            db.execute(
                "INSERT INTO records VALUES(?,1,'active','ready',?,?,NULL,NULL)",
                (rid, record["created_at"], record["updated_at"]),
            )
            db.execute(
                "INSERT INTO revisions VALUES(?,?,1,?,?,?)",
                (vid, rid, revision["text"], revision["reference_time"], revision["created_at"]),
            )
            db.execute(
                "INSERT INTO jobs(id,revision_id,status,created_at,updated_at) VALUES(?,?,'succeeded',?,?)",
                (jid, vid, record["created_at"], record["updated_at"]),
            )
            for position, memory in enumerate(memories):
                mid = f"synthetic-m-{index:06d}-{position}"
                db.execute(
                    "INSERT INTO memories VALUES(?,?,?,?,?)",
                    (mid, vid, jid, memory["local_id"], memory["payload"]),
                )
                db.execute(
                    "INSERT INTO embeddings SELECT ?,model_key,dimensions,vector FROM embeddings WHERE memory_id=?",
                    (mid, memory["id"]),
                )
                db.execute(
                    "INSERT INTO evidence SELECT ?,position,quote,start,end FROM evidence WHERE memory_id=?",
                    (mid, memory["id"]),
                )
                db.execute(
                    "INSERT INTO facts SELECT ?,projection_version,actor,recipient,object_key,payload,? FROM facts WHERE memory_id=?",
                    (mid, mid, memory["id"]),
                )
        store.bump(db)
    store.checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--records", type=int, default=10000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if _native_matcher() is None:
        raise RuntimeError("C++ matcher must be installed before real-model comparison")
    revision = hashlib.file_digest(
        Path("C:/models/bge-m3-Q8_0.gguf").open("rb"), "sha256"
    ).hexdigest()
    result = dict(
        samples=args.samples,
        records=args.records,
        seed="identical repeated synthetic book-gift source",
        seed_created_with="GPU real extraction and embeddings; shared across all modes/backends",
        cpu_forced_on_gpu_host=True,
        runs=[],
        original_model_budget=dict(timeout=180, chat_timeout=300),
        sources={
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (
                "native/keyword_match.cpp",
                "pma/search_explain.py",
                "pma/service.py",
                "pma/chat/engine.py",
            )
        },
    )
    seed_path = args.output / "synthetic-seed.db"
    for mode in ("gpu", "cpu"):
        owned, logs = [], []
        mode_root = args.output / mode
        mode_root.mkdir()
        try:
            for index, (model, context) in enumerate(
                (("Qwen3-8B-Q4_K_M.gguf", 16384), ("bge-m3-Q8_0.gguf", 8192))
            ):
                log = (mode_root / f"server-{index}.log").open("w", encoding="utf-8")
                logs.append(log)
                command = [
                    "C:/llama.cpp/llama-server.exe",
                    "-m",
                    f"C:/models/{model}",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(18081 + index),
                    "-c",
                    str(context),
                    "-ngl",
                    "99" if mode == "gpu" else "0",
                    "--alias",
                    "qwen3" if index == 0 else "bge-m3",
                    "--log-disable",
                ]
                command += (
                    ["-np", "1"]
                    if index == 0
                    else ["-b", "8192", "-ub", "8192", "--embedding", "--pooling", "cls"]
                )
                process = subprocess.Popen(
                    command, stdout=log, stderr=log, creationflags=0x08000000
                )
                owned.append(process)
                wait_ready(process, 18081 + index)
            settings = AppSettings(
                data_dir=mode_root,
                embedding_revision=revision,
                embedding_endpoint="http://127.0.0.1:18082/v1/embeddings",
                answer_validation=True,
                llm=Settings(
                    endpoint="http://127.0.0.1:18081/v1/chat/completions",
                    model="qwen3",
                    timeout=180,
                ),
            )
            if not seed_path.exists():
                service = Service(Store(seed_path), LocalModels(settings), settings)
                record = service.store.create(SHORT, "2026-10-19T09:00:00+09:00")
                service.run_one()
                if service.store.job(record["job_id"])["status"] != "succeeded":
                    raise RuntimeError("Real synthetic seed extraction failed")
                service.store.checkpoint()
                expand_seed(seed_path, args.records)
                with service.store.connect() as db:
                    result["memories"] = db.execute("SELECT count(*) FROM memories").fetchone()[0]
            services = {}
            for backend in ("python", "cpp"):
                path = mode_root / f"{backend}.db"
                shutil.copy2(seed_path, path)
                services[backend] = Service(Store(path), LocalModels(settings), settings)
            for scenario in ("search", "memory_chat"):
                failures = 0
                for sample in range(args.samples + 1):
                    order = ("python", "cpp") if sample % 2 == 0 else ("cpp", "python")
                    for backend in order:
                        os.environ["PMA_KEYWORD_BACKEND"] = backend
                        service = services[backend]
                        import pma.search_explain as matcher_module

                        loader = matcher_module._native_matcher
                        actual = loader()
                        metrics = dict(native_calls=0, native_seconds=0.0, matching_rows=0)

                        def invoke(rows, terms, vocabulary, normalize):
                            start = time.perf_counter()
                            try:
                                return actual(rows, terms, vocabulary, normalize)
                            finally:
                                metrics["native_calls"] += 1
                                metrics["matching_rows"] += len(rows)
                                metrics["native_seconds"] += time.perf_counter() - start

                        matcher_module._native_matcher = lambda: invoke
                        row = dict(
                            mode=mode,
                            backend=backend,
                            scenario=scenario,
                            sample=sample,
                            warmup=sample == 0,
                        )
                        begin = time.perf_counter()
                        try:
                            with (
                                MemorySampler([os.getpid()] + [p.pid for p in owned]) as memory,
                                instrument_http() as calls,
                            ):
                                if scenario == "search":
                                    response = service.search(QUESTION, today="2026-10-19")
                                    row["result_count"] = len(response.get("results", []))
                                else:
                                    engine = ChatEngine(service)
                                    sid = engine.store.create_empty()["id"]
                                    response = engine.message(
                                        sid,
                                        "benchmark",
                                        QUESTION,
                                        today="2026-10-19",
                                        mode="memory",
                                    )
                                    row["validation"] = response.get("validation")
                                    row["items"] = len(response.get("items", []))
                                    row["citations"] = sum(
                                        len(item.get("citations", []))
                                        for item in response.get("items", [])
                                    )
                                    row["expected_book"] = any(
                                        "책" in item.get("text", "")
                                        for item in response.get("items", [])
                                    )
                                row.update(
                                    seconds=time.perf_counter() - begin,
                                    status=response["status"],
                                    http_calls=calls,
                                    response_digest=digest(response),
                                )
                            row.update(
                                ram_peak_mib=max(memory.ram, default=0),
                                gpu_total_peak_mib=max(memory.vram, default=None),
                            )
                            if backend == "cpp" and not metrics["native_calls"]:
                                raise RuntimeError("C++ path was not called")
                        except Exception as exc:
                            row.update(
                                seconds=time.perf_counter() - begin,
                                status="error",
                                error_code=getattr(exc, "code", type(exc).__name__),
                            )
                            failures += 1
                        finally:
                            matcher_module._native_matcher = loader
                            if "calls" in locals():
                                row.setdefault("http_calls", calls)
                            if "memory" in locals():
                                row.update(
                                    ram_peak_mib=max(memory.ram, default=0),
                                    gpu_total_peak_mib=max(memory.vram, default=None),
                                )
                        row.update(metrics)
                        result["runs"].append(row)
                        (args.output / "results.json").write_text(
                            json.dumps(result, indent=2), encoding="utf-8"
                        )
                        print(
                            json.dumps(
                                {
                                    k: row.get(k)
                                    for k in (
                                        "mode",
                                        "backend",
                                        "scenario",
                                        "sample",
                                        "status",
                                        "seconds",
                                        "native_calls",
                                        "ram_peak_mib",
                                        "gpu_total_peak_mib",
                                    )
                                }
                            ),
                            flush=True,
                        )
                    if failures >= 3:
                        result.setdefault("incomplete_scenarios", {})[f"{mode}/{scenario}"] = {
                            "reason": "repeated_request_failures",
                            "requested_per_backend": args.samples,
                            "measured_per_backend": sample,
                        }
                        break
        finally:
            for process in owned:
                if process.poll() is None:
                    process.terminate()
            for process in owned:
                try:
                    process.wait(15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for log in logs:
                log.close()
    result["completed"] = True
    (args.output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
