"""Summarize explicit real-model trials without starting models or opening databases."""

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

from evaluation.latency_bottlenecks import analyze


def signature(artifact, search):
    response = artifact["response"]
    if search:
        return [(r["id"], r["record_id"], r["version"], r["evidence"])
                for r in response["results"]]
    return [response["status"], response["items"], [{
        k: c.get(k) for k in ("item_index", "memory_id", "record_id", "revision_id", "quote", "start", "end")
    } for c in response.get("citation_details", [])], response.get("validation")]


def summarize(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    result = {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "analysis": analyze(document), "configuration": document["configuration"],
              "source_unchanged": document.get("source_unchanged"),
              "evaluator_unchanged": document.get("evaluator_unchanged"),
              "native_extensions_unchanged": document.get("native_extensions_unchanged"),
              "cache": {}, "quality_comparison": {}, "quality_artifacts": {},
              "cold_first_observations": []}
    signatures = {}
    expected = Counter()
    inspected = Counter()
    for row in document["runs"]:
        calls = row.get("performance", {}).get("model_http_calls", [])
        details = {"qwen_calls": sum(c.get("operation") == "/v1/chat/completions" for c in calls),
                   "embedding_calls": sum(c.get("operation") == "/v1/embeddings" for c in calls),
                   "independent_review_calls": sum(c.get("phase") == "review" and
                       c.get("operation") == "/v1/chat/completions" for c in calls),
                   "counts": row.get("performance", {}).get("profile", {}).get("counts", {}),
                   "cache_after": row.get("interpretation_cache_after")}
        if row.get("warmup"):
            result["cold_first_observations"].append({"case": row["case"], "variant": row["variant"],
                "seconds": row["seconds"], "quality": row.get("quality"), **details})
            continue
        key = row["variant"] + "/" + row["case"]
        result["cache"].setdefault(key, []).append(details)
        expected[row["case"], row["variant"]] += 1
        artifact_path = path.parent / "quality" / f"{row['case']}-{row['sample']}-{row['variant']}.json"
        if not row.get("error_code") and artifact_path.exists():
            inspected[row["case"], row["variant"]] += 1
            result["quality_artifacts"][str(artifact_path.resolve())] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            encoded = json.dumps(signature(artifact, "results" in artifact["response"]),
                                 ensure_ascii=False, sort_keys=True)
            signatures.setdefault(row["case"], {}).setdefault(row["variant"], set()).add(
                hashlib.sha256(encoded.encode()).hexdigest())
    for case, variants in signatures.items():
        result["quality_comparison"][case] = {
            "exact_answer_or_search_order_and_citations_equal": (
                bool(variants.get("current")) and variants.get("current") == variants.get("candidate")
                and all(inspected[case, arm] == expected[case, arm] > 0 for arm in ("current", "candidate"))),
            "artifacts_checked": {arm: inspected[case, arm] for arm in ("current", "candidate")},
            "distinct_signatures": {k: sorted(v) for k, v in variants.items()}}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [summarize(p) for p in args.results]
    args.output.with_suffix(".json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["질문·문맥 해석 재사용 비교", "==========================", "",
        "Qwen/BGE 모델과 독립 답변 검증을 유지했습니다. 개인 DB는 사용하지 않았습니다.",
        "같은 입력의 준비 실행 이후 지정 횟수를 반복한 비교입니다. 새 질문의 속도 향상을 뜻하지 않습니다.",
        "기준과 후보 양쪽에 기존 ID 단축·원문 답변안 옵션을 적용하고, 후보에만 해석 재사용을 추가했습니다.",
        "기준/후보 순서를 교대하고 요청마다 모델 프롬프트 슬롯을 비웠습니다.",
        "해석 캐시의 초기화 조건은 실행별로 표시합니다. 첫 요청 관측은 별도로 표시합니다.", ""]
    for trial in results:
        placement = trial["analysis"]["placement"]
        lines += [placement.upper(), "-" * len(placement), "", f"원시 결과: {trial['path']}",
                  f"측정 완료: {trial['analysis']['execution_completed']}",
                  f"사례별 준비 실행 제외 반복 수: {trial['configuration']['samples']}",
                  "해석 캐시: " + ("매 요청 전 초기화" if trial['configuration'].get('cold_interpretations')
                                   else "반복 요청 사이에 유지"), ""]
        for key, case in trial["analysis"]["cases"].items():
            latency = case["latency_seconds"]
            detail = trial["cache"].get(key, [])
            median_calls = statistics.median([r["qwen_calls"] for r in detail]) if detail else None
            med = f"{latency['median']:.3f}" if latency['median'] is not None else "미완료"
            maximum = f"{latency['maximum']:.3f}" if latency['maximum'] is not None else "미완료"
            lines += [f"* {key}: 중앙 {med}초 / 최대 {maximum}초; "
                      f"품질 {case['automatic_quality_passes']}/{case['requested']}; Qwen 호출 중앙 {median_calls}회.",
                      f"  RAM 관측 최대 {case['ram_peak_mb']} MiB; 장치 VRAM 최대 {case['device_vram_peak_mb']} MiB.",
                      f"  Private commit 최대 {case['private_commit_peak_mb']} MiB; 시스템 여유 RAM 최소 {case['system_available_ram_min_mb']} MiB."]
            stages = case["exclusive_stages_seconds"]
            stage_text = ", ".join(f"{name} {stage['median']:.3f}초" for name, stage
                in stages.items() if stage["median"] is not None and stage["median"] >= .1)
            lines += ["  단계별 중앙: " + (stage_text or "각 단계 0.1초 미만")]
        lines += ["", "첫 요청 관측(각 1회, 통계적 개선율로 해석하지 않음):", ""]
        for row in trial["cold_first_observations"]:
            lines += [f"* {row['variant']}/{row['case']}: {row['seconds']:.3f}초, Qwen {row['qwen_calls']}회, "
                      f"독립 답변 검증 {row['independent_review_calls']}회."]
        lines += ["", "반복 품질 대조:", ""]
        for case, checked in trial["quality_comparison"].items():
            lines += [f"* {case}: 답변/검색 순서·인용의 정확 일치 {checked['exact_answer_or_search_order_and_citations_equal']}."]
        lines += [""]
    lines += ["범위와 한계", "-----------", "",
        "11개 합성 기록의 제한된 질문 반복 결과입니다. 자동 품질 검사는 전 범위 의미 품질 보장이 아닙니다.",
        "원문·기록 버전·대화·날짜·모델 설정이 달라지면 재사용하지 않습니다. 처음 묻는 질문에는 이득이 없습니다.",
        "본 비교는 같은 DB를 복제해 동일한 초기 대화에서 실행했습니다. 일반 대화에 새 메시지가 추가되면 문맥 캐시는 미적중할 수 있습니다.",
        "최종 답변 검증과 저장 시 출처 확인은 그대로 수행합니다. 모델 호출 수는 토큰 계산 요청을 제외합니다.",
        "메모리는 약 1초 간격의 요청 중 관측입니다. 짧은 요청의 최대치 및 모델 로딩 최대치를 보장하지 않습니다.",
        "RAM은 실험 Python·모델의 작업 집합, VRAM은 다른 앱을 포함한 장치 전체입니다.",
        "Private commit은 물리 RAM 사용량이 아닙니다. 캐시는 모델을 내리지 않으며 RAM·VRAM 절감을 보장하지 않습니다.",
        "CPU는 GPU 장치·연산·KV 오프로딩을 끕니다. GPU가 물리적으로 없는 PC는 검증하지 않았습니다.",
        "모델 로딩·색인·준비 실행·브라우저 표시 시간은 전체 응답 시간에 포함하지 않습니다.",
        "이 선택 옵션은 제품 기본 비활성입니다. 사용법: docs/interpretation_reuse.rst.", ""]
    args.output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
