"""Real-model, synthetic-only stage tracing. Never opens the user's database."""

import argparse
import hashlib
import json
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from evaluation.relationship_checks import check_case
from pma.models import ANSWER_SCHEMA, LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store

ROOT = Path(__file__).resolve().parents[1]


class TracedModels(LocalModels):
    def extract(self, text, context):
        self.last_stage = "extraction"
        return super().extract(text, context)

    def embed(self, texts):
        self.last_stage = "embedding"
        return super().embed(texts)

    def understand(self, question, today):
        self.last_stage = "query_interpretation"
        result = super().understand(question, today)
        self.last_understanding = result
        return result

    def answer(self, question, evidence):
        self.last_stage = "answer_generation"
        self.last_evidence = evidence
        result = super().answer(question, evidence)
        self.last_answer = result
        return result

    def select(self, question, evidence):
        self.last_stage = "retrieval_selection"
        return super().select(question, evidence)

    def verify(self, question, evidence, items):
        self.last_stage = "answer_validation"
        return super().verify(question, evidence, items)


def run(dataset, output, cached_extractions=None):
    settings = AppSettings.from_env()
    models = TracedModels(settings)
    report = {
        "synthetic_only": True,
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "code_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                ROOT / "pma/models.py",
                ROOT / "pma/service.py",
                ROOT / "prompts/extraction.txt",
                ROOT / "pma/facts.py",
                ROOT / "pma/grounding.py",
            )
        },
        "embedding_revision": settings.embedding_revision,
        "records": [],
        "questions": [],
        "scenarios": [],
        "semantic_accuracy": None,
        "review_note": "Candidate hit is not answer correctness. Review each answer against expected.",
    }
    fixture = json.loads(dataset.read_text(encoding="utf-8"))
    if fixture.get("synthetic") is not True:
        raise ValueError("Only explicitly synthetic fixtures are accepted.")
    cached = {}
    if cached_extractions:
        old = json.loads(cached_extractions.read_text(encoding="utf-8"))
        if old.get("synthetic_only") is not True:
            raise ValueError("Synthetic cache required")
        # Reports generated before source snapshots were added can only reuse
        # the exact original diagnostic fixture verified by its content hash.
        originals = old.get("source_records")
        if originals is None:
            original_path = ROOT / "data/search_diagnostics.json"
            if old["dataset_sha256"] != hashlib.sha256(original_path.read_bytes()).hexdigest():
                raise ValueError("Cache source hash mismatch")
            originals = json.loads(original_path.read_text(encoding="utf-8"))["records"]
        original_map = {r["id"]: r for r in originals}
        current_map = {r["id"]: r for r in fixture["records"]}
        cached = {
            r["id"]: r["memories"]
            for r in old["records"]
            if r["status"] == "ready" and original_map.get(r["id"]) == current_map.get(r["id"])
        }
    report["source_records"] = fixture["records"]
    report["cached_extraction_ids"] = sorted(cached)
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="pma-diagnostic-") as directory:
        store = Store(Path(directory) / "memory.db")
        service = Service(store, models, replace(settings, data_dir=Path(directory)))
        source_ids = {}
        for record in fixture["records"]:
            rid = store.create(record["text"], record["reference_time"])["record_id"]
            source_ids[rid] = record["id"]
            if record["id"] in cached:
                job = store.claim()
                memories = cached[record["id"]]
                vectors = models.embed([m["content"] for m in memories])
                store.publish(
                    job, memories, vectors, settings.embedding_key, {"cached_extraction": True}
                )
            else:
                service.run_one()
            result = store.get(rid)
            report["records"].append(
                {
                    "id": record["id"],
                    "status": result["status"],
                    "memories": result["memories"],
                    "error_code": result["error_code"],
                    "failure_stage": models.last_stage if result["status"] == "failed" else None,
                }
            )
            save()
            print(
                f"record {record['id']}: {result['status']} ({len(result['memories'])})", flush=True
            )
        for case in fixture["questions"]:
            started = time.monotonic()
            models.last_understanding = None
            models.last_evidence = None
            models.last_answer = None
            entry = dict(case)
            try:
                answer = service.answer(case["question"], today=fixture["today"])
                entry["understood"] = models.last_understanding
                entry["response"] = answer
                entry["acceptance"] = check_case(case, answer, source_ids)
                hits = [source_ids[r["record_id"]] for r in answer["results"]]
                entry["retrieved_sources"] = hits
                entry["relevant_source_retrieved"] = bool(set(hits) & set(case["relevant"]))
                entry["unexpected_date_filter"] = not case["date_filter"] and any(
                    answer["filters"].values()
                )
                print(
                    f"question {case['id']}: {answer['status']} hits={','.join(dict.fromkeys(hits))}",
                    flush=True,
                )
            except Exception as exc:
                entry["error_type"] = type(exc).__name__
                entry["failure_stage"] = getattr(models, "last_stage", "unknown")
                entry["understood"] = models.last_understanding
                entry["answer_input"] = models.last_evidence
                entry["unvalidated_answer"] = models.last_answer
                # Application-owned codes only; never serialize arbitrary exception bodies.
                if str(exc) in {
                    "INVALID_CITATION",
                    "INVALID_ANSWER",
                    "INVALID_ANSWER_STATE",
                    "INVALID_MODEL_SCHEMA",
                    "MODEL_TRUNCATED",
                }:
                    entry["error_code"] = str(exc)
                print(f"question {case['id']}: {type(exc).__name__}", flush=True)
            entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
            report["questions"].append(entry)
            save()
        store.checkpoint()
        for index, scenario in enumerate(fixture.get("scenarios", [])):
            scenario_store = Store(Path(directory) / f"scenario-{index}.db")
            scenario_service = Service(scenario_store, models, settings)
            inserted = set()
            by_source = {r["id"]: r for r in fixture["records"]}
            extracted = {r["id"]: r for r in report["records"]}
            for stage in scenario["stages"]:
                for source_id in stage:
                    if source_id in inserted:
                        continue
                    source = by_source[source_id]
                    scenario_store.create(source["text"], source["reference_time"])
                    job = scenario_store.claim()
                    memories = extracted[source_id]["memories"]
                    scenario_store.publish(
                        job,
                        memories,
                        models.embed([m["content"] for m in memories]),
                        settings.embedding_key,
                        {"scenario": True},
                    )
                    inserted.add(source_id)
                response = scenario_service.answer(scenario["question"], today=fixture["today"])
                report["scenarios"].append(
                    {
                        "name": scenario["name"],
                        "stage": stage,
                        "expected": scenario["expected"],
                        "response": response,
                    }
                )
                save()
            scenario_store.checkpoint()


