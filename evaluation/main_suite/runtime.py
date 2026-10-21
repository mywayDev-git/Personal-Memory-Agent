"""Disposable real product adapters. Servers are owned by this invocation only."""

import hashlib
import json
import os
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import requests

from config.settings import Settings
from pma.chat.engine import ChatEngine
from pma.chat.store import ChatStore
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store

NOW = "2026-10-20T10:00:00+09:00"


def cancel_point(cancelled):
    if cancelled is not None and cancelled():
        raise KeyboardInterrupt("EVALUATION_CANCELLED")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_root(path):
    """Only a dedicated workspace .local subtree may contain synthetic databases."""
    workspace = Path(__file__).resolve().parents[2]
    allowed = (workspace / ".local/main-suite").resolve()
    original = Path(path).absolute()
    root = original.resolve()
    if not root.is_relative_to(allowed) or root == allowed:
        raise ValueError("OUTPUT_MUST_BE_A_RUN_UNDER_WORKSPACE_LOCAL_MAIN_SUITE")
    personal = AppSettings.from_env().data_dir.resolve()
    if root.is_relative_to(personal) or personal.is_relative_to(root):
        raise ValueError("PERSONAL_DATA_PATH_REJECTED")
    for parent in [original, *original.parents]:
        if parent.exists() and (parent.is_symlink() or parent.is_junction()):
            raise ValueError("OUTPUT_LINK_REJECTED")
        if parent == workspace:
            break
    return root


def model_specs(manifest, *, cancelled=None):
    required = {"path", "sha256", "context", "threads", "gpu_layers"}
    specs = {}
    for role in ("generation", "embedding"):
        values = manifest[role]
        if not values:
            raise ValueError("EMPTY_MODEL_REGISTRY")
        for name, spec in values.items():
            cancel_point(cancelled)
            if not name or "--" in name or not name.replace("-", "").replace("_", "").isalnum():
                raise ValueError("INVALID_MODEL_NAME")
            if not required <= spec.keys():
                raise ValueError("INCOMPLETE_MODEL_SPEC")
            path = Path(spec["path"]).resolve(strict=True)
            actual = digest(path)
            if spec["sha256"] and actual != spec["sha256"]:
                raise ValueError("MODEL_HASH_MISMATCH")
            if not spec["sha256"] and name != "baseline":
                raise ValueError("ADDITIONAL_MODEL_REQUIRES_PINNED_HASH")
            if spec["context"] < 1024 or spec["threads"] < 0 or spec["gpu_layers"] < 0:
                raise ValueError("INVALID_MODEL_SETTINGS")
            specs[role, name] = {**spec, "path": str(path), "sha256": actual}
    return specs


@contextmanager
def servers(server, generation, embedding, root, *, port=18481, cancelled=None):
    processes, handles = [], []
    cancel_point(cancelled)
    # Fail on occupied ports; never reuse or terminate an ordinary server.
    for number in (port, port + 1):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", number))
    try:
        for index, spec in enumerate((generation, embedding)):
            cancel_point(cancelled)
            command = [str(server), "-m", spec["path"], "--host", "127.0.0.1",
                       "--port", str(port + index), "--alias", "main-generation" if index == 0 else "main-embedding",
                       "-c", str(spec["context"]), "-ngl", str(spec["gpu_layers"]),
                       "--log-disable", "-np", "1"]
            if spec["threads"]:
                command += ["-t", str(spec["threads"])]
            if index:
                command += ["--embedding", "--pooling", spec["pooling"], "--embd-normalize", "2"]
            handle = (root / f"server-{index}.log").open("a", encoding="utf-8")
            handles.append(handle)
            process = subprocess.Popen(command, stdout=handle, stderr=handle,
                                       creationflags=0x08000000 if os.name == "nt" else 0)
            processes.append(process)
            deadline = time.monotonic() + 300
            with requests.Session() as client:
                client.trust_env = False
                while True:
                    cancel_point(cancelled)
                    if process.poll() is not None:
                        raise RuntimeError("EVALUATION_MODEL_SERVER_EXITED")
                    try:
                        if client.get(f"http://127.0.0.1:{port + index}/health", timeout=2).ok:
                            break
                    except requests.RequestException:
                        pass
                    if time.monotonic() >= deadline:
                        raise TimeoutError("EVALUATION_MODEL_STARTUP_TIMEOUT")
                    time.sleep(.3)
        llm = Settings(endpoint=f"http://127.0.0.1:{port}/v1/chat/completions",
                       model="main-generation", temperature=0, seed=42)
        settings = AppSettings(data_dir=root, llm=llm, context_tokens=generation["context"],
                               embedding_endpoint=f"http://127.0.0.1:{port+1}/v1/embeddings",
                               embedding_model="main-embedding", embedding_revision=embedding["sha256"],
                               embedding_dimensions=embedding["dimensions"],
                               embedding_profile=embedding["profile"], answer_validation=True)
        settings.validate()
        yield settings, processes
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for handle in handles:
            handle.close()


