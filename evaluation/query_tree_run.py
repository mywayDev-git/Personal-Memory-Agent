"""Serial isolated experiments: python -m evaluation.query_tree_run --help."""

import argparse
import copy
import csv
import hashlib
import html
import json
import random
import sqlite3
import tempfile
import time
from collections import defaultdict
from contextlib import ExitStack, closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from evaluation.kiwi_compare import model_identity
from evaluation.kiwi_runtime import Meter
from evaluation.query_paired import ARMS, PairedIndex
from evaluation.query_tree import Index, analyze, coverage, digest, instrumented_service, pack
from pma.grounding import claims_supported
from pma.models import ANSWER_SCHEMA, LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.validator import schema_errors

ROOT = Path("output/query-tree-v1")
DATA = Path("data/query_tree_cases.json")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class Embeddings:
    def __init__(self, path, model):
        self.model = model
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, value BLOB)")
        self.original = model.embed

    def __call__(self, texts):
        if not texts:
            return np.empty((0, self.model.settings.embedding_dimensions), dtype=np.float32)
        keys = [digest([self.model.settings.embedding_key, t]) for t in texts]
        cached = {
            k: row[0]
            for k in set(keys)
            if (row := self.db.execute("SELECT value FROM cache WHERE key=?", (k,)).fetchone())
        }
        pending = dict((k, t) for k, t in zip(keys, texts, strict=True) if k not in cached)
        pending = list(pending.items())
        for start in range(0, len(pending), 32):
            batch = pending[start : start + 32]
            vectors = self.original([t for _, t in batch])
            for (key, _), vec in zip(batch, vectors, strict=True):
                cached[key] = np.asarray(vec, dtype="<f4").tobytes()
                self.db.execute("INSERT OR REPLACE INTO cache VALUES(?,?)", (key, cached[key]))
            self.db.commit()
        return np.stack([np.frombuffer(cached[k], dtype="<f4") for k in keys])


def prepare(case, models, settings, cache, memory_source="extracted", trace_extraction=False):
    if memory_source == "reference":
        return copy.deepcopy(case["reference_memories"])
    old = Path("output/answer-validation-v1/prepared") / f"{case['id']}.json"
    if case["cohort"] == "regression":
        prior = read(old)
        # Reuse raw extractions, never the prior answer as ground truth.
        return [
            [
                dict(r["memory"], _evidence_spans=r["evidence"])
                for r in prior["memories"]
                if r["text"] == record["text"]
            ]
            for record in case["records"]
        ]
    values = []
    for record in case["records"]:
        key = digest([record, settings.embedding_key, vars(settings.llm)])
        dest = cache / f"{key}.json"
        if dest.exists():
            values.append(read(dest)["memories"])
            continue
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            store = Store(Path(tmp) / "extract.db")
            item = store.create(record["text"], record["reference_time"])
            if trace_extraction:
                from evaluation.validation_trace import ExtractionTrace

                with ExtractionTrace(models) as trace:
                    try:
                        Service(store, models, settings).run_one()
                    finally:
                        trace_path = cache / f"{key}.trace.json"
                        previous = read(trace_path).get("events", []) if trace_path.exists() else []
                        write(
                            trace_path,
                            dict(
                                record=record,
                                events=previous + [dict(stage="attempt")] + trace.events,
                            ),
                        )
            else:
                Service(store, models, settings).run_one()
            if store.get(item["record_id"])["status"] not in {"ready", "ready_empty"}:
                raise ValueError("EXTRACTION_FAILED")
            _, rows = store.snapshot(settings.embedding_key)
            memories = [dict(r["memory"], _evidence_spans=r["evidence"]) for r in rows]
            write(dest, dict(record=record, memories=memories))
            values.append(memories)
    return values


