"""Synthetic-only DB/search benchmark. Never opens the application's database.

Each implementation runs in a fresh child process. Model calls are deterministic
stubs: timings measure local data/search work, not inference or HTTP latency.
"""

import argparse
import cProfile
import hashlib
import importlib.util
import json
import os
import pstats
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pma.facts import FACT_VERSION, project  # noqa: E402
from pma.service import Service  # noqa: E402
from pma.store import Store  # noqa: E402


def seed(path, count, dimensions=1024):
    if path.exists():
        raise FileExistsError(path)
    store = Store(path)
    rng = np.random.default_rng(20261019)
    text = "2026년 10월 12일 제주에 여행을 갔다."
    memory = dict(content=text, subject={"kind": "self"}, predicate="여행을 갔다",
                  object={"value": "제주"}, target="", memory_type="event",
                  assertion_polarity="affirmed", evidence=[{"quote": text}],
                  time=dict(raw="2026년 10월 12일", start="2026-10-12", end="2026-10-12",
                            precision="day", certainty="certain"))
    fact = project(memory, text, "2026-10-19", "2026-10-19")
    with store.connect(True) as db:
        for index in range(count):
            rid, vid, jid, mid = (f"{prefix}{index:08d}" for prefix in "rvjm")
            stamp = "2026-10-19T00:00:00+00:00"
            body = {**memory, "content": text + f" 합성 항목 {index:08d}"}
            derived = {**fact, "event_time": {**fact["event_time"],
                       "start": "2026-10-12" if index % 10 == 0 else "2025-01-01"}}
            vector = rng.normal(size=dimensions).astype("<f4").tobytes()
            db.execute("INSERT INTO records VALUES(?,1,'active','ready',?,?,NULL,NULL)",
                       (rid, stamp, stamp))
            db.execute("INSERT INTO revisions VALUES(?,?,1,?,?,?)", (vid, rid, text, None, stamp))
            db.execute("INSERT INTO jobs(id,revision_id,status,created_at,updated_at) "
                       "VALUES(?,?,'succeeded',?,?)", (jid, vid, stamp, stamp))
            db.execute("INSERT INTO memories VALUES(?,?,?,?,?)",
                       (mid, vid, jid, "0", json.dumps(body, ensure_ascii=False)))
            db.execute("INSERT INTO embeddings VALUES(?,?,?,?)", (mid, "synthetic", dimensions, vector))
            for position in range(1 + (index % 3 == 0)):
                db.execute("INSERT INTO evidence VALUES(?,?,?,?,?)", (mid, position, text, 0, len(text)))
            db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?)",
                       (mid, FACT_VERSION, "self", None, "제주", json.dumps(derived, ensure_ascii=False), mid))
            if index % 10 == 0:
                payload = json.dumps(dict(record_version=1,
                    lifecycle_status="archived" if index % 40 == 0 else "active"))
                db.execute("INSERT INTO captured_memories VALUES(?,?,?,?)",
                           (f"c{index}", "other" if index % 50 == 0 else "local-account", rid, payload))
        store.bump(db)
    return count


def load_baseline(directory):
    if directory is None:
        from evaluation.database_reference import Service, Store
        return Store, Service
    spec = importlib.util.spec_from_file_location("pma._db_keywords", directory / "search_explain_before.py")
    keywords = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(keywords)
    classes = []
    for filename, symbol in (("store_before.py", "Store"), ("service_before.py", "Service")):
        spec = importlib.util.spec_from_file_location("pma._db_" + symbol, directory / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if symbol == "Service":
            module.keyword_query = keywords.keyword_query
            module.keyword_matches = keywords.keyword_matches
        classes.append(getattr(module, symbol))
    return classes


def rss():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in
                ("peak", "working", "pool_peak", "pool", "nonpool_peak", "nonpool", "page", "page_peak")]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        data = Counters()
        data.cb = ctypes.sizeof(data)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(data), data.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return dict(rss_mib=data.working / 2**20, peak_rss_mib=data.peak / 2**20)
    import resource
    return dict(peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def digest(value):
    result = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                              default=lambda x: x.hex() if isinstance(x, bytes) else str(x))
    for part in encoder.iterencode(value):
        result.update(part.encode())
    return result.hexdigest()


