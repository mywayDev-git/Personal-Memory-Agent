"""Isolated real-model latency/quality benchmark; only hand-authored synthetic records.

Each measured request starts from the same seed database. A follow-up includes
an unmeasured anchor turn. Cold model startup, indexing and warmups are separate.
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import socket
import statistics
import subprocess
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from config.settings import Settings
from evaluation.latency_models import MODELS, digest
from evaluation.performance_benchmark import MemorySampler, wait_ready
from pma.chat.engine import ChatEngine
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.llm_client import request_budget
from scripts.memory_agent.performance import profile_request
from scripts.memory_agent.validator import load_schema, schema_errors

DOCUMENTS = [
    ("gift", "2026년 10월 12일 민수에게 파란색 책을 선물했다.", "선물했다", "파란색 책"),
    ("negative", "지연에게는 선물을 주지 않았다.", "주지 않았다", "선물"),
    ("study", "2026년 10월 1일 파이썬 공부를 시작했다.", "시작했다", "파이썬"),
    ("stopped", "파이썬 공부를 접었다.", "접었다", "파이썬"),
    ("plan", "도서관 책은 2026년 10월 25일까지 반납할 계획이다.", "반납할 계획이다", "도서관 책"),
    ("cancel", "부산 여행은 취소했다. 비가 많이 내렸기 때문이다.", "취소했다", "부산 여행"),
    ("coworker", "회사 동료 민수는 프론트엔드 개발자다.", "개발자다", "민수"),
    ("club", "동아리 친구 민수는 수학 교사다.", "교사다", "민수"),
    ("note", "파이썬 공부 노트: asyncio.gather로 비동기 작업을 모았다.", "모았다", "파이썬"),
    ("unrelated", "2026년 10월 13일 공원에서 산책했다.", "산책했다", "공원"),
    ("long", "검색 프로젝트 메모. " + "원문 근거와 정확한 인용을 유지하며 검색을 검토했다. " * 40,
     "검토했다", "검색 프로젝트"),
]
CASES = {
    "simple_search": {"question": "민수에게 무엇을 선물했어?", "search": True, "gold": ["gift"]},
    "alias_ko": {"question": "파이썬 공부 기록", "search": True, "gold": ["study", "stopped", "note"]},
    "alias_en": {"question": "Python 공부 기록", "search": True, "gold": ["study", "stopped", "note"]},
    "typo": {"question": "파이선 공부 기록", "search": True, "gold": ["study", "stopped", "note"]},
    "simple_answer": {"question": "2026년 10월 12일 민수에게 무엇을 선물했어?", "gold": ["gift"]},
    "stopped": {"question": "파이썬 공부를 중단한 기록이 있어?", "gold": ["stopped"]},
    "negation": {"question": "지연에게 선물을 줬어?", "gold": ["negative"]},
    "plan": {"question": "도서관 책은 실제로 반납했어?", "gold": ["plan"]},
    "identity": {"question": "민수는 누구야?", "clarification": True, "gold": ["coworker", "club"]},
    "followup": {"question": "그 사람 직업은 뭐야?", "anchor": "회사 동료 민수는 누구야?", "gold": ["coworker"]},
    "additional_search": {"question": "부산 여행은 왜 취소했어?", "gold": ["cancel"]},
    "no_evidence": {"question": "지연의 혈액형이 뭐야?", "absent": True, "gold": []},
    "long_evidence": {"question": "검색 프로젝트에서 무엇을 검토했어?", "gold": ["long"]},
    "concurrent": {"question": "민수에게 무엇을 선물했어?", "gold": ["gift"], "background": True},
}


def summary(rows):
    measured = [row for row in rows if not row.get("warmup")]
    completed = [row for row in measured if not row.get("error_code")]
    values = sorted(row["seconds"] for row in completed)
    return {
        "samples": len(measured), "completed": len(completed),
        "failures": len(measured) - len(completed),
        "failure_rate": (len(measured) - len(completed)) / len(measured) if measured else None,
        "median_seconds": statistics.median(values) if values else None,
        "p95_seconds": values[math.ceil(.95 * len(values)) - 1] if values else None,
        "quality_passes": sum(row.get("quality", {}).get("passed", False) for row in measured),
        "peak_ram_mb": max((r.get("ram_peak_mb", 0) for r in measured), default=None),
        "peak_gpu_total_mb": max((r["gpu_total_peak_mb"] for r in measured
                                  if r.get("gpu_total_peak_mb") is not None), default=None),
    }


@contextmanager
def servers(args, generation, embedding):
    processes, logs = [], []
    started = time.perf_counter()
    commands = []
    for port in (args.port, args.port + 1):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    try:
        for index, path in enumerate((generation, embedding)):
            log = (args.output / f"server-{index}.log").open("w", encoding="utf-8")
            logs.append(log)
            gpu = args.placement == "gpu" or (args.placement == "hybrid" and index == 0)
            command = [str(args.server), "-m", str(path.resolve()), "--host", "127.0.0.1",
                       "--port", str(args.port + index), "-c", "16384" if index == 0 else "8192",
                       "-ngl", "99" if gpu else "0", "--alias", "latency-generation" if index == 0 else "latency-embedding",
                       "--flash-attn", args.flash, "--log-disable"]
            command += ["-np", "1"] if index == 0 else [
                "--embedding", "--pooling", "last" if args.embedding == "qwen" else "cls",
                "--embd-normalize", "2", "-b", "8192", "-ub", "8192"]
            if args.threads:
                command += ["-t", str(args.threads)]
            commands.append(command)
            process = subprocess.Popen(command, stdout=log, stderr=log,
                                       creationflags=0x08000000 if os.name == "nt" else 0)
            processes.append(process)
            wait_ready(process, args.port + index)
        yield processes, {"seconds": time.perf_counter() - started, "commands": commands}
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
        for log in logs:
            log.close()


def seed_database(path, models, settings):
    store = Store(path)
    keys = {}
    # Documents use the document embedding path, never the query instruction.
    vectors = models.embed([row[1] for row in DOCUMENTS])
    for (key, text, predicate, obj), vector in zip(DOCUMENTS, vectors, strict=True):
        record = store.create(text, "2026-10-19T09:00:00+09:00")
        job = store.claim()
        date = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
        event_time = {"raw": None, "start": None, "end": None, "precision": "unknown", "certainty": "uncertain"}
        if date:
            event_time.update(raw=date[0], start=f"{int(date[1]):04}-{int(date[2]):02}-{int(date[3]):02}", precision="day", certainty="explicit")
        memory = {"local_id": "m1", "content": text,
                  "subject": {"kind": "self", "value": "나", "value_type": "string"},
                  "predicate": predicate, "object": {"kind": "entity", "value": obj, "value_type": "string"},
                  "target": None, "memory_type": "event", "polarity": "neutral", "content_certainty": "explicit",
                  "assertion_polarity": "negated" if key == "negative" else "affirmed",
                  "evidence": [{"quote": text}], "time": event_time}
        schema = load_schema(Path("schema/memory_extraction_output.schema.json"))
        if schema_errors({"memories": [{k: v for k, v in memory.items() if k != "local_id"}]}, schema):
            raise ValueError("INVALID_SYNTHETIC_MEMORY")
        store.publish(job, [memory], [vector], settings.embedding_key, {})
        keys[record["record_id"]] = key
    store.checkpoint()
    return keys


def quality(case, response, evidence, keys):
    found = {keys.get(row["record_id"]) for row in evidence}
    gold = set(case["gold"])
    if case.get("search"):
        return {"passed": gold <= found, "recall": len(found & gold) / len(gold),
                "precision": len(found & gold) / len(found) if found else 0}
    status = response["status"]
    citations = response.get("citation_details", [])
    valid = all(any(row["id"] == ref["memory_id"] and
                    row["source_text"][ref["start"]:ref["end"]] == ref["quote"]
                    for row in evidence) for ref in citations)
    cited = {keys.get(ref["record_id"]) for ref in citations}
    passed = (status == "insufficient_evidence" if case.get("absent") else
              status == "needs_clarification" and gold <= cited if case.get("clarification") else
              status == "answered" and response.get("validation") == "model_checked" and gold <= cited)
    return {"passed": passed and valid, "citation_spans_valid": valid,
            "gold_sources_cited": len(cited & gold), "gold_sources": len(gold),
            "status": status, "validation": response.get("validation")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--server", type=Path, default=Path("C:/llama.cpp/llama-server.exe"))
    parser.add_argument("--model-directory", type=Path, default=Path(".local/response-latency/models"))
    parser.add_argument("--generation", choices=["baseline", "q4", "q8"], default="baseline")
    parser.add_argument("--embedding", choices=["bge", "qwen"], default="bge")
    parser.add_argument("--placement", choices=["cpu", "gpu", "hybrid"], default="cpu")
    parser.add_argument("--flash", choices=["auto", "on", "off"], default="auto")
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--port", type=int, default=18181)
    parser.add_argument("--variants", nargs="+", choices=["baseline", "cached", "batch8", "plain", "combined"], default=["baseline"])
    parser.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    parser.add_argument("--multilingual", action="store_true")
    args = parser.parse_args()
    if args.samples < 1 or args.output.exists() or not 1024 <= args.port < 65535:
        parser.error("positive samples, unused output directory and valid port required")
    generation = Path("C:/models/Qwen3-8B-Q4_K_M.gguf") if args.generation == "baseline" else args.model_directory / MODELS[f"generation-{args.generation}"]["filename"]
    embedding = Path("C:/models/bge-m3-Q8_0.gguf") if args.embedding == "bge" else args.model_directory / MODELS["embedding-q8"]["filename"]
    hashes = {"generation": digest(generation), "embedding": digest(embedding), "server": digest(args.server)}
    args.output.mkdir(parents=True)
    if shutil.disk_usage(args.output).free < 512 * 1024 * 1024:
        parser.error("at least 512 MiB free space required for evaluation output")
    report = {"schema_version": 1, "personal_database_used": False, "configuration": vars(args).copy(),
              "hashes": hashes, "seed_policy": "hand-authored synthetic memories, real document embeddings",
              "runs": [], "summary": {}, "sources": {
                  p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for root in ("pma", "scripts/memory_agent") for p in Path(root).rglob("*.py")}}

    def save():
        report["summary"] = {f"{variant}/{case}": summary([
            r for r in report["runs"] if r["variant"] == variant and r["case"] == case])
            for variant in args.variants for case in args.cases}
        temporary = args.output / "results.partial"
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(args.output / "results.json")

    try:
        with servers(args, generation, embedding) as (processes, startup):
            report["startup"] = startup
            settings = AppSettings(data_dir=args.output, embedding_revision=hashes["embedding"],
                embedding_endpoint=f"http://127.0.0.1:{args.port + 1}/v1/embeddings",
                embedding_model="bge-m3" if args.embedding == "bge" else "qwen3-embedding-0.6b",
                llm=Settings(endpoint=f"http://127.0.0.1:{args.port}/v1/chat/completions", model="latency-generation"))
            if args.embedding == "qwen":
                settings = replace(settings, embedding_profile="qwen3-retrieval-v1")
            started = time.perf_counter()
            seed = args.output / "synthetic-seed.db"
            keys = seed_database(seed, LocalModels(settings), settings)
            report["index_seconds"] = time.perf_counter() - started
            if args.multilingual:
                from evaluation.multilingual_search import evaluate

                evaluate(settings, args.output / "multilingual.json")
            for case_name in args.cases:
                case = CASES[case_name]
                for sample in range(args.samples + 1):
                    order = args.variants if sample % 2 == 0 else list(reversed(args.variants))
                    for variant in order:
                        variant_settings = replace(settings, request_token_cache=variant != "baseline",
                                                   selection_batch_size=8 if variant in {"batch8", "combined"} else 4,
                                                   chat_presentation="plain" if variant in {"plain", "combined"} else "reviewed")
                        path = args.output / f"{case_name}-{sample}-{variant}.db"
                        shutil.copy2(seed, path)
                        service = Service(Store(path), LocalModels(variant_settings), variant_settings)
                        engine = ChatEngine(service)
                        sid = engine.store.create_empty()["id"]
                        if case.get("anchor"):
                            engine.message(sid, "anchor", case["anchor"], today="2026-10-19", mode="memory")
                        row = {"case": case_name, "sample": sample, "warmup": sample == 0, "variant": variant}
                        worker = None
                        background_record = None
                        if case.get("background"):
                            arrival = threading.Event()
                            extract = service.models.extract
                            def observed_extract(*a, **kw):
                                arrival.set()
                                return extract(*a, **kw)
                            service.models.extract = observed_extract
                            background_record = service.store.create("2026년 10월 15일 도서관에서 책을 빌렸다.", "2026-10-19T09:00:00+09:00")
                            worker = threading.Thread(target=service.run_one)
                            worker.start()
                            row["arrival_during_extract"] = arrival.wait(30) and service.gate.locked()
                        with MemorySampler([os.getpid()] + [p.pid for p in processes]) as mem:
                            started = time.perf_counter()
                            try:
                                if case.get("search"):
                                    with profile_request() as profile, request_budget(300) as budget:
                                        response = service.search(case["question"], today="2026-10-19")
                                    row["performance"] = {"profile": profile.snapshot(), "model_http_calls": budget.calls}
                                    evidence = response["results"]
                                else:
                                    response = engine.message(sid, "measured", case["question"], today="2026-10-19", mode="memory")
                                    message = engine.store.get(sid)["messages"][-1]
                                    row["performance"] = message["snapshot"].get("performance", {})
                                    evidence = message["evidence"]
                                row["quality"] = quality(case, response, evidence, keys)
                                row["status"] = response.get("status")
                                # Separate synthetic quality artifact; performance rows contain no text.
                                artifacts = args.output / "quality"
                                artifacts.mkdir(exist_ok=True)
                                (artifacts / f"{case_name}-{sample}-{variant}.json").write_text(
                                    json.dumps({"response": response, "evidence": evidence}, ensure_ascii=False, indent=2), encoding="utf-8")
                            except Exception as exc:
                                row["error_code"] = getattr(exc, "code", type(exc).__name__)
                                frame = traceback.extract_tb(exc.__traceback__)[-1]
                                row["error_location"] = {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                                messages = engine.store.get(sid)["messages"]
                                row["performance"] = (messages[-1].get("snapshot") or {}).get("performance", {}) if messages else {}
                            row["seconds"] = time.perf_counter() - started
                        if worker is not None:
                            worker.join()
                            row["background_status"] = service.store.job(background_record["job_id"])["status"]
                            row.setdefault("quality", {})["passed"] = bool(
                                row.get("quality", {}).get("passed") and row["arrival_during_extract"]
                                and row["background_status"] == "succeeded")
                        row["ram_peak_mb"] = max(mem.ram, default=0)
                        row["gpu_total_peak_mb"] = max(mem.vram, default=None)
                        report["runs"].append(row)
                        save()
                        print(json.dumps({k: row.get(k) for k in ("case", "sample", "variant", "seconds", "status", "error_code", "quality")}), flush=True)
    finally:
        save()


if __name__ == "__main__":
    main()