def probes(report_path, output):
    """Isolate answer behavior from ranking; optional instruction is experimental only."""
    baseline = json.loads(report_path.read_text(encoding="utf-8"))
    if baseline.get("synthetic_only") is not True:
        raise ValueError("Synthetic report required")
    records = {r["id"]: r for r in baseline["records"]}

    class GuidedModels(LocalModels):
        def structured(self, prompt, data, schema):
            if schema == ANSWER_SCHEMA:
                prompt += (
                    " 날짜를 묻는 질문에는 time.start의 정규화된 날짜를 사용하라. "
                    "싸우다와 다투다는 같은 경험을 가리킬 수 있다. "
                    "수량과 단위, 행동 주체, 완료 여부가 질문 조건과 일치하는지 먼저 대조하라. "
                    "4km와 5km는 다르다. 정확한 거리 질문에서 다른 거리를 긍정 근거로 쓰지 마라. "
                    "부산에서 무엇을 했는지 물으면 근거에 있는 부산 여행의 활동을 답하라."
                )
            return super().structured(prompt, data, schema)

    settings = AppSettings.from_env()
    result = []
    cases = [
        ("fight", "나 친구랑 싸웠었는데 언제였지"),
        ("run5", "나 4km 달린적 있나"),
        ("busan", "부산 가서 뭐했지"),
    ]
    for source, question in cases:
        evidence = [
            {
                "id": f"{source}-{i}",
                "record_id": source,
                "version": 1,
                "content": m["content"],
                "time": m["time"],
                "evidence": m["evidence"],
                "score": 1.0,
            }
            for i, m in enumerate(records[source]["memories"])
        ]
        for label, models in [
            ("isolated_baseline", LocalModels(settings)),
            ("isolated_guidance_experiment", GuidedModels(settings)),
        ]:
            entry = {"source": source, "question": question, "variant": label}
            try:
                entry["response"] = models.answer(question, evidence)
            except Exception as exc:
                entry["error_type"] = type(exc).__name__
            result.append(entry)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"probe {source} {label} finished", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/search_diagnostics.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output/search_diagnostics.json")
    parser.add_argument("--probe-report", type=Path)
    parser.add_argument("--cached-extractions", type=Path)
    args = parser.parse_args()
    if args.probe_report:
        if args.output.resolve() == args.probe_report.resolve():
            parser.error("Probe output must differ from the baseline report")
        probes(args.probe_report, args.output)
    else:
        run(args.dataset, args.output, args.cached_extractions)


if __name__ == "__main__":
    main()
