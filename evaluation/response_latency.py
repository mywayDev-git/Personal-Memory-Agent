"""Isolated real-model latency/quality benchmark; only hand-authored synthetic records.

Each measured request starts from the same seed database. A follow-up includes
an unmeasured anchor turn. Model startup, indexing and warmups are separate.
"""

import argparse
import hashlib
import itertools
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
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from config.settings import Settings
from evaluation.latency_models import MODELS, digest
from evaluation.latency_variants import OPTIONS, configured, parameters
from evaluation.first_response_cases import BASE_DOCUMENTS
from evaluation.performance_benchmark import MemorySampler, wait_ready
from pma.chat.engine import ChatEngine
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.llm_client import request_budget
from scripts.memory_agent.performance import profile_request
from scripts.memory_agent.validator import load_schema, schema_errors

DOCUMENTS = list(BASE_DOCUMENTS)
SCORING_VERSION = 6
CASES = {
    "simple_search": {"question": "민수에게 무엇을 선물했어?", "search": True, "gold": ["gift"]},
    "alias_ko": {"question": "파이썬 공부 기록", "search": True, "gold": ["study", "stopped", "note"]},
    "alias_en": {"question": "Python 공부 기록", "search": True, "gold": ["study", "stopped", "note"]},
    "typo": {"question": "파이선 공부 기록", "search": True, "gold": ["study", "stopped", "note"]},
    "simple_answer": {"question": "2026년 10월 12일 민수에게 무엇을 선물했어?", "gold": ["gift"],
                      "answer_patterns": [r"파란|파랑|푸른|청색|blue", r"책|도서|서적|book"]},
    "stopped": {"question": "파이썬 공부를 중단한 기록이 있어?", "gold": ["stopped"],
                "answer_patterns": [r"접|중단|그만|포기"],
                "answer_excluded_patterns": [
                    r"(?:중단(?:한|했다는|했던)?|접었다는|그만둔)\s*(?:기록|내용|사실|증거)(?:은|는|이|가)?\s*(?:없(?!지)|확인되지|찾을\s*수\s*없)"]},
    "negation": {"question": "지연에게 선물을 줬어?", "gold": ["negative"],
                 "answer_patterns": [r"않|안\s*(?:했|주|줬)|부정|미전달"]},
    "plan": {"question": "도서관 책은 실제로 반납했어?", "gold": ["plan"],
             "answer_patterns": [r"계획|예정", r"확인|알\s*수\s*없|불명|불확실|실제|실행"]},
    "identity": {"question": "민수는 누구야?", "clarification": True, "gold": ["coworker", "club"]},
    "followup": {"question": "그 사람 직업은 뭐야?", "anchor": "회사 동료 민수는 누구야?", "gold": ["coworker"],
                 "answer_patterns": [r"프론트|프런트|front[- ]?end"], "allowed_sources": ["coworker"]},
    "identity_exclusion": {"question": "회사 동료 민수 말고 동아리 친구 민수의 직업은 뭐야?",
                           "gold": ["club"], "allowed_sources": ["club"],
                           "answer_patterns": [r"수학", r"교사"]},
    "stopped_date": {"question": "파이썬 공부는 언제 중단했어?", "gold": ["stopped"],
                     "answer_patterns": [r"접|중단|그만|포기", r"확인|알\s*수\s*없|미상|불명|명시.*않"]},
    "additional_search": {"question": "부산 여행은 왜 취소했어?", "gold": ["cancel"],
                          "answer_patterns": [r"비|우천|rain"]},
    "no_evidence": {"question": "지연의 혈액형이 뭐야?", "absent": True, "gold": []},
    "long_evidence": {"question": "검색 프로젝트에서 무엇을 검토했어?", "gold": ["long"]},
    "concurrent": {"question": "민수에게 무엇을 선물했어?", "gold": ["gift"], "background": True},
    "selection_batch": {"question": "기록에 담긴 내용을 모두 찾아줘", "search": True, "selection": True,
                        "gold": [key for key, *_ in DOCUMENTS]},
    "multi_hop": {"question": "회사 동료 민수의 직업과 부산 여행을 취소한 이유는 뭐야?",
                  "gold": ["coworker", "cancel"], "allowed_sources": ["coworker", "cancel"],
                  "answer_patterns": [r"프론트|프런트|front[- ]?end", r"비|우천|rain"]},
}