def distractors(count):
    records, memories = [], []
    for i in range(count):
        person = f"방해인물{i:04d}"
        text = f"2026-09-{i % 28 + 1:02d}에 {person}는 공부하면서 빵을 먹었다."
        records.append(dict(text=text, reference_time=None))
        memories.append(
            [
                dict(
                    local_id="m1",
                    content=text,
                    memory_type="event",
                    subject=dict(kind="entity", value=person, value_type="string"),
                    predicate="먹었다",
                    object=dict(kind="literal", value="빵", value_type="string"),
                    target=None,
                    time=dict(
                        raw=None, start=None, end=None, precision="unknown", certainty="uncertain"
                    ),
                    assertion_polarity="affirmed",
                    polarity="neutral",
                    content_certainty="explicit",
                    evidence=[dict(quote=text)],
                )
            ]
        )
    return records, memories


def populate(store, records, memories, embed, settings):
    record_numbers = {}
    for i, (record, raw) in enumerate(zip(records, memories, strict=True)):
        raw = copy.deepcopy(raw)
        created = store.create(record["text"], record["reference_time"])
        record_numbers[created["record_id"]] = i
        job = store.claim()
        provenance = []
        for m in raw:
            original_spans = m.pop("_evidence_spans", None)
            if original_spans is not None:
                provenance.append(dict(evidence=original_spans))
                continue
            spans = []
            cursor = 0
            for e in m["evidence"]:
                start = record["text"].find(e["quote"], cursor)
                if start < 0:
                    start = record["text"].index(e["quote"])
                spans.append(dict(quote=e["quote"], start=start, end=start + len(e["quote"])))
                cursor = start + len(e["quote"])
            provenance.append(dict(evidence=spans))
        store.publish(
            job,
            raw,
            embed([m["content"] for m in raw]),
            settings.embedding_key,
            {"provenance": provenance},
        )
    _, snapshot = store.snapshot(settings.embedding_key)
    rows = []
    for r in snapshot:
        m = r["memory"]
        rows.append(
            dict(
                m,
                id=r["id"],
                record_id=r["record_id"],
                record_no=record_numbers[r["record_id"]],
                version=r["version"],
                source_text=r["text"],
                reference_time=r["reference_time"],
                recorded_at=r["created_at"],
                evidence=r["evidence"],
                fact=r["fact"],
            )
        )
    return rows


def answer(models, question, nodes):
    trace = []
    if not nodes:
        return dict(status="insufficient_evidence", items=[]), trace
    try:
        response = models.answer(question, nodes)
        trace.append(dict(stage="draft", response=copy.deepcopy(response)))
        if schema_errors(response, ANSWER_SCHEMA):
            raise ValueError("ANSWER_SCHEMA")
        if (response["status"] == "answered") != bool(response["items"]):
            raise ValueError("ANSWER_STATE")
        allowed = {n["id"] for n in nodes}
        if any(set(i["citations"]) - allowed for i in response["items"]):
            raise ValueError("CITATIONS")
        if response["items"]:
            supported = claims_supported(response["items"], nodes) and models.verify(
                question, nodes, response["items"]
            )
            trace.append(dict(stage="verify", supported=supported))
            if not supported:
                return dict(status="insufficient_evidence", items=[]), trace
        return response, trace
    except Exception as exc:
        trace.append(dict(stage="error", error=type(exc).__name__))
        return dict(status="insufficient_evidence", items=[]), trace


