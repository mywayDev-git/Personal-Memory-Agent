"""Compare current optimized Python matching to the C++ prototype, synthetic only."""

import argparse
import importlib.util
import json
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from evaluation.database_benchmark import digest, rss, seed, stage_measurements
from pma.search_explain import TOKEN, keyword_query, normalize
from pma.search_explain import python_keyword_matches_batch as keyword_matches_batch
from pma.service import Service
from pma.store import Store


def native(path):
    name = "_keyword_native_expressions" if path.name.startswith("_keyword_native_expressions") else "_keyword_native"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return lambda rows, terms, vocabulary: module.match_batch(rows, terms, vocabulary, normalize)


def quality(matcher):
    rng = random.Random(20261019)
    words = ["제주에", "갔다", "여행은", "취소하지", "않았다", "고양이", "수", "밤", "API",
             "Straße", "STRASSE", "İ", "ı", "K", "ＡＰＩ", "a_b", "²", "Ⅲ", "½", "e\u0301",
             "😀", "\ud800", "𐐀", "𐐨", "민수에게", "선물하지", "에서부터", "서울숲", "0001"]
    questions = ["제주 여행", "취소하지 않았다", "고양이 수 밤 api", "strasse İ K", "민수 선물", "수 있나요", "ＡＰＩ ² Ⅲ", "𐐨 a_b"]
    batches = 0
    for case in range(160):
        texts = ["".join(rng.choice(words + [" ", "!", "-", "\n", "\u200d"]) for _ in range(30))
                 for _ in range(8)]
        if case % 4 == 0:
            texts.append("".join(chr(rng.randrange(0x110000)) for _ in range(200)))
        rows = [{"text": t, "memory": {"content": t[::-1] if case % 2 else t}} for t in texts]
        question = questions[case % len(questions)]
        terms, vocabulary = keyword_query(question, rows)
        expected = keyword_matches_batch(rows, terms, vocabulary)
        actual = matcher(rows, terms, vocabulary)
        assert actual == expected, ("MATCH_CHANGED", case)
        for row, matches in zip(rows, actual, strict=True):
            for match in matches:
                text = row["text"] if match["field"] == "source_text" else row["memory"]["content"]
                assert text[match["start"]:match["end"]] == match["quote"]
        batches += 1
    # Cross the bounded-cache limit, then repeat early tokens with another query.
    rows = [{"text": " ".join(f"단어{i}" for i in range(17000)) + " 제주에 제주",
             "memory": {"content": "😀 제주에 갔다. 취소하지 않았다."}}]
    terms, vocabulary = keyword_query("제주 여행 취소하지", rows)
    assert matcher(rows, terms, vocabulary) == keyword_matches_batch(rows, terms, vocabulary)
    assert matcher([], terms, vocabulary) == []
    assert matcher(rows, [], vocabulary) == [[]]
    # Cover every CPython Unicode code point, including surrogates, using all
    # reference word runs as exact terms so token-boundary differences surface.
    text = "".join(chr(i) for i in range(0x110000))
    tokens = TOKEN.findall(text)
    terms = [{"text": token.casefold(), "normalized": normalize(token, set())} for token in tokens]
    rows = [{"text": text, "memory": {"content": ""}}]
    assert matcher(rows, terms, set()) == keyword_matches_batch(rows, terms, set())
    return dict(random_batches=batches, randomized_rows=1320, cache_limit_crossing=True,
                empty_input=True, unicode_offsets=True, exact_output_equality=True,
                unicode_codepoints=0x110000, unicode_word_runs=len(tokens))


def measurements(call, samples):
    start = time.perf_counter()
    value = call()
    first = time.perf_counter() - start
    values = []
    for _ in range(samples):
        start = time.perf_counter()
        value = call()
        values.append(time.perf_counter() - start)
    return value, dict(first_seconds=first, median_seconds=statistics.median(values),
                       max_seconds=max(values), samples_seconds=values, memory=rss())