@contextmanager
def planning_variant(enabled):
    """Evaluation-only input reduction; source semantics and product defaults stay intact."""
    if not enabled:
        yield
        return
    from pma.chat import automatic

    original = automatic.structured
    def structured(engine, prompt, data, schema, max_tokens=1024):
        if schema is automatic.NEXT:
            data = {**data,
                    "searches": [{k: v for k, v in row.items() if k != "query_plan"}
                                 for row in data.get("searches", [])],
                    "evidence": [{k: v for k, v in row.items() if k not in {"score", "search_explanation"}}
                                 for row in data.get("evidence", [])]}
        return original(engine, prompt, data, schema, max_tokens)
    with patch.object(automatic, "structured", structured):
        yield


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


def repository_reference():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def reset_experiment_slot(port):
    """Only the fresh owned experiment server; do not relax transport URL policy."""
    from scripts.memory_agent.llm_client import local_session, validate_endpoint
    endpoint = f"http://127.0.0.1:{port}/slots/0"
    validate_endpoint(endpoint)
    with local_session() as transport:
        response = transport.post(endpoint, params={"action": "erase"}, json={},
                                  timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f"EXPERIMENT_SLOT_RESET_HTTP_{response.status_code}")


@contextmanager
def servers(args, generation, embedding):
    processes, logs = [], []
    started = time.perf_counter()
    commands = []
    startup_memory = []
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
            if not gpu:
                # Layer placement alone can leave KV/host operations on a GPU.
                command += ["--device", "none", "--no-op-offload", "--no-kv-offload"]
            command += ["-np", "1"] if index == 0 else [
                "--embedding", "--pooling", "last" if args.embedding == "qwen" else "cls",
                "--embd-normalize", "2", "-b", str(args.embedding_batch), "-ub", str(args.embedding_batch)]
            if index == 0:
                cache_type = getattr(args, 'generation_cache_type', 'f16')
                command += ['--cache-type-k', cache_type, '--cache-type-v', cache_type]
            if index == 0 and args.reset_prompt_cache:
                slot_path = args.output / "owned-slots"
                slot_path.mkdir()
                command += ["--slots", "--slot-save-path", str(slot_path.resolve()), "--cache-ram", "0"]
            if args.threads:
                command += ["-t", str(args.threads)]
            if index == 0 and getattr(args, "generation_batch_threads", 0):
                command += ["-tb", str(args.generation_batch_threads)]
            if index == 0 and getattr(args, "runtime", "llama") == "openvino":
                command = [str(args.runtime_python), "-u", "-m", "evaluation.openvino_server",
                           "--model", str(args.runtime_model.resolve()), "--port", str(args.port),
                           "--threads", str(args.threads or 8)]
            commands.append(command)
            process = subprocess.Popen(command, stdout=log, stderr=log,
                                       creationflags=0x08000000 if os.name == "nt" else 0)
            processes.append(process)
            memory = None
            try:
                if getattr(args, "startup_memory", False):
                    with MemorySampler([os.getpid()] + [p.pid for p in processes]) as memory:
                        wait_ready(process, args.port + index)
                    startup_memory.append({"server_index": index, "ram_peak_mb": max(memory.ram, default=None),
                        "private_commit_peak_mb": max(memory.private_commit, default=None),
                        "gpu_total_peak_mb": max(memory.vram, default=None),
                        "system_available_ram_min_mb": min(memory.available_ram, default=None),
                        "process_tree_complete": bool(memory.process_tree_complete) and all(memory.process_tree_complete),
                        "tracked_processes_peak": max(memory.tracked_processes, default=None)})
                else:
                    wait_ready(process, args.port + index)
            except BaseException as exc:
                failure = {
                    "phase": "server_startup", "port": args.port + index,
                    "error_type": type(exc).__name__, "returncode": process.poll(),
                    "owned_experiment_server": True}
                if memory is not None:
                    failure["startup_memory"] = {
                        "ram_peak_mb": max(memory.ram, default=None),
                        "private_commit_peak_mb": max(memory.private_commit, default=None),
                        "gpu_total_peak_mb": max(memory.vram, default=None),
                        "system_available_ram_min_mb": min(memory.available_ram, default=None)}
                (args.output / "server-failure.json").write_text(json.dumps(failure), encoding="utf-8")
                raise
        yield processes, {"seconds": time.perf_counter() - started, "commands": commands,
                          "memory": startup_memory}
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=30)
        for log in logs:
            log.close()


