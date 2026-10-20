"""Compare identical synthetic fixtures; retain failures and measurement boundaries."""

import argparse
import json
import math
import statistics
from pathlib import Path


def fixture_pass(case):
    # Regrade the earlier v2 runs under the same mandatory-citation rule as v3.
    return bool(
        case["passed"]
        and (
            not case["expected"]["expected_search"]
            or case.get("response", {}).get("citation_details")
        )
    )


def retrieval_metrics(case):
    expected = case["expected"]
    if not expected["expected_search"]:
        return None
    gold = {r["id"]: 1 for r in expected["records"]}
    if case["id"] == "NAT-T10":
        gold = {expected["records"][0]["id"]: 1}
    if case["id"] in {"NAT-T03", "NAT-T07"}:
        gold[expected["records"][-1]["id"]] = 2
    ranked = list(dict.fromkeys(case.get("evidence_ids", [])))[:8]
    dcg = sum((2 ** gold.get(key, 0) - 1) / math.log2(i + 2) for i, key in enumerate(ranked))
    ideal = sum(
        (2**grade - 1) / math.log2(i + 2)
        for i, grade in enumerate(sorted(gold.values(), reverse=True)[:8])
    )
    return {
        "recall_at_8": len(set(ranked) & set(gold)) / len(gold),
        "ndcg_at_8": dcg / ideal,
        "reciprocal_rank": next((1 / (i + 1) for i, key in enumerate(ranked) if key in gold), 0),
    }


def summarize(report):
    rows = report["cases"]
    durations = sorted(row["elapsed_seconds"] for row in rows)
    retrieval = [metrics for row in rows if (metrics := retrieval_metrics(row)) is not None]
    cited = [row for row in rows if row.get("response", {}).get("citation_details")]
    successful = [row["elapsed_seconds"] for row in rows if fixture_pass(row)]
    return {
        "cases": len(rows),
        "fixture_passed": sum(fixture_pass(row) for row in rows),
        "fixture_pass_rate": sum(fixture_pass(row) for row in rows) / len(rows),
        "failed_cases": [row["id"] for row in rows if not fixture_pass(row)],
        "latency_including_failures": {
            "p50": statistics.median(durations),
            "p95": durations[round((len(durations) - 1) * 0.95)],
            "p99": durations[round((len(durations) - 1) * 0.99)],
        },
        "successful_latency_p50": statistics.median(successful) if successful else None,
        "retrieval": {key: statistics.mean(r[key] for r in retrieval) for key in retrieval[0]}
        if retrieval
        else {},
        "exact_citation_case_rate": sum(
            r.get("checks", {}).get("exact_citations", False) for r in cited
        )
        / len(cited)
        if cited
        else None,
        "python_cpu_seconds_total": sum(r.get("python_cpu_seconds", 0) for r in rows),
        "combined_cpu_seconds_total": sum(r.get("combined_process_cpu_seconds", 0) for r in rows),
        "combined_ram_peak_mb": max(
            (r.get("combined_process_ram_peak_mb") or 0 for r in rows), default=None
        ),
        "whole_gpu_vram_peak_mb": max(
            (r.get("whole_gpu_vram_peak_mb") or 0 for r in rows), default=None
        ),
    }