def owner_probe(store):
    from pma.errors import AppError

    sessions = {}
    for owner in ("user-a", "user-b", "user-c"):
        sessions[owner] = ChatStore(store, owner).create_empty()["id"]
    checks, exposures = [], 0
    for viewer, sid in sessions.items():
        for owner in sessions:
            try:
                ChatStore(store, owner).get(sid)
                checks.append(owner == viewer)
                exposures += owner != viewer
            except AppError as exc:
                checks.append(owner != viewer and exc.code == "NOT_FOUND")
    return {"passed": all(checks), "checks": checks, "security_exposures": exposures,
            "scope": "internal_owner_sessions_only"}


def import_probe(store, case):
    from pma.imports import TextImporter

    text = case["records"][0]["text"]
    importer = TextImporter(store)
    preview = importer.preview("synthetic.md", text)
    first = importer.commit(preview["import_id"], "synthetic-import")
    second = importer.commit(preview["import_id"], "synthetic-import")
    parts = preview["chunks"]
    return {"passed": first == second and "".join(p["text"] for p in parts) == text
            and all(text[p["start"]:p["end"]] == p["text"] for p in parts),
            "chunks": len(parts), "result": first}


def execute(case, settings, directory, *, seed_template=None, cancelled=None):
    partial = {"events": [], "steps": [], "phase": "initialization"}
    try:
        return _execute(case, settings, directory, seed_template=seed_template,
                        cancelled=cancelled, partial=partial)
    except Exception as exc:
        from scripts.memory_agent.diagnostics import failure
        exc.evaluation_observation = {**partial, "failure": failure(exc, partial["phase"])[1]}
        raise


def record_snapshot(store):
    """All rows, including trash, so a create-then-trash still counts as a write."""
    with store.connect() as db:
        return [tuple(row) for row in db.execute("SELECT id,version,state FROM records ORDER BY id")]


def run_indexing(service, store, record_id):
    service.run_one()
    record = store.get(record_id)
    job = store.job(record["job_id"])
    if job["status"] != "succeeded":
        from scripts.memory_agent.diagnostics import ProcessingError
        with store.connect() as db:
            diagnostic = db.execute("SELECT metadata FROM jobs WHERE id=?", (record["job_id"],)).fetchone()[0]
        raise ProcessingError(job.get("error_code") or "EXTRACTION_FAILED", "extract",
                              job_diagnostic=json.loads(diagnostic) if diagnostic else None)