def measure(call, samples):
    start = time.perf_counter()
    value = call()
    cold = time.perf_counter() - start
    times = []
    for _ in range(samples):
        start = time.perf_counter()
        value = call()
        times.append(time.perf_counter() - start)
    return value, dict(first_seconds=cold, median_seconds=statistics.median(times),
                       max_seconds=max(times), samples_seconds=times, **rss())


def profile(call):
    profiler = cProfile.Profile()
    profiler.runcall(call)
    stats = pstats.Stats(profiler)
    return sorted([
        dict(file=Path(key[0]).name, line=key[1], function=key[2], calls=value[1],
             self_seconds=value[2], cumulative_seconds=value[3])
        for key, value in stats.stats.items()], key=lambda x: -x["self_seconds"])[:25]


def stage_measurements(svc, samples):
    """Time existing stage boundaries without cProfile's per-call overhead."""
    namespace = svc._search.__globals__
    original = namespace["capture"]
    timings = []
    active = None
    started = 0
    stages = {}

    def boundary(method, *args, **kwargs):
        nonlocal active, started
        if method == "begin":
            current = time.perf_counter()
            if active is not None:
                stages[active] = stages.get(active, 0) + current - started
            active, started = str(args[0]), current
        return original(method, *args, **kwargs)

    svc._search("제주 여행", None, "2026-10-19")
    namespace["capture"] = boundary
    try:
        for _ in range(samples):
            stages, active = {}, None
            begin = time.perf_counter()
            result = svc._search("제주 여행", None, "2026-10-19")
            end = time.perf_counter()
            if active is not None:
                stages[active] = stages.get(active, 0) + end - started
            timings.append(dict(total_seconds=end - begin, stages=stages))
    finally:
        namespace["capture"] = original
    names = set().union(*(item["stages"] for item in timings))
    return dict(samples=timings, median_total_seconds=statistics.median(
        item["total_seconds"] for item in timings), stages_median_seconds={
            name: statistics.median(item["stages"].get(name, 0) for item in timings)
            for name in sorted(names)}, digest=digest(result), memory=rss(),
            retained_vector_bytes=(getattr(svc, "_vector_cache", None)[1].nbytes
                if getattr(svc, "_vector_cache", None) else 0))