def report(out):
    rows, details, failures = [], [], []
    reviews = read(out / "reviews.json") if (out / "reviews.json").exists() else []
    groups = defaultdict(list)
    for path in sorted(out.glob("results/*.json")):
        d = read(path)
        if d.get("status") != "complete":
            failures.append(
                dict(case=d["case"], scale=d["scale"], error=d.get("error"), detail=d.get("detail"))
            )
            continue
        for label, arm in d["arms"].items():
            metrics = arm["metrics"]["delivered"]
            reviewed = next(
                (
                    r
                    for r in reviews
                    if r["case"] == d["case"]
                    and r["scale"] == d["scale"]
                    and r["condition"] == label
                    and r["response_hash"] == digest(arm.get("response"))
                    and r.get("reason")
                    and r["judgment"]
                    in {
                        "correct",
                        "wrong",
                        "appropriate_abstention",
                        "excessive_abstention",
                        "needs_review",
                    }
                ),
                None,
            )
            row = dict(
                case=d["case"],
                split=d["split"],
                scale=d["scale"],
                condition=label,
                excluded=d["excluded"],
                **{
                    k: metrics[k] for k in ["recall", "precision", "all_required", "selected_nodes"]
                },
                seconds=arm["seconds"],
                candidate_all_required=arm["metrics"]["candidates"]["all_required"],
                selected_all_required=arm["metrics"]["selected"]["all_required"],
                analysis_status=(
                    "not_applied"
                    if d.get("suite") == "paired-v1" and label[1] == "0"
                    else d["analysis"]["status"]
                ),
                answer_judgment=reviewed["judgment"]
                if reviewed
                else "needs_review"
                if "response" in arm
                else "not_run",
            )
            rows.append(row)
            if not d["excluded"]:
                groups[(d["split"], d["scale"], label)].append(row)
        details.append(
            f"<details><summary>{html.escape(d['case'])} / scale {d['scale']}</summary><pre>{html.escape(json.dumps(d, ensure_ascii=False, indent=2))}</pre></details>"
        )
    if rows:
        with (out / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    costs = []
    for path in sorted(out.glob("results/*.json")):
        entry = read(path)
        stages = defaultdict(list)
        for call in entry.get("calls", []):
            stages[call["stage"]].append(call)
        for stage, calls in stages.items():
            costs.append(
                dict(
                    case=entry["case"],
                    scale=entry["scale"],
                    stage=stage,
                    calls=len(calls),
                    errors=sum(c["status"] != "ok" for c in calls),
                    prompt_tokens=sum(c.get("prompt_tokens") or 0 for c in calls),
                    completion_tokens=sum(c.get("completion_tokens") or 0 for c in calls),
                    usage_missing=sum(c.get("total_tokens") is None for c in calls),
                    seconds=sum(c["seconds"] for c in calls),
                )
            )
    if costs:
        with (out / "costs.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(costs[0]))
            writer.writeheader()
            writer.writerows(costs)
    summaries = []
    for (split, scale, label), values in sorted(groups.items()):
        summaries.append(
            dict(
                split=split,
                scale=scale,
                condition=label,
                cases=len(values),
                recall=float(np.mean([v["recall"] for v in values])),
                precision=float(np.mean([v["precision"] for v in values])),
                all_required=sum(v["all_required"] for v in values),
                candidate_all_required=sum(v["candidate_all_required"] for v in values),
                selected_all_required=sum(v["selected_all_required"] for v in values),
                analysis_fallback=sum(v["analysis_status"] == "fallback" for v in values),
                answer_judgments={
                    judgment: sum(v["answer_judgment"] == judgment for v in values)
                    for judgment in sorted({v["answer_judgment"] for v in values})
                },
                median_seconds=float(np.median([v["seconds"] for v in values])),
                p95_seconds=float(np.percentile([v["seconds"] for v in values], 95)),
            )
        )
    write(out / "summary.json", summaries)
    write(out / "failures.json", failures)
    (out / "diagnostics.jsonl").write_text(
        "\n".join(
            json.dumps(read(p), ensure_ascii=False) for p in sorted(out.glob("results/*.json"))
        )
        + "\n",
        encoding="utf-8",
    )
    page = "<!doctype html><html lang='ko'><meta charset='utf-8'><title>질문·트리 검색 실험</title><style>body{font:16px/1.6 system-ui;max-width:1200px;margin:32px auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f8;padding:12px}details{margin:12px}</style><h1>질문 분해·트리 검색 실험</h1><p>실험 후보, 운영 미적용. 검색 근거 회수율은 답변 정확도가 아닙니다. 답변은 원문 대조 검토 전까지 성공으로 계산하지 않습니다. 원문 구간 겹침 precision은 정확한 역할 일치의 대체 지표가 아닙니다.</p><pre>"
    page += (
        html.escape(json.dumps(summaries, ensure_ascii=False, indent=2))
        + "</pre>"
        + "".join(details)
        + "</html>"
    )
    table = "<h2>필수 근거 전체 포함 건수</h2><table border='1' cellpadding='6'><tr><th>구분</th><th>방해 기록</th><th>조건</th><th>사례</th><th>후보</th><th>선택</th><th>실제 전달</th></tr>"
    for s in summaries:
        table += (
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(s[k]))}</td>"
                for k in [
                    "split",
                    "scale",
                    "condition",
                    "cases",
                    "candidate_all_required",
                    "selected_all_required",
                    "all_required",
                ]
            )
            + "</tr>"
        )
    table += "</table><p>A 기존 검색 · B 의미 제외 제거 · C 질문 분해 · D 주제 트리 · E 원문 검색 · F 원문+문맥 확장</p>"
    table += f"<p>실행 실패 {len(failures)}건. 호출·토큰은 costs.csv, 원문 대조는 각 사례 진단을 확인하세요. 새 48개는 두 합성 원문을 공유하는 병렬 질문입니다. 답변 정확도와 질문 분석 의미 정확도는 아직 수동 검토가 필요합니다.</p>"
    page = page.replace("<pre>", table + "<pre>", 1)
    if (out / "manifest.json").exists() and read(out / "manifest.json").get("suite") == "paired-v1":
        page = page.replace("질문 분해·트리 검색 실험", "전체 질문 분해 8조건 비교")
        page = page.replace(
            "A 기존 검색 · B 의미 제외 제거 · C 질문 분해 · D 주제 트리 · E 원문 검색 · F 원문+문맥 확장",
            "V 벡터·키워드 · M 사실별 다중 벡터 · G 사건 그래프 단독 · H 혼합. "
            "0은 분해 미적용, 1은 모든 질문에 분해 시도. "
            "그래프는 이름·대상의 후보 연결이며 동일 인물·사건의 확정이나 완전한 그래프 패턴 매칭이 아닙니다. "
            "질문 분석 비용은 공통 단계로 측정하고 분해 적용 조건에만 귀속합니다. "
            "동일 질문·동일 답변 입력은 조건 사이에서 답변을 공유하며 재사용 출처를 기록합니다. "
            "벡터 캐시가 있는 실측 시간이며 검색 시간만으로 전체 지연을 비교하지 마세요.",
        )
    (out / "report.html").write_text(page, encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--phase", choices=["run", "report"], default="run")
    parser.add_argument("--tag", default="pilot-1")
    parser.add_argument(
        "--split", choices=["development", "holdout", "regression", "all"], default="development"
    )
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--scale", type=int, choices=[0, 100, 1000], default=0)
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--paired", action="store_true", help="Eight retrieval/decomposition pairs")
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--memory-source", choices=["extracted", "reference"], default="extracted")
    parser.add_argument("--trace-extraction", action="store_true")
    parser.add_argument(
        "--freeze-from", type=Path, help="Completed development run for new holdout"
    )
    args = parser.parse_args()
    if not re_safe_tag(args.tag):
        raise ValueError("INVALID_TAG")
    out = ROOT / args.tag
    if args.phase == "report":
        report(out)
        return
    cases = [
        c
        for c in read(args.data)
        if (not args.ids or c["id"] in args.ids)
        and (args.split == "all" or c["split"] == args.split)
    ]
    if not cases or (args.limit is not None and args.limit < 1):
        parser.error("No matching cases, or invalid limit; check --split and --ids.")
    validation = any(c.get("cohort") == "validation-v1" for c in cases)
    if validation and (not args.paired or args.scale or args.answers or args.split == "all"):
        parser.error("Validation requires --paired, one split, scale 0 and selective answers.")
    out.mkdir(parents=True, exist_ok=True)
    settings = AppSettings.from_env()
    settings = replace(
        settings,
        answer_validation=False,
        embedding_revision=read(Path("output/answer-validation-v1/final-1/fixed/manifest.json"))[
            "settings"
        ]["embedding"].split(":")[1],
    )
    settings = replace(settings, llm=replace(settings.llm, temperature=0, seed=42, top_p=1.0))
    if (
        settings.data_dir.resolve() == out.resolve()
        or settings.data_dir.resolve() in out.resolve().parents
    ):
        raise ValueError("PERSONAL_DB_OVERLAP")
    files = [
        p
        for folder in ["pma", "scripts", "config", "schema", "prompts"]
        for p in Path(folder).rglob("*")
        if p.is_file() and p.suffix in {".py", ".json", ".txt"}
    ]
    files += list(Path("evaluation").glob("query_tree*.py")) + [args.data]
    if validation:
        files += list(Path("evaluation").glob("*.py"))
    if args.paired:
        files += [Path("evaluation/query_paired.py")]
    files += list(Path("output/answer-validation-v1/prepared").glob("*.json"))
    identity = dict(
        files={p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        settings=dict(llm=vars(settings.llm), embedding=settings.embedding_key),
        models=model_identity(settings),
        answers=args.answers,
    )
    if args.paired:
        identity["suite"] = "paired-v1"
        identity["arms"] = ARMS
    if validation or args.data != DATA or args.memory_source != "extracted":
        identity["validation"] = dict(
            data=str(args.data),
            memory_source=args.memory_source,
            split=args.split,
            case_ids=[c["id"] for c in cases],
            trace_extraction=args.trace_extraction,
            interpretation="reference upper bound"
            if args.memory_source == "reference"
            else "extracted baseline",
        )
    if validation and args.split == "holdout":
        from evaluation.validation_audit import freeze_holdout

        freeze_holdout(args.freeze_from, out, identity, read(args.data))
    if (out / "manifest.json").exists() and read(out / "manifest.json") != identity:
        raise ValueError("RESUME_IDENTITY_MISMATCH")
    write(out / "manifest.json", identity)
    for p in files:
        target = out / "snapshot" / p
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(p.read_bytes())
    models = LocalModels(settings)
    cache = out / "extractions"
    cache.mkdir(exist_ok=True)
    embeddings = Embeddings(out / "vectors.sqlite", models)
    count = 0
    for case in cases:
        dest = out / "results" / f"{case['id']}--{args.scale}.json"
        if dest.exists() and read(dest).get("status") == "complete":
            continue
        if dest.exists():
            previous = read(dest)
            write(
                out / "attempts" / f"{case['id']}--{args.scale}--{digest(previous)}.json", previous
            )
        meter = Meter(models)
        started = time.perf_counter()
        entry = dict(
            case=case["id"],
            split=case["split"],
            excluded=case["excluded"],
            scale=args.scale,
            question=case["questions"][0]["text"],
            gold=case["gold"],
            expected=case.get("expected"),
            arms={},
        )
        try:
            with meter, patch.object(models, "embed", embeddings):
                meter.stage = "preparation"
                memories = prepare(
                    case, models, settings, cache, args.memory_source, args.trace_extraction
                )
                records = copy.deepcopy(case["records"])
                if args.scale:
                    extra_records, extra_memories = distractors(args.scale)
                    records += extra_records
                    memories += extra_memories
                with (
                    tempfile.TemporaryDirectory(dir=out, prefix="synthetic-") as tmp,
                    ExitStack() as stack,
                ):
                    store = Store(Path(tmp) / "memory.db")
                    rows = populate(store, records, memories, embeddings, settings)
                    meter.stage = "index"
                    index_start = time.perf_counter()
                    index_type = PairedIndex if args.paired else Index
                    index = stack.enter_context(
                        closing(
                            index_type(Path(tmp) / "tree.sqlite", models, rows, records, embeddings)
                        )
                    )
                    entry["index_seconds"] = time.perf_counter() - index_start
                    if args.paired:
                        entry["suite"] = "paired-v1"
                        entry["graph"] = {
                            "features": index.features,
                            "buckets": [
                                dict(kind=k[0], value=k[1], members=sorted(v))
                                for k, v in sorted(index.buckets.items())
                            ],
                            "identity_verified": False,
                        }
                        entry["multi_vector_fragments"] = index.fragments
                        meter.stage = "dense_index"
                        dense_start = time.perf_counter()
                        index.prepare_dense()
                        entry["dense_index_seconds"] = time.perf_counter() - dense_start
                        entry["vector_count"] = sum(len(v) for v in index.vectors.values())
                        entry["vector_bytes"] = sum(v.nbytes for v in index.vectors.values())
                    else:
                        entry["index_bytes"] = (Path(tmp) / "tree.sqlite").stat().st_size
                    entry["records"] = records
                    entry["frozen_memories"] = memories
                    entry["membership"] = index.membership
                    question = entry["question"]
                    meter.stage = "question_analysis"
                    analysis_start = time.perf_counter()
                    analysis = analyze(models, question)
                    entry["analysis"] = analysis
                    entry["analysis_seconds"] = time.perf_counter() - analysis_start
                    arm_order = list(ARMS) if args.paired else list("ABCDEF")
                    random.Random(42 + int(digest(case["id"])[:8], 16)).shuffle(arm_order)
                    entry["arm_order"] = arm_order
                    answer_cache = {}
                    for label in arm_order:
                        meter.stage = f"search-{label}"
                        arm_start = time.perf_counter()
                        if label == "A":
                            traces = []
                            service = instrumented_service()(
                                store, models, settings, diagnostic_sink=traces.append
                            )
                            _, found = service._search(question, today="2026-10-14")
                            nodes = [copy.deepcopy(index.nodes[r["id"]]) for r in found["results"]]
                            trace = dict(
                                baseline=traces,
                                status=found["status"],
                                selected=[n["id"] for n in nodes],
                            )
                            ranked_ids = next(
                                (t["ids"] for t in traces if t["stage"] == "ranked"), []
                            )[:24]
                        else:
                            nodes, trace = index.search(question, analysis, label)
                            ranked_ids = trace["candidates"]
                        selected_metrics = coverage(nodes, case["gold"])
                        candidate_metrics = coverage(
                            [index.nodes[k] for k in ranked_ids if k in index.nodes], case["gold"]
                        )
                        packed, dropped = pack(nodes, models, expanded=label == "F")
                        arm = dict(
                            trace=trace,
                            context_dropped=dropped,
                            selected=packed,
                            direct_selected=copy.deepcopy(nodes),
                            metrics=dict(
                                candidates=candidate_metrics,
                                selected=selected_metrics,
                                delivered=coverage(packed, case["gold"]),
                            ),
                            seconds=time.perf_counter() - arm_start,
                        )
                        if args.paired:
                            arm["analysis_seconds"] = (
                                entry["analysis_seconds"] if label[1] == "1" else 0
                            )
                            arm["search_with_analysis_seconds"] = (
                                arm["seconds"] + arm["analysis_seconds"]
                            )
                        if args.answers:
                            meter.stage = f"answer-{label}"
                            answer_key = digest([question, models.compact_evidence(packed)])
                            if args.paired and answer_key in answer_cache:
                                cached = answer_cache[answer_key]
                                arm["response"] = copy.deepcopy(cached["response"])
                                arm["answer_trace"] = copy.deepcopy(cached["trace"])
                                arm["answer_reused_from"] = cached["label"]
                                arm["answer_seconds"] = cached["seconds"]
                            else:
                                answer_start = time.perf_counter()
                                arm["response"], arm["answer_trace"] = answer(
                                    models, question, packed
                                )
                                arm["answer_seconds"] = time.perf_counter() - answer_start
                                if args.paired and not any(
                                    t["stage"] == "error" for t in arm["answer_trace"]
                                ):
                                    answer_cache[answer_key] = dict(
                                        response=arm["response"],
                                        trace=arm["answer_trace"],
                                        label=label,
                                        seconds=arm["answer_seconds"],
                                    )
                            arm["answer_judgment"] = "needs_review"
                        arm["total_seconds"] = time.perf_counter() - arm_start
                        entry["arms"][label] = arm
                    entry["status"] = "complete"
        except Exception as exc:
            entry.update(status="failed", error=type(exc).__name__, detail=str(exc))
        entry.update(calls=meter.calls, seconds=time.perf_counter() - started)
        write(dest, entry)
        print(
            case["id"],
            entry["status"],
            round(entry["seconds"], 2),
            entry.get("detail", ""),
            flush=True,
        )
        count += 1
        if args.limit and count >= args.limit:
            break
    embeddings.db.close()
    report(out)


def re_safe_tag(tag):
    import re

    return re.fullmatch(r"[A-Za-z0-9_-]+", tag) is not None


if __name__ == "__main__":
    main()