def paired_measurements(db, extension, samples):
    """Alternate order on one service to check process/order sensitivity."""
    import pma.service as module
    matchers = {"python": keyword_matches_batch, "cpp": native(extension)}
    models = SimpleNamespace(
        understand=lambda *a: dict(intent="recall", date_from=None, date_to=None),
        embed=lambda texts: [[1.] + [0.] * 1023 for _ in texts],
        select=lambda q, rows: [row["id"] for row in rows])
    svc = Service(Store(db), models, SimpleNamespace(embedding_key="synthetic", embedding_dimensions=1024))
    original = module.keyword_matches_batch
    results = []
    try:
        for mode in ("python", "cpp"):
            module.keyword_matches_batch = matchers[mode]
            svc._search("제주 여행", None, "2026-10-19")
        for iteration in range(samples):
            order = ("python", "cpp") if iteration % 2 == 0 else ("cpp", "python")
            for mode in order:
                module.keyword_matches_batch = matchers[mode]
                start = time.perf_counter()
                found = svc._search("제주 여행", None, "2026-10-19")
                elapsed = time.perf_counter() - start
                results.append(dict(iteration=iteration, mode=mode, seconds=elapsed,
                                    digest=digest(found), memory=rss()))
    finally:
        module.keyword_matches_batch = original
    assert len({item["digest"] for item in results}) == 1
    return results


def child(args):
    matcher = native(args.extension) if args.mode == "cpp" else keyword_matches_batch
    if args.mode == "quality":
        print(json.dumps(quality(native(args.extension))))
        return
    store = Store(args.db)
    output = dict(mode=args.mode, initial_memory=rss())
    if args.scope == "matching":
        _, rows = store.snapshot_for_owner("synthetic", "local-account")
        for label, question in (("normal", "제주 여행"), ("many_terms", "제주 여행 취소하지 않았다 api 고양이 수 밤")):
            terms, vocabulary = keyword_query(question, rows)
            found, output[label] = measurements(lambda: matcher(rows, terms, vocabulary), args.samples)
            output[label]["digest"] = digest(found)
            output[label]["rows"] = len(rows)
            output[label]["hits"] = sum(map(len, found))
    else:
        import pma.service as module
        module.keyword_matches_batch = matcher
        models = SimpleNamespace(
            understand=lambda *a: dict(intent="recall", date_from=None, date_to=None),
            embed=lambda texts: [[1.] + [0.] * 1023 for _ in texts],
            select=lambda q, rows: [row["id"] for row in rows])
        svc = Service(store, models, SimpleNamespace(embedding_key="synthetic", embedding_dimensions=1024))
        for label, filters in (("all", None), ("date_filtered", {"date_from": "2026-10-01", "date_to": "2026-10-31"})):
            found, output[label] = measurements(lambda: svc._search("제주 여행", filters, "2026-10-19"), args.samples)
            output[label]["digest"] = digest(found)
        output["stages"] = stage_measurements(svc, args.samples)
    print(json.dumps(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--mode", choices=["python", "cpp", "quality"])
    parser.add_argument("--scope", choices=["matching", "search"])
    parser.add_argument("--db", type=Path)
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000, 25000])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--paired-only", action="store_true")
    args = parser.parse_args()
    if args.samples < 1 or any(size < 1 for size in args.sizes):
        parser.error("sizes and samples must be positive")
    if args.paired_only:
        if args.db is None:
            parser.error("--paired-only requires --db")
        print(json.dumps(paired_measurements(args.db, args.extension, args.samples)))
        return
    if args.mode:
        child(args)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    result = dict(quality=quality(native(args.extension)), comparisons=[], criteria=dict(
        matching_median_reduction_at_least=0.20, search_median_reduction_at_least=0.10,
        max_peak_memory_increase_mib=10, exact_equality_required=True))
    for count in args.sizes:
        db = args.output / f"synthetic-{count}.db"
        seed(db, count)
        for scope in ("matching", "search"):
            for mode in ("python", "cpp"):
                command = [sys.executable, "-m", "evaluation.native_keyword_benchmark", "--output", str(args.output),
                           "--extension", str(args.extension), "--mode", mode, "--scope", scope,
                           "--db", str(db), "--samples", str(args.samples)]
                run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                     env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                if run.returncode:
                    raise RuntimeError(run.stderr)
                row = json.loads(run.stdout)
                row.update(count=count, scope=scope)
                result["comparisons"].append(row)
                (args.output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(count, scope, mode, flush=True)
    for count in args.sizes:
        for scope, labels in (("matching", ("normal", "many_terms")), ("search", ("all", "date_filtered"))):
            pair = [r for r in result["comparisons"] if r["count"] == count and r["scope"] == scope]
            for label in labels:
                assert pair[0][label]["digest"] == pair[1][label]["digest"], (count, scope, label)
    result["paired_largest"] = paired_measurements(
        args.output / f"synthetic-{max(args.sizes)}.db", args.extension, args.samples)
    (args.output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