def child(args):
    # Keep the original DB/cache benchmark reproducible after the optional C++
    # matcher is installed. Native matching has its own explicit comparison tool.
    os.environ["PMA_KEYWORD_BACKEND"] = "python"
    store_type, service_type = load_baseline(args.baseline) if args.mode == "baseline" else (Store, Service)
    store = store_type(args.db)
    models = SimpleNamespace(
        understand=lambda *a: dict(intent="recall", date_from=None, date_to=None),
        embed=lambda texts: [[1.] + [0.] * 1023 for _ in texts],
        select=lambda question, rows: [row["id"] for row in rows])
    svc = service_type(store, models, SimpleNamespace(embedding_key="synthetic", embedding_dimensions=1024))
    if args.mode == "batch":
        svc.vector_cache_bytes = 0
        # Isolate SQL tuning/batched evidence from both cache optimizations.
        keywords = load_baseline(args.baseline)[1]._search.__globals__
        import pma.service as service_module
        old = keywords["keyword_matches"]
        service_module.keyword_matches = lambda r, t, v, **kw: old(r, t, v)
        service_module.keyword_matches_batch = lambda rows, terms, vocabulary: [
            old(row, terms, vocabulary) for row in rows]
    if args.stage_only:
        print(json.dumps(stage_measurements(svc, args.samples)))
        return
    output = dict(mode=args.mode, database_bytes=args.db.stat().st_size, initial_memory=rss())
    (generation, rows), output["snapshot"] = measure(
        lambda: store.snapshot_for_owner("synthetic", "local-account"), args.samples)
    output["snapshot"]["rows"] = len(rows)
    output["snapshot"]["digest"] = digest(rows)
    # The scope below mirrors the original matrix preparation and stable top-k.
    from pma.models import normalized_vectors

    def vector():
        if args.mode == "baseline":
            matrix = normalized_vectors(np.stack([np.frombuffer(r["vector"], dtype="<f4")
                for r in rows]), len(rows), 1024)
        else:
            matrix = svc._candidate_matrix(generation, rows)
        scores = matrix @ np.array(models.embed([""])[0], dtype=np.float32)
        return np.argsort(-scores, kind="stable")[:20].tolist()

    ranking, output["vector"] = measure(vector, args.samples)
    output["vector"]["digest"] = digest(ranking)
    rows = None
    for label, filters in (("all", None), ("date_filtered", {"date_from": "2026-10-01", "date_to": "2026-10-31"})):
        result, output[label] = measure(lambda: svc._search("제주 여행", filters, "2026-10-19"), args.samples)
        output[label]["digest"] = digest(result)
        output[label]["results"] = len(result[1]["results"])
    svc._search("제주 여행", None, "2026-10-19")
    output["profile"] = profile(lambda: svc._search("제주 여행", None, "2026-10-19"))
    output["snapshot_profile"] = profile(lambda: store.snapshot_for_owner("synthetic", "local-account"))
    statements = []
    original_connect = store.connect

    @contextmanager
    def traced(*a, **kw):
        with original_connect(*a, **kw) as db:
            db.set_trace_callback(statements.append)
            yield db

    store.connect = traced
    store.snapshot_for_owner("synthetic", "local-account")
    store.connect = original_connect
    output["snapshot_sql_statements"] = len([sql for sql in statements if sql.startswith(("SELECT", "WITH"))])
    query = next(sql for sql in statements if "SELECT m.id,m.payload" in sql)
    with store.connect() as db:
        output["query_plan"] = [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + query)]
    output["final_memory"] = rss()
    print(json.dumps(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path,
                        help="Optional frozen pre-change source directory; otherwise use reference algorithms")
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 25000])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--mode", choices=["baseline", "batch", "cached"])
    parser.add_argument("--db", type=Path)
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    if args.samples < 1 or any(count < 1 for count in args.sizes):
        parser.error("sizes and samples must be positive")
    if args.mode:
        child(args)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    # Preserve exact pre-change sources as reviewable benchmark inputs.
    if args.baseline is not None:
        for name in ("store_before.py", "service_before.py", "search_explain_before.py"):
            (args.output / name).write_bytes((args.baseline / name).read_bytes())
    else:
        (args.output / "database_reference.py").write_bytes((ROOT / "evaluation/database_reference.py").read_bytes())
    sources = {}
    for name in ("pma/store.py", "pma/service.py", "pma/search_explain.py"):
        data = (ROOT / name).read_bytes()
        target = args.output / (Path(name).stem + "_after.py")
        target.write_bytes(data)
        sources[name] = hashlib.sha256(data).hexdigest()
    import platform
    import sqlite3
    (args.output / "manifest.json").write_text(json.dumps(dict(
        sources=sources, python=sys.version, numpy=np.__version__, sqlite=sqlite3.sqlite_version,
        platform=platform.platform(), samples=args.samples, sizes=args.sizes,
        models="deterministic stubs; no HTTP/inference", dimensions=1024,
        captures="10% captured; 2.5% archived; 2% other owner (overlapping)"), indent=2), encoding="utf-8")
    results = []
    for count in args.sizes:
        db = args.output / f"synthetic-{count}.db"
        seed(db, count)
        for mode in ("baseline", "batch", "cached"):
            command = [sys.executable, __file__, "--output", str(args.output),
                       "--mode", mode, "--db", str(db), "--samples", str(args.samples)]
            if args.baseline is not None:
                command.extend(["--baseline", str(args.output)])
            run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            if run.returncode:
                raise RuntimeError(run.stderr)
            value = json.loads(run.stdout)
            value["count"] = count
            results.append(value)
            (args.output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(count, mode, "snapshot", round(value["snapshot"]["median_seconds"], 4),
                  "search", round(value["all"]["median_seconds"], 4), flush=True)
    for count in args.sizes:
        subset = [r for r in results if r["count"] == count]
        for scope in ("snapshot", "vector", "all", "date_filtered"):
            assert len({r[scope]["digest"] for r in subset}) == 1, (count, scope, "RESULT_CHANGED")


if __name__ == "__main__":
    main()