def seed_database(path, models, settings, *, template=None):
    if template is not None:
        shutil.copy2(template, path)
        store = Store(path)
        with store.connect() as db:
            sources = db.execute("SELECT record_id,text FROM revisions").fetchall()
            if sorted(row[1] for row in sources) != sorted(row[1] for row in DOCUMENTS):
                raise ValueError("SEED_TEMPLATE_IS_NOT_THE_SYNTHETIC_FIXTURE")
            memories = db.execute("SELECT id,payload FROM memories ORDER BY id").fetchall()
            existing = {r[0] for r in db.execute("SELECT DISTINCT model_key FROM embeddings")}
        if existing != {settings.embedding_key}:
            vectors = models.embed([json.loads(row[1])["content"] for row in memories])
            with store.connect(True) as db:
                db.execute("DELETE FROM embeddings")
                for row, vector in zip(memories, vectors, strict=True):
                    db.execute("INSERT INTO embeddings VALUES(?,?,?,?)",
                               (row[0], settings.embedding_key, len(vector), vector.astype("<f4").tobytes()))
                store.bump(db)
        store.checkpoint()
        by_text = {text: key for key, text, *_ in DOCUMENTS}
        return {rid: by_text[text] for rid, text in sources}
    store = Store(path, clock=lambda: "2026-10-19T09:00:00+09:00")
    keys = {}
    # Documents use the document embedding path, never the query instruction.
    vectors = models.embed([row[1] for row in DOCUMENTS])
    identifiers = itertools.count()
    for (key, text, predicate, obj), vector in zip(DOCUMENTS, vectors, strict=True):
        with patch("pma.store.identifier", side_effect=lambda: str(uuid5(NAMESPACE_URL, f"pma-latency-v1/{next(identifiers)}"))):
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
        with patch("pma.store.identifier", side_effect=lambda: str(uuid5(NAMESPACE_URL, f"pma-latency-v1/{next(identifiers)}"))):
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
    text = "\n".join(item["text"] for item in response.get("items", []))
    patterns_match = all(re.search(pattern, text, re.I) for pattern in case.get("answer_patterns", []))
    contradiction_free = not any(re.search(pattern, text, re.I) for pattern in case.get("answer_excluded_patterns", []))
    scope_valid = "allowed_sources" not in case or cited <= set(case["allowed_sources"])
    passed = (status == "insufficient_evidence" if case.get("absent") else
              status == "needs_clarification" and gold <= cited if case.get("clarification") else
              status == "answered" and response.get("validation") == "model_checked" and gold <= cited)
    if case.get('unknown_attribute'):
        if status == 'insufficient_evidence' and not response.get('items'):
            passed, patterns_match = True, True
        else:
            passed = status == 'answered' and response.get('validation') == 'model_checked' and bool(cited)
    return {"passed": bool(passed and valid and patterns_match and scope_valid and contradiction_free), "citation_spans_valid": valid,
            "answer_patterns_match": bool(patterns_match),
            "answer_contradiction_free": contradiction_free,
            "source_scope_valid": scope_valid,
            "gold_sources_cited": len(cited & gold), "gold_sources": len(gold),
            "status": status, "validation": response.get("validation")}