def compare(before, after):
    if before.get("dataset_sha256") != after.get("dataset_sha256"):
        raise ValueError("DATASET_MISMATCH")
    if before.get("scoring_version") not in (2, 3) or after.get("scoring_version") not in (2, 3):
        raise ValueError("SCORING_MISMATCH")
    if before.get("settings") != after.get("settings"):
        raise ValueError("SETTINGS_MISMATCH")
    left, right = {c["id"]: c for c in before["cases"]}, {c["id"]: c for c in after["cases"]}
    if left.keys() != right.keys():
        raise ValueError("INCOMPLETE_PAIR")
    for key in left:
        if left[key]["expected"] != right[key]["expected"]:
            raise ValueError("FIXTURE_MISMATCH")
    return {
        "canonical_scoring_version": 3,
        "before": summarize(before),
        "after": summarize(after),
        "dataset_sha256": before["dataset_sha256"],
        "cases": [
            {
                "id": key,
                "before_passed": fixture_pass(left[key]),
                "after_passed": fixture_pass(right[key]),
                "before_seconds": left[key]["elapsed_seconds"],
                "after_seconds": right[key]["elapsed_seconds"],
                "before_checks": left[key].get("checks"),
                "after_checks": right[key].get("checks"),
            }
            for key in left
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--recheck", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def read(p):
        return json.loads(p.read_text(encoding="utf-8"))

    before, after, matrix = read(args.before), read(args.after), read(args.matrix)
    rechecks = []
    for path in args.recheck:
        checked = read(path)
        if checked.get("settings") != after.get("settings"):
            raise ValueError("SETTINGS_MISMATCH")
        replacements = {c["id"]: c for c in checked["cases"]}
        original = {c["id"]: c for c in after["cases"]}
        if not replacements.keys() <= original.keys() or any(
            replacements[key]["expected"] != original[key]["expected"] for key in replacements
        ):
            raise ValueError("RECHECK_FIXTURE_MISMATCH")
        after["cases"] = [replacements.get(c["id"], c) for c in after["cases"]]
        rechecks.append(
            {
                "path": str(path),
                "cases": list(replacements),
                "source_hashes": checked["source_hashes"],
            }
        )
    result = compare(before, after)
    result["rechecks"] = rechecks
    latest = {c["id"]: c for c in matrix["cases"]}
    latest.update({c["id"]: c for c in after["cases"]})
    result["initial_matrix"] = {
        "passed": sum(fixture_pass(c) for c in matrix["cases"]),
        "measured": matrix["measured"],
        "original_v2_passed": matrix["passed"],
    }
    result["latest_scenario_coverage"] = {
        "passed": sum(fixture_pass(c) for c in latest.values()),
        "cases": len(latest),
        "single_build_full_run": False,
    }
    result["limitations"] = [
        "각 사례 1회인 위험 기반 14개 비교이며 통계적 일반화가 아니다.",
        "원문 fixture를 직접 색인했으므로 추출 정확도를 측정하지 않는다.",
        "생성 서버는 기존 로컬 서버이며 다른 작업의 부하를 완전히 통제하지 않았다.",
        "RAM은 지정한 프로세스 작업 집합의 1초 표본 최대값, VRAM은 다른 앱을 포함한 GPU 전체 사용량이다.",
        "fixture 통과율은 필수 개념·금지 주장·인용·기억 거부 검사이며 전체 의미 정확도·자연스러움의 사람 평가를 대신하지 않는다.",
        "최신 시나리오 커버리지는 초기 30개와 수정 후 재검증을 합친 값이며 한 빌드의 30회 성능 측정이 아니다.",
        "전후 비교에는 원인 수정 후 해당 진도 사례의 재측정이 포함된다. 원 실행과 재측정의 소스 해시·시각은 각각 보존한다.",
    ]
    args.output.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    b, a = result["before"], result["after"]
    lines = [
        "대화 환경 통합 검증 보고서",
        "==========================",
        "",
        "실제 수행 결과",
        "---------------",
        "",
        "기존 코드 28d9672와 통합 코드를 같은 14개 합성 사례·모델·서버로 비교했다. 상세 입력·응답·인용·소스 해시는 JSON 결과에 보존했다.",
        "",
        f"* 고정 fixture 검사: 기존 {b['fixture_passed']}/{b['cases']} → 통합 {a['fixture_passed']}/{a['cases']}.",
        f"* 실패 포함 지연 p50: {b['latency_including_failures']['p50']:.2f}초 → {a['latency_including_failures']['p50']:.2f}초.",
        f"* 실패 포함 지연 p95: {b['latency_including_failures']['p95']:.2f}초 → {a['latency_including_failures']['p95']:.2f}초.",
        f"* 실패 포함 지연 p99: {b['latency_including_failures']['p99']:.2f}초 → {a['latency_including_failures']['p99']:.2f}초.",
        f"* Recall@8: {b['retrieval'].get('recall_at_8', 0):.3f} → {a['retrieval'].get('recall_at_8', 0):.3f}.",
        f"* nDCG@8: {b['retrieval'].get('ndcg_at_8', 0):.3f} → {a['retrieval'].get('ndcg_at_8', 0):.3f}.",
        f"* 지정 프로세스 CPU 합계: {b['combined_cpu_seconds_total']:.2f}초 → {a['combined_cpu_seconds_total']:.2f}초.",
        f"* 지정 프로세스 RAM 표본 최대: {b['combined_ram_peak_mb']:.1f}MiB → {a['combined_ram_peak_mb']:.1f}MiB.",
        "",
        f"초기 NAT 전체 실행은 필수 인용까지 동일하게 재평가하면 {result['initial_matrix']['passed']}/{matrix['measured']}였다. 수정·fixture 보완 후 재검증을 합친 최신 시나리오는 {result['latest_scenario_coverage']['passed']}/{len(latest)}다.",
        "",
        "평가 경계",
        "-----------",
        "",
        *["* " + text for text in result["limitations"]],
        "",
        "실패와 수정",
        "-----------",
        "",
        "* 재개 발화의 ‘다시’, 질의의 ‘마지막’, Part 번호를 과목명으로 잘못 해석하던 범위를 수정했다. 원문에 과목이 없는 진도를 특정 과목으로 승격하지 않는 회귀도 추가했다.",
        "* 근거가 모두 제외된 뒤 빈 enum의 모델 검증을 요청하던 경로는 명시적 근거 부족으로 종료한다.",
        "* 동일한 명시적 날짜·대상의 반대 완료 근거가 답변에서 빠지지 않도록 보존하고 독립 검토한다.",
        "* 검증 전 해석이 제안 생성의 사실 근거로 사용되던 경로를 차단했다. 과거 기억 답변도 제안 단계의 사실 근거로 재사용하지 않는다. 인용이 없는 개인 사실은 평가에서도 실패로 재분류한다.",
        "* 질문 자체에 생성 지침을 덧붙여 검증 의도를 바꾸지 않게 했다. 다른 Part를 인용하거나 명시된 완료 날짜를 없다고 말하는 후보는 별도 의미 검사로 거부한다.",
        "* 마지막 결정·지난 기록 설명의 명시적 조회와 일반 대화를 구분했다. 인사·감사를 모델이 그대로 반복하면 안전한 짧은 응답으로 복구한다.",
        "* NAT-T30 초기 fixture에는 과목명이 없었다. Python을 원문에 명시한 fixture로 보완하고, 무주제 원문을 Python으로 추정하지 않는 별도 회귀를 유지했다.",
        "* 비동기 갱신이 기록 화면을 대화로 바꾸는 경합과 저장 중 Escape 취소를 실제 앱 브라우저 검사로 수정했다.",
        "",
        "미측정·후속 평가",
        "----------------",
        "",
        "실제 사용자의 장기 자연스러움·추천 유용성, 대규모 새 데이터, 모든 17×10 평가 조합, 한 빌드 전체 NAT 반복 측정은 별도 평가 대상이다. 모델·검증 기본값은 완화하지 않았다.",
        "일부 제안에 이미 표시한 진도의 반복과 상투적인 마무리가 남아 있다. 사실·출처 검사 통과를 자연스러움의 완성으로 해석하지 않는다.",
        "",
        "회귀·화면 검증과 실행 환경",
        "--------------------------",
        "",
        "* 최종 전체 회귀: 549 passed, 기존 Starlette/httpx 사용 중단 경고 1개. pytest tests -q -p no:cacheprovider로 실행했다.",
        "* 실제 Chrome 브라우저: 화면 검사 31개와 앱 초기화·탐색 검사 13개, 합계 44개 통과. production HTML/CSS/JS와 합성 API를 사용했다. 실제 브라우저 확대율 대신 200%에 해당하는 축소 뷰포트를 검사했다.",
        "* Python 정적 검사와 변경 JavaScript 문법 검사 통과. UI 결과는 conversation_ui_results.json, 화면 예시는 docs/conversation-ui에 보존했다.",
        "* 기존 임베딩 서버 연결이 중단되어 비교 양쪽에 같은 모델의 임시 CPU 임베딩 서버를 사용했다. 개인 DB·운영 설정을 변경하지 않았다. 평가 종료 후 임시 서버를 종료했다.",
        "* 중간 회귀 실행은 디스크 공간 부족으로 중단됐다. 이 작업의 임시 DB만 정리한 뒤 전체 재실행한 결과가 위 549개다. 중단된 실행을 통과로 합산하지 않았다.",
        "* 지연과 CPU 비용이 증가했다. 비교는 검색 생략·검증 실패가 있던 기존 요청도 포함하므로 순수 생성 속도 비교로 해석하지 않는다. 검증을 생략하는 속도 개선은 적용하지 않았다.",
        "",
    ]
    args.output.with_suffix(".rst").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