def _execute(case, settings, directory, *, seed_template=None, cancelled=None, partial):
    """Run real extraction first; a new DB is used for every case/attempt."""
    from pma.web import RecordInput
    from scripts.memory_agent.llm_client import request_budget
    from scripts.memory_agent.performance import profile_request

    from .sources import resolve_sources

    cancel_point(cancelled)
    case = resolve_sources(case)
    if case["adapter"] == "contract_tests":
        from .contract_runner import execute_contract_tests
        return execute_contract_tests(case["behavior_contract"], directory, cancelled)
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "synthetic.db"
    if seed_template is not None:
        import shutil
        shutil.copy2(seed_template[0], path)
    store = Store(path, clock=lambda: NOW)
    if case["adapter"] == "contract_probe":
        from .contract_probes import execute_contract
        return execute_contract(store, case["input_contract"])
    if case["adapter"] == "owner_probe":
        return {"probe": owner_probe(store)}
    if case["adapter"] == "import_probe":
        return {"probe": import_probe(store, case)}
    events = partial["events"]
    partial["phase"] = "extraction"
    settings = replace(settings, data_dir=directory)
    service = Service(store, LocalModels(settings), settings, diagnostic_sink=events.append)
    if case["adapter"] == "fault_probe":
        from unittest.mock import patch
        created = store.create("PMA에서 캐시 검증을 완료했다.", NOW)
        # Actual extraction, followed by an injected embedding transport failure.
        with patch.object(service.models, "embed", side_effect=requests.ConnectionError("synthetic fault")):
            service.run_one()
        failed = store.job(created["job_id"])["status"] == "failed"
        with store.connect() as db:
            count = db.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        store.retry(created["record_id"])
        service.run_one()
        recovered = store.get(created["record_id"])["status"] == "ready"
        return {"probe": {"passed": failed and count == 0 and recovered,
                           "fault": "embedding_connection_failure", "recovered": recovered,
                           "model_accuracy_sample": False}}
    ids = dict(seed_template[1]) if seed_template else {}
    started = time.perf_counter()
    records = case["records"]
    if case.get("corpus_size"):
        records = records + [{"id": f"noise-{i}", "text": f"합성 프로젝트 번호 {i}의 방문 장소는 도서관이다.",
                              "version": 1, "owner": "user-a"} for i in range(case["corpus_size"]-len(records))]
    for record in records:
        cancel_point(cancelled)
        if seed_template:
            break
        # Other synthetic owners are never injected into a single-user search scope.
        if record["owner"] != "user-a":
            continue
        data = RecordInput(text=record.get("initial_text", record["text"]), reference_time=NOW)
        result = store.create(data.text, data.reference_time)
        ids[record["id"]] = result["record_id"]
        with request_budget(360):
            run_indexing(service, store, result["record_id"])
    indexing_ms = (time.perf_counter() - started) * 1000
    # Re-embed a shared real extraction seed for a different embedding candidate.
    if seed_template:
        import numpy as np
        with store.connect() as db:
            memories = db.execute("SELECT id,payload FROM memories ORDER BY id").fetchall()
        vectors = service.models.embed([json.loads(m["payload"])["content"] for m in memories]) if memories else []
        with store.connect(True) as db:
            db.execute("DELETE FROM embeddings")
            for memory, vector in zip(memories, vectors, strict=True):
                db.execute("INSERT INTO embeddings VALUES(?,?,?,?)", (memory["id"], settings.embedding_key,
                           settings.embedding_dimensions, np.asarray(vector, dtype="<f4").tobytes()))
            store.bump(db)
    # A checkpointed copy before user mutations is suitable only for retrieval ablation.
    store.checkpoint()
    import shutil
    shutil.copy2(path, directory / "extraction-seed.db")
    engine = ChatEngine(service)
    sid = engine.store.create_empty()["id"]
    response, step_results = {}, partial["steps"]
    final_event_start = len(events)
    before_chat = record_snapshot(store)
    partial["phase"] = "steps"
    query_started = time.perf_counter()
    with request_budget(360), profile_request() as profile:
        for index, step in enumerate(case["steps"]):
            cancel_point(cancelled)
            action = step["action"]
            partial["phase"] = action
            event_start = len(events)
            t0 = time.perf_counter()
            if action == "delete":
                store.trash(ids[step["record"]])
            elif action == "restore":
                store.restore(ids[step["record"]])
                run_indexing(service, store, ids[step["record"]])
            elif action == "update":
                current = store.get(ids[step["record"]])
                store.update(ids[step["record"]], current["version"], step["text"], NOW)
                run_indexing(service, store, ids[step["record"]])
            elif action == "new_session":
                sid = engine.store.create_empty()["id"]
            elif action in {"capture", "assert_no_capture"}:
                from pma.memory.api import OWNER, natural_candidates
                from pma.memory.repository import MemoryRepository
                last = engine.store.get(sid)["messages"][-1]
                candidates = natural_candidates(store, sid, last["id"], last["question"], "general")
                if action == "assert_no_capture":
                    if candidates or record_snapshot(store) != before_chat:
                        raise RuntimeError("F-MEMORY:NONCONSENSUAL_CAPTURE")
                else:
                    if not candidates:
                        raise RuntimeError("F-MEMORY:EXPLICIT_CAPTURE_MISSING")
                    candidate = next(c for c in candidates if c["source_type"] == "user_message")
                    saved = MemoryRepository(store).commit(OWNER, candidate["candidate_id"],
                        approved=step["approved"], request_id="main-capture")
                    run_indexing(service, store, saved["record_id"])
                    ids["captured"] = saved["record_id"]
            elif action == "search":
                final_event_start = event_start
                response = engine.search(step["question"], filters=step.get("filters"), today=NOW[:10])
            elif action == "chat":
                before_chat = record_snapshot(store)
                final_event_start = event_start
                response = engine.message(sid, f"main-{index}", step["question"], today=NOW[:10],
                                          mode=step.get("mode", "auto"), filters=step.get("filters"))
            elif action in {"concurrent_search", "concurrent_write", "concurrent_delete"}:
                from concurrent.futures import ThreadPoolExecutor
                def search():
                    with request_budget(360):
                        return service.search(step["question"], today=NOW[:10])
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first = pool.submit(search)
                    if action == "concurrent_search":
                        second = pool.submit(search)
                        response = {"status": "answered", "items": []}
                        found = [first.result(), second.result()]
                        if [{r["record_id"] for r in item["results"]} for item in found][0] != {r["record_id"] for r in found[1]["results"]}:
                            raise RuntimeError("F-STATE:CONCURRENT_SEARCH_INCONSISTENT")
                    elif action == "concurrent_write":
                        store.create("합성 동시 저장 작업을 대기열에 넣었다.", NOW)
                        first.result()
                    else:
                        store.trash(ids["target"])
                        try:
                            first.result()
                        except Exception as exc:
                            if getattr(exc, "code", None) not in {"SOURCE_CHANGED", "DATA_CHANGED"}:
                                raise
                        later = search()
                        if any(r["record_id"] == ids["target"] for r in later["results"]):
                            raise RuntimeError("F-SECURITY:DELETED_RESULT_EXPOSED")
                # Report concurrency invariants independently of answer accuracy.
                return {"probe": {"passed": True, "scope": action, "model_accuracy_sample": False},
                        "events": events, "indexing_ms": indexing_ms}
            else:
                raise ValueError("UNSUPPORTED_TEST_ACTION:" + action)
            step_results.append({"action": action, "response": response,
                                 "event_start": event_start, "event_end": len(events),
                                 "latency_ms": (time.perf_counter() - t0) * 1000})
    query_ms = (time.perf_counter() - query_started) * 1000
    sources = {}
    for logical_id, rid in ids.items():
        source = store.get(rid)
        sources[rid] = {"logical_id": logical_id, "text": source["text"],
                        "version": source["version"], "state": source["state"]}
    retrieval_events = [e for e in events if e["stage"] == "retrieval_merge"]
    final_query_events = []
    # Do not count evidence from an earlier turn as retrieval for the final question.
    final_query_events = [e for e in events[final_event_start:] if e["stage"] == "retrieval_merge"]
    memory_to_logical = {}
    memory_sources = {}
    with store.connect() as db:
        for row in db.execute("SELECT m.id,r.record_id,r.version,r.id AS revision_id FROM memories m JOIN revisions r ON m.revision_id=r.id"):
            if row["record_id"] in sources:
                memory_to_logical[row["id"]] = sources[row["record_id"]]["logical_id"]
                memory_sources[row["id"]] = {"record_id": row["record_id"], "version": row["version"], "revision_id": row["revision_id"]}
    retrieval_batches = [[memory_to_logical[c["id"]] for c in e["candidates"]
                          if c["id"] in memory_to_logical] for e in final_query_events]
    retrieved = retrieval_batches[-1] if retrieval_batches else []
    extracted_facts = {}
    current_record = None
    for event in events:
        if event['stage'] == 'processing_start':
            current_record = event.get('record_id')
            if current_record in sources:
                extracted_facts[sources[current_record]['logical_id']] = ''
        elif event['stage'] == 'embedding_start' and current_record in sources:
            logical = sources[current_record]['logical_id']
            extracted_facts[logical] = extracted_facts.get(logical, '') + json.dumps([
                {k:v for k,v in memory.items() if k != 'evidence'} for memory in event.get('memories', [])], ensure_ascii=False)
    return {"response": response, "sources": sources, "memory_sources": memory_sources, "retrieved": retrieved,
            "retrieval_observed": bool(final_query_events), "retrieval_batches": retrieval_batches, "extracted_facts": extracted_facts,
            "retrieval_ranking_policy": "last_search_batch_source_deduplicated", "events": events,
            "latency_ms": query_ms, "indexing_ms": indexing_ms, "steps": step_results,
            "performance": profile.snapshot(), "seed": [str(directory / "extraction-seed.db"), ids],
            "retrieval_event_count": len(retrieval_events)}