def check_cancelled(args):
    if getattr(args, "cancel_file", None) and args.cancel_file.exists():
        raise KeyboardInterrupt("LATENCY_EXPERIMENT_CANCELLED")
    floor = getattr(args, "min_free_gib", 0)
    if floor and args.output.exists() and shutil.disk_usage(args.output).free < floor * 1024 ** 3:
        raise ValueError("EXPERIMENT_DISK_FLOOR")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--server", type=Path, default=Path("C:/llama.cpp/llama-server.exe"))
    parser.add_argument("--model-directory", type=Path, default=Path(".local/response-latency/models"))
    parser.add_argument("--generation", choices=["baseline", "q4", "q8"], default="baseline")
    parser.add_argument("--runtime", choices=["llama", "openvino"], default="llama")
    parser.add_argument("--runtime-python", type=Path)
    parser.add_argument("--runtime-model", type=Path)
    parser.add_argument("--startup-memory", action="store_true")
    parser.add_argument("--min-free-gib", type=float, default=.5)
    parser.add_argument("--embedding", choices=["bge", "qwen"], default="bge")
    parser.add_argument("--placement", choices=["cpu", "gpu", "hybrid"], default="cpu")
    parser.add_argument("--flash", choices=["auto", "on", "off"], default="auto")
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--generation-batch-threads", type=int, default=0)
    parser.add_argument('--generation-cache-type', choices=['f16', 'q8_0'], default='f16')
    parser.add_argument("--embedding-batch", type=int, choices=[512, 2048, 4096, 8192], default=8192)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--port", type=int, default=18181)
    parser.add_argument("--variants", nargs="+", choices=["baseline", "cached", "batch8", "plain", "combined", "planning", "planning_plain", "reuse", "source_first", "current", "candidate"], default=["baseline"])
    parser.add_argument("--candidate-options", nargs="+", choices=list(OPTIONS), default=[])
    parser.add_argument("--baseline-options", nargs="+", choices=list(OPTIONS), default=[])
    parser.add_argument("--cold-interpretations", action="store_true",
                        help="Clear only the interpretation cache before every trial, including warmup.")
    parser.add_argument("--reset-prompt-cache", action="store_true",
                        help="Erase the owned experiment slot before each warmup/measured request")
    parser.add_argument("--cancel-file", type=Path, help="Stop between requests when this file exists")
    parser.add_argument("--cases", nargs="+", choices=list(CASES), default=list(CASES))
    parser.add_argument("--multilingual", action="store_true")
    parser.add_argument("--review-bank", action="store_true")
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--quality-only", action="store_true", help="One quality observation without latency warmup; never sufficient for speed adoption")
    parser.add_argument("--fixture-manifest-sha256")
    parser.add_argument("--fixture-split", choices=["development", "holdout", "identity_confirmation", "identity_search_confirmation", "identity_completion_confirmation", "integrity_development", "integrity_confirmation", "integrity_supplement", "integrity_v2_development", "integrity_v2_confirmation", "integrity_v3_development", "integrity_v3_confirmation", "integrity_source_development", "integrity_source_confirmation"])
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--skip-timing-on-retrieval-failure", action="store_true")
    parser.add_argument("--multilingual-current-only", action="store_true")
    parser.add_argument("--seed-template", type=Path, help="Reuse this evaluator's synthetic seed; only embeddings may be rebuilt")
    parser.add_argument("--anchor-templates", type=Path, help="Completed same-fixture results with checked anchors; does not test target-device preparation")
    parser.add_argument("--fixed-anchor", action="store_true", help="Prepare and verify one shared anchor DB per case so variants receive identical history")
    parser.add_argument("--retrieval-baseline", type=Path,
                        help="Quality-screen against a fresh 90-case report; rejected models only run the two basic timing cases")
    args = parser.parse_args()
    if args.runtime != 'llama' and args.generation_cache_type != 'f16':
        parser.error('KV cache profile comparison requires the owned llama runtime')
    if (args.samples < 1 or args.output.exists() or not 1024 <= args.port < 65535
            or args.threads < 0 or args.generation_batch_threads < 0):
        parser.error("positive samples, unused output directory and valid port required")
    preparation_started = time.perf_counter()
    if args.runtime == "openvino" and (args.placement != "cpu" or not args.runtime_python or not args.runtime_model):
        parser.error("OpenVINO trials require cpu placement, --runtime-python and --runtime-model")
    generation = Path("C:/models/Qwen3-8B-Q4_K_M.gguf") if args.generation == "baseline" else args.model_directory / MODELS[f"generation-{args.generation}"]["filename"]
    if args.runtime == "openvino":
        generation = args.runtime_model / "openvino_model.bin"
    embedding = Path("C:/models/bge-m3-Q8_0.gguf") if args.embedding == "bge" else args.model_directory / MODELS["embedding-q8"]["filename"]
    hashes = {"generation": digest(generation), "embedding": digest(embedding), "server": digest(args.server)}
    native_extensions = {str(path): digest(path) for path in Path("pma").glob("*.pyd")}
    artifact_verification_seconds = time.perf_counter() - preparation_started
    os.environ["PMA_GENERATION_REVISION"] = hashes["generation"]
    args.output.mkdir(parents=True)
    if not math.isfinite(args.min_free_gib) or args.min_free_gib < .5 or shutil.disk_usage(args.output).free < args.min_free_gib * 1024 ** 3:
        parser.error("insufficient free disk space for the configured experiment floor")
    report = {"schema_version": 1, "personal_database_used": False, "configuration": vars(args).copy(),
              "status": "RUNNING", "execution_completed": False,
              "cpu_placement_policy": "device-none-no-op-offload-no-kv-offload",
              "gpu_absent_environment_verified": False,
              "measurement_scope": "response_return_before_quality_artifacts",
              "quality_scoring_version": SCORING_VERSION,
              "synthetic_fixture_sha256": hashlib.sha256(json.dumps(
                  {"documents": DOCUMENTS, "cases": CASES}, sort_keys=True,
                  ensure_ascii=False).encode()).hexdigest(),
              "repository_reference_revision": repository_reference(),
              "artifact_verification_seconds": artifact_verification_seconds,
              "hashes": hashes, "seed_policy": "hand-authored synthetic memories, real document embeddings",
              "native_extensions": native_extensions,
              "keyword_backend_requested": os.getenv("PMA_KEYWORD_BACKEND", "auto"),
              "runs": [], "summary": {}, "sources": {
                  p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for root in ("pma", "scripts/memory_agent") for p in Path(root).rglob("*.py")}}
    report["evaluator_sources"] = {p: digest(Path(p)) for p in (
        "evaluation/response_latency.py", "evaluation/multilingual_search.py", "evaluation/response_latency_report.py",
        "evaluation/latency_variants.py", "evaluation/latency_recheck.py", "evaluation/performance_benchmark.py",
        "evaluation/first_response.py", "evaluation/first_response_cases.py", "evaluation/first_response_manifest.json",
        "evaluation/review_bank.py", "evaluation/identity_followup_cases.py", "evaluation/identity_followup_manifest.json",
        "evaluation/anchor_templates.py", "evaluation/identity_search_cases.py", "evaluation/identity_search_manifest.json",
        "evaluation/identity_completion_cases.py", "evaluation/identity_completion_manifest.json",
        "evaluation/answer_integrity_cases.py", "evaluation/answer_integrity_cases.json", "evaluation/answer_integrity_manifest.json",
        "evaluation/answer_integrity_review.py", "evaluation/identity_cause_v2_cases.json", "evaluation/identity_cause_v2_manifest.json", "evaluation/identity_cause_v3_cases.json", "evaluation/identity_cause_v3_manifest.json", "evaluation/quote_boundary_cases.json", "evaluation/quote_boundary_manifest.json", "evaluation/source_completion_cases.json", "evaluation/source_completion_manifest.json", "evaluation/answer_integrity_supplement.json", "evaluation/answer_integrity_supplement_manifest.json")}
    if args.seed_template:
        report["seed_template_sha256"] = digest(args.seed_template)
    if args.runtime == "openvino":
        report["runtime_artifacts"] = {str(p): digest(p) for p in args.runtime_model.iterdir() if p.is_file() and p != generation}
        report["runtime_gateway_sha256"] = digest(Path("evaluation/openvino_server.py"))
        report["evaluator_sources"]["evaluation/openvino_server.py"] = report["runtime_gateway_sha256"]
        packages = args.runtime_python.parent.parent / "Lib" / "site-packages"
        report["runtime_binaries"] = {str(p.relative_to(packages)): digest(p)
            for name in ("openvino_genai", "openvino", "openvino_tokenizers")
            for p in (packages / name).rglob("*") if p.suffix in {".pyd", ".dll"}}
    if args.retrieval_only:
        args.multilingual = True
        report["configuration"]["multilingual"] = True
        args.cases = []
        report["configuration"]["cases"] = []
    if args.review_only:
        args.review_bank = True
        report["configuration"]["review_bank"] = True
        args.cases = []
        report["configuration"]["cases"] = []

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
            keys = seed_database(seed, LocalModels(settings), settings, template=args.seed_template)
            report["index_seconds"] = time.perf_counter() - started
            report["synthetic_seed_sha256"] = digest(seed)
            report["initial_preparation_seconds"] = time.perf_counter() - preparation_started
            if args.review_bank:
                from evaluation.review_bank import evaluate as evaluate_review
                if (args.fixture_split or '').startswith('integrity_'):
                    from functools import partial
                    from evaluation.answer_integrity_review import evaluate
                    evaluate_review = partial(evaluate, split=args.fixture_split.removeprefix('integrity_'))
                from pma.chat.models import ChatLocalModels
                review_memory = None
                try:
                    with MemorySampler([os.getpid()] + [p.pid for p in processes]) as review_memory:
                        report["review_bank"] = evaluate_review(
                            ChatLocalModels(configured(settings, args.candidate_options)), args.output / "review-quality.json",
                            before_call=lambda: check_cancelled(args))
                finally:
                    if review_memory is not None:
                        report.setdefault("review_bank", {"status": "ERROR"})["memory"] = {
                            "ram_peak_mb": max(review_memory.ram, default=None),
                            "private_commit_peak_mb": max(review_memory.private_commit, default=None),
                            "gpu_total_peak_mb": max(review_memory.vram, default=None),
                            "system_available_ram_min_mb": min(review_memory.available_ram, default=None),
                            "process_tree_complete": bool(review_memory.process_tree_complete) and all(review_memory.process_tree_complete),
                            "tracked_processes_peak": max(review_memory.tracked_processes, default=None)}
                save()
            if args.multilingual:
                from evaluation.multilingual_search import evaluate

                multilingual = evaluate(configured(settings, args.candidate_options), args.output / "multilingual.json", current_only=args.multilingual_current_only)
                if args.retrieval_baseline:
                    from evaluation.response_latency_report import retrieval_gate

                    baseline = json.loads(args.retrieval_baseline.read_text(encoding="utf-8"))
                    report["retrieval_gate"] = retrieval_gate(baseline, multilingual)
                    if not report["retrieval_gate"]["passed"]:
                        report["screen_rejected"] = True
                        report["configuration"]["original_cases"] = args.cases
                        args.cases = [] if args.skip_timing_on_retrieval_failure else ["simple_search", "simple_answer"]
                        report["configuration"]["cases"] = args.cases
                        print(json.dumps({"retrieval_gate": report["retrieval_gate"],
                                          "remaining_timing_cases": args.cases}), flush=True)
            for case_name in args.cases:
                check_cancelled(args)
                case = CASES[case_name]
                case_seed, anchored_sid = seed, None
                if case.get("anchor") and args.fixed_anchor:
                    anchor_started = time.perf_counter()
                    case_seed = args.output / f"{case_name}-anchor.db"
                    if args.anchor_templates:
                        from evaluation.anchor_templates import import_anchor
                        anchored_sid, anchor_metadata = import_anchor(args.anchor_templates, case_name, case, case_seed,
                            documents=DOCUMENTS, hashes=hashes, fixture_split=args.fixture_split,
                            fixture_sha256=args.fixture_manifest_sha256, keys=keys, score=quality)
                        anchor_metadata['preparation_seconds'] = time.perf_counter() - anchor_started
                        report.setdefault('anchors', {})[case_name] = anchor_metadata
                        save()
                    else:
                        anchored_sid = None
                if case.get("anchor") and args.fixed_anchor and not anchored_sid:
                    shutil.copy2(seed, case_seed)
                    anchor_service = Service(Store(case_seed), LocalModels(settings), settings)
                    anchor_engine = ChatEngine(anchor_service)
                    anchored_sid = anchor_engine.store.create_empty()["id"]
                    anchor_response = anchor_engine.message(
                        anchored_sid, "anchor", case["anchor"], today="2026-10-19", mode="memory")
                    anchor_message = anchor_engine.store.get(anchored_sid)["messages"][-1]
                    anchor_quality = quality({**case, **case.get('anchor_case', {})}, anchor_response, anchor_message["evidence"], keys)
                    if not anchor_quality["passed"]:
                        raise ValueError("INVALID_SHARED_ANCHOR")
                    anchor_service.store.checkpoint()
                    report.setdefault("anchors", {})[case_name] = {
                        "quality": anchor_quality, "sha256": digest(case_seed),
                        "preparation_seconds": time.perf_counter() - anchor_started,
                        "shared_between_variants": True,
                    }
                for sample in range(1 if args.quality_only else 0, args.samples + 1):
                    order = args.variants if sample % 2 == 0 else list(reversed(args.variants))
                    for variant in order:
                        check_cancelled(args)
                        if args.reset_prompt_cache:
                            reset_experiment_slot(args.port)
                        variant_settings = replace(settings, request_token_cache=variant in {"cached", "combined"},
                                                   request_reuse=variant == "reuse",
                                                   source_stop_drafts=variant in {"reuse", "source_first"},
                                                   selection_batch_size=8 if variant in {"batch8", "combined"} else 4,
                                                   chat_presentation="plain" if variant in {"plain", "combined", "planning_plain"} else "reviewed")
                        if variant in {"current", "candidate"}:
                            variant_settings = configured(settings, args.candidate_options if variant == "candidate" else args.baseline_options)
                        from pma.interpretation_cache import clear_interpretations, cache_info
                        if args.cold_interpretations:
                            clear_interpretations()
                        path = args.output / f"{case_name}-{sample}-{variant}.db"
                        shutil.copy2(case_seed, path)
                        service = Service(Store(path), LocalModels(variant_settings), variant_settings)
                        validation_trace = []
                        # Only this synthetic harness retains content-rich rejection
                        # diagnostics; ordinary performance logs remain content-free.
                        service.diagnostic_sink = lambda entry: validation_trace.append(entry) if entry.get('stage') == 'chat_validation' else None
                        engine = ChatEngine(service)
                        sid = anchored_sid or engine.store.create_empty()["id"]
                        if case.get("anchor") and not anchored_sid:
                            with planning_variant(variant in {"planning", "planning_plain"}):
                                engine.message(sid, "anchor", case["anchor"], today="2026-10-19", mode="memory")
                        row = {"case": case_name, "sample": sample, "warmup": sample == 0, "variant": variant,
                               "parameters": {"request_token_cache": variant_settings.request_token_cache,
                                              "request_reuse": variant_settings.request_reuse,
                                              "source_stop_drafts": variant_settings.source_stop_drafts,
                                              "selection_batch_size": variant_settings.selection_batch_size,
                                              "chat_presentation": variant_settings.chat_presentation,
                                              "compact_planning": variant in {"planning", "planning_plain"}}}
                        if variant in {"current", "candidate"}:
                            row["parameters"] = parameters(variant_settings)
                        row["interpretation_cache_before"] = cache_info()
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
                            profile = budget = None
                            try:
                                if case.get("search"):
                                    with profile_request() as profile, request_budget(300) as budget:
                                        if case.get("selection"):
                                            _, candidates = service.store.snapshot(variant_settings.embedding_key)
                                            evidence = [{"id": r["id"], "record_id": r["record_id"],
                                                         "source_text": r["text"], "content": r["memory"]["content"],
                                                         "fact": r["fact"], "evidence": r["evidence"]} for r in candidates]
                                            decisions = service.models.select_explained(case["question"], evidence)
                                            response = {"status": "ok", "results": [r for r in evidence
                                                if decisions[r["id"]]["category"] not in {"irrelevant", "unverified_selection"}]}
                                        else:
                                            response = service.search(case["question"], today="2026-10-19")
                                    row["seconds"] = time.perf_counter() - started
                                    row["performance"] = {"profile": profile.snapshot(), "model_http_calls": budget.calls}
                                    evidence = response["results"]
                                else:
                                    with planning_variant(variant in {"planning", "planning_plain"}):
                                        response = engine.message(sid, "measured", case["question"], today="2026-10-19", mode="memory")
                                    row["seconds"] = time.perf_counter() - started
                                    message = engine.store.get(sid)["messages"][-1]
                                    row["performance"] = message["snapshot"].get("performance", {})
                                    evidence = message["evidence"]
                                row["quality"] = quality(case, response, evidence, keys)
                                row["status"] = response.get("status")
                                # Separate synthetic quality artifact; performance rows contain no text.
                                artifacts = args.output / "quality"
                                artifacts.mkdir(exist_ok=True)
                                (artifacts / f"{case_name}-{sample}-{variant}.json").write_text(
                                    json.dumps({"response": response, "evidence": evidence, "validation_trace": validation_trace}, ensure_ascii=False, indent=2), encoding="utf-8")
                            except Exception as exc:
                                row["error_phase"] = "evaluation_after_response" if "seconds" in row else "response"
                                row["error_code"] = getattr(exc, "code", type(exc).__name__)
                                frame = traceback.extract_tb(exc.__traceback__)[-1]
                                row["error_location"] = {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
                                if profile is not None:
                                    row["performance"] = {"profile": profile.snapshot("failed"),
                                                          "model_http_calls": budget.calls if budget else []}
                                else:
                                    messages = engine.store.get(sid)["messages"]
                                    row["performance"] = (messages[-1].get("snapshot") or {}).get("performance", {}) if messages else {}
                            row.setdefault("seconds", time.perf_counter() - started)
                            row["interpretation_cache_after"] = cache_info()
                        if worker is not None:
                            worker.join()
                            row["background_status"] = service.store.job(background_record["job_id"])["status"]
                            row.setdefault("quality", {})["passed"] = bool(
                                row.get("quality", {}).get("passed") and row["arrival_during_extract"]
                                and row["background_status"] == "succeeded")
                        row["ram_peak_mb"] = max(mem.ram, default=0)
                        row["private_commit_peak_mb"] = max(mem.private_commit, default=None)
                        row["system_available_ram_min_mb"] = min(mem.available_ram, default=None)
                        row["memory_processes_complete"] = (bool(mem.observed_processes)
                            and all(count == len(mem.pids) for count in mem.observed_processes)
                            and bool(mem.process_tree_complete) and all(mem.process_tree_complete))
                        row["tracked_processes_peak"] = max(mem.tracked_processes, default=None)
                        row["page_fault_delta"] = (max(mem.page_faults) - min(mem.page_faults)
                                                   if mem.page_faults else None)
                        row["gpu_total_peak_mb"] = max(mem.vram, default=None)
                        report["runs"].append(row)
                        save()
                        print(json.dumps({k: row.get(k) for k in ("case", "sample", "variant", "seconds", "status", "error_code", "quality")}), flush=True)
            report["source_unchanged"] = all(digest(Path(path)) == expected
                                             for path, expected in report["sources"].items())
            report["evaluator_unchanged"] = all(digest(Path(path)) == expected
                                                for path, expected in report["evaluator_sources"].items())
            report["native_extensions_unchanged"] = all(digest(Path(path)) == expected
                                                        for path, expected in native_extensions.items())
            report["execution_completed"] = (report["source_unchanged"] and report["evaluator_unchanged"]
                                             and report["native_extensions_unchanged"])
            report["status"] = "COMPLETED" if report["execution_completed"] else "SOURCE_CHANGED"
    except KeyboardInterrupt:
        report["status"] = "INTERRUPTED"
        raise
    except BaseException as exc:
        report["status"] = "ERROR"
        report["fatal_error_type"] = type(exc).__name__
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
