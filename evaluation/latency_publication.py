"""Publish content-free measurements from completed, isolated synthetic trials."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from evaluation.latency_models import MODELS, digest
from evaluation.response_latency_report import SCORING_VERSION, latency_gate, rescore

TRIALS = (
    "baseline-gpu-full", "baseline-current-comparison", "q4-gpu-full", "q8-gpu-full",
    "qwen-embedding-gpu-full", "planning-critical", "planning-final20", "selection-batches",
    "gpu-flash-on", "gpu-flash-off", "hybrid-basic", "cpu-basic",
    "gpu-flash-auto-basic", "gpu-flash-on-quality-screen",
)
CRITICAL_CASES = {"stopped", "negation", "plan", "identity", "followup", "additional_search",
                  "no_evidence", "long_evidence", "concurrent", "multi_hop"}


def critical_gate(summaries):
    return (set(summaries) == {"planning/" + case for case in CRITICAL_CASES}
            and all(row["samples"] >= 5 and row["quality_passes"] == row["samples"] and row["failures"] == 0
                    for row in summaries.values()))


def verification_gate(verification):
    python = verification.get("python", {})
    mixed = verification.get("mixed_event_summary", {})
    return (python.get("passed", 0) > 0 and python.get("failed") == 0
            and verification.get("ui_all_passed") is True and len(verification.get("ui_checks", [])) >= 4
            and mixed.get("cases", 0) > 0 and mixed.get("exact_sets") == mixed["cases"]
            and mixed.get("wrong_filter_questions") == 0 and mixed.get("wrong_expansion_approvals") == 0)


def median(values):
    return statistics.median(values) if values else None


def breakdown(rows):
    stages = sorted({key for row in rows for key in row.get("performance", {}).get("profile", {}).get("stages", {})})
    counters = sorted({key for row in rows for key in row.get("performance", {}).get("profile", {}).get("counts", {})})
    result = {"stages": {}, "counters": {}, "http": {}}
    for name in stages:
        values = [row.get("performance", {}).get("profile", {}).get("stages", {}).get(name, {}) for row in rows]
        result["stages"][name] = {key + "_median": median([r.get(key, 0) for r in values])
                                  for key in ("calls", "failures", "inclusive_seconds", "exclusive_seconds")}
    for name in counters:
        values = [r.get("performance", {}).get("profile", {}).get("counts", {}).get(name, 0) for r in rows]
        result["counters"][name] = {"min": min(values), "median": median(values), "max": max(values)}
    operations = sorted({c["operation"] for r in rows for c in r.get("performance", {}).get("model_http_calls", [])})
    for operation in operations:
        calls = [[c for c in r.get("performance", {}).get("model_http_calls", []) if c["operation"] == operation] for r in rows]
        result["http"][operation] = {
            "calls_median": median([len(cs) for cs in calls]),
            "seconds_median": median([sum(c["seconds"] for c in cs) for cs in calls]),
            "usage_reported_calls_median": median([sum("usage" in c for c in cs) for cs in calls]),
            "known_prompt_tokens_median": median([sum(c.get("usage", {}).get("prompt_tokens", 0) for c in cs) for cs in calls]),
            "known_completion_tokens_median": median([sum(c.get("usage", {}).get("completion_tokens", 0) for c in cs) for cs in calls]),
        }
    return result


def publish(root, *, allow_partial=False):
    result = {
        "schema_version": 1, "scoring_version": SCORING_VERSION, "personal_database_used": False,
        "hardware": {"cpu": "Intel Core i7-13700", "physical_cores": 16, "logical_processors": 24,
                     "physical_ram_bytes": 16940138496, "gpu": "NVIDIA GeForce RTX 3060",
                     "gpu_vram_mib": 8192, "driver": "617.42"},
        "runtime": {"version": "0.6.0-dev", "build": 11524, "commit": "86a283532", "compiler": "Clang 20.1.8"},
        "original_work_preserved_commit": "5a57d39", "initial_profiled_product_commit": "9a3c24d",
        "candidate_artifacts": MODELS, "conversion_tool_revision_disclosed": False,
        "synthetic_seed_canonical_json_sha256": hashlib.sha256(json.dumps(
            json.loads(Path("evaluation/response_latency_seed.json").read_text(encoding="utf-8")),
            sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "trials": {}, "missing_or_incomplete": [],
        "excluded": ["C-drive interrupted CPU run (disk full)", "screen1/2 invalid fixture",
                     "pilot screen3 (old scorer; separate rescoring exists, not pooled with final trials)"],
        "method": {"warmups_excluded": True, "failed_requests_separate_from_success_latency": True,
                   "paired_order_alternates": True, "stage_medians_are_not_additive": True,
                   "memory_sampling_seconds": 1, "cold_boot_startup_measured": False,
                   "raw_text_in_performance_logs": False, "fresh_question_understanding_in_model_comparisons": True},
    }
    for name in TRIALS:
        path = root / name / "results.json"
        if not path.exists():
            result["missing_or_incomplete"].append(name)
            continue
        source = json.loads(path.read_text(encoding="utf-8"))
        # The first 14-case run predates the end-of-run source guard. Require its
        # complete grid and the identical product manifest from the guarded control.
        config = source["configuration"]
        observed = {(r["variant"], r["case"], r["sample"]) for r in source["runs"]}
        expected = {(v, c, s) for v in config["variants"] for c in config["cases"] for s in range(config["samples"] + 1)}
        control_path = root / "baseline-current-comparison" / "results.json"
        legacy_complete = (name == "baseline-gpu-full" and observed == expected and len(observed) == len(source["runs"])
                           and control_path.exists() and source["sources"] == json.loads(control_path.read_text(encoding="utf-8"))["sources"])
        if source.get("execution_completed") is not True and not legacy_complete:
            result["missing_or_incomplete"].append(name)
            continue
        report = rescore(path)
        config = report["configuration"]
        trial = {"configuration": {key: config[key] for key in (
            "generation", "embedding", "placement", "flash", "threads", "samples", "variants", "cases")},
                 "hashes": report["hashes"], "input_results_sha256": digest(path),
                 "product_sources_sha256": hashlib.sha256(json.dumps(report["sources"], sort_keys=True).encode()).hexdigest(),
                 "evaluator_sources": report.get("evaluator_sources"),
                 "source_unchanged": report.get("source_unchanged"),
                 "evaluator_unchanged": report.get("evaluator_unchanged"),
                 "repository_reference_revision": report.get("repository_reference_revision"),
                 "measurement_scope": report.get("measurement_scope", "legacy_wall_including_quality_artifact_io"),
                 "original_quality_scoring_version": source.get("quality_scoring_version"),
                 "legacy_complete_grid_without_end_guard": legacy_complete,
                 "summary": report["summary"], "runs": [], "breakdown": {},
                 "preparation": {key: report.get(key) for key in (
                     "artifact_verification_seconds", "index_seconds", "initial_preparation_seconds")},
                 "model_startup_seconds": report["startup"]["seconds"],
                 "server_arguments": report["startup"]["commands"],
                 "retrieval_gate": report.get("retrieval_gate"), "screen_rejected": report.get("screen_rejected", False)}
        if name == "gpu-flash-on-quality-screen":
            screen = report["summary"]["baseline/stopped"]
            trial["quality_screen"] = {"cases": ["stopped"], "full_complex_suite_completed": False,
                                       "scope_passed": screen["samples"] >= 5 and screen["quality_passes"] == screen["samples"] and screen["failures"] == 0}
        if "original_cases" in config:
            trial["skipped_cases_after_quality_rejection"] = [c for c in config["original_cases"] if c not in config["cases"]]
        for row in report["runs"]:
            if row["warmup"]:
                continue
            saved = {key: row[key] for key in (
                "case", "sample", "variant", "parameters", "seconds", "status", "error_code", "quality",
                "ram_peak_mb", "gpu_total_peak_mb", "background_status", "arrival_during_extract", "error_phase") if key in row}
            profile = row.get("performance", {}).get("profile", {})
            saved["counters"] = profile.get("counts", {})
            saved["exclusive_stage_seconds"] = {key: val["exclusive_seconds"] for key, val in profile.get("stages", {}).items()}
            saved["profile_elapsed_seconds"] = profile.get("elapsed_seconds")
            trial["runs"].append(saved)
        for key in trial["summary"]:
            variant, case = key.split("/", 1)
            rows = [r for r in report["runs"] if not r["warmup"] and r["variant"] == variant and r["case"] == case]
            trial["breakdown"][key] = breakdown(rows)
        multilingual_path = path.parent / "multilingual.json"
        if multilingual_path.exists():
            multi = json.loads(multilingual_path.read_text(encoding="utf-8"))
            trial["multilingual"] = {key: multi.get(key) for key in (
                "scope", "replayed_model_outputs", "documents", "document_embedding_seconds", "evaluated_modes", "summary", "alias_checks")}
            trial["multilingual"]["per_question"] = [{"id": row["id"], **{key: row.get("expanded", {}).get(key) for key in (
                "precision_at_8", "recall_at_8", "understanding_error", "search_seconds", "understanding_seconds", "total_seconds")}}
                for row in multi["cases"]]
        result["trials"][name] = trial
    if result["missing_or_incomplete"] and not allow_partial:
        raise ValueError("INCOMPLETE_TRIALS: " + ", ".join(result["missing_or_incomplete"]))
    final = result["trials"].get("planning-final20", {}).get("summary", {})
    if "planning/simple_answer" in final:
        result["simple_answer_timing_gate"] = latency_gate(final["baseline/simple_answer"], final["planning/simple_answer"])
    critical = result["trials"].get("planning-critical", {}).get("summary", {})
    result["critical_quality_passed"] = critical_gate(critical)
    result["defaults_changed"] = False
    result["quality_latency_qualified"] = bool(result.get("simple_answer_timing_gate", {}).get("passed")
                                              and result["critical_quality_passed"] and not result["missing_or_incomplete"])
    result["verification_passed"] = False
    result["overall_qualified"] = False  # A complete verification record is also required.
    return result


def rst_table(headers, rows):
    lines = [".. list-table::", "   :header-rows: 1", ""]
    for row in [headers, *rows]:
        lines.append("   * - " + str(row[0]))
        lines.extend("     - " + str(value) for value in row[1:])
    return "\n".join(lines) + "\n\n"


def render_report(report):
    def seconds(value):
        return "미측정" if value is None else f"{value:.3f}"

    trials = report["trials"]
    sections = [
        "응답 속도와 근거 품질 비교\n==========================\n\n",
        "개인 DB를 사용하지 않고 합성 원문 11개와 별도 다국어 문서 216개로 측정했다. "
        "기존 변경은 5a57d39로 원래 브랜치에 보존·푸시했고, 성능 작업은 codex/response-latency에 분리했다. "
        "생성·임베딩 모델과 배치·표시·캐시의 제품 기본값은 유지했다.\n\n",
        "이전 GPU 보고서의 검색 약 3.1초·기억 답변 약 15.3초는 질문과 실행 조건이 다른 참고값이다. "
        "이번 개선율의 분모로 사용하지 않고 현재 변경이 포함된 새 기준선과 비교했다.\n\n",
        "채택 판정\n---------\n\n",
    ]
    gate = report.get("simple_answer_timing_gate", {})
    sections.append(f"단순 답변 20회 속도 기준: {'통과' if gate.get('passed') else '미충족'}. "
                    f"핵심 복합 사례 품질 기준: {'통과' if report['critical_quality_passed'] else '미충족'}. "
                    f"전체 채택 조건: {'충족' if report['overall_qualified'] else '미충족'}.\n\n")
    if "median_reduction" in gate:
        sections.append(f"단순 답변 중앙값 감소율은 {gate['median_reduction']:.1%}다. "
                        "이 수치를 복합 질문 전체의 개선율로 해석하지 않는다.\n\n")
    sections.append("모든 핵심 사례가 통과해야 기본값 변경 후보가 된다. 인용 위치가 정확하고 독립 모델 검증이 "
                    "성공해도 동명이인의 직업을 합치거나 반납 계획을 실제 실행으로 해석하면 실패다. "
                    "정답 근거 누락·과도한 거절도 품질 실패로 센다.\n\n")
    sections.append("측정 조건\n---------\n\n"
                    "Intel Core i7-13700(16코어/24스레드), 물리 RAM 16,940,138,496바이트, "
                    "RTX 3060 8,192 MiB, 드라이버 617.42. llama.cpp 0.6.0-dev build 11524 "
                    "(86a283532, Clang 20.1.8). 생성 문맥 16,384·임베딩 8,192 토큰을 유지했다. "
                    "18181/18182 포트만 실험에 사용했고, 사용자 승인으로 기존 앱을 일시 종료했다.\n\n"
                    "후보별 준비 실행 1회를 제외하고 5회, 최종 비교는 같은 서버·질문·DB의 두 변형을 "
                    "반복마다 역순으로 실행해 각각 20회 측정했다. P95는 nearest-rank 방식이며 "
                    "5회 P95는 최댓값이다. 서로 다른 실행의 표본을 합치지 않았다. "
                    "실행 실패는 완주 지연 통계와 분리하고 실패율·품질 실패에 포함했다. "
                    "품질 실패한 완주 요청의 시간도 표에는 남기지만, 품질 조건을 통과한 속도 개선으로 세지 않는다.\n\n")
    sections.append("측정은 모델 서버 HTTP 호출을 포함한 Service.search / ChatEngine.message 함수 호출의 벽시계다. "
                    "기억 답변에는 독립 검증과 최종 DB 커밋이 포함된다. FastAPI 전송·브라우저 렌더링, "
                    "단순 검색의 검색 결과 세션 저장은 포함하지 않는다. 최종 20회와 이후 실행 설정·배치 비교는 "
                    "함수 반환 시 시간을 멈추고 정답 채점·평가 파일 저장을 제외한다. 그 이전 기준선·모델·복합 품질 "
                    "실험의 벽시계에는 평가 파일 저장·채점·메시지 재조회 비용도 소량 포함되었다. 이 측정 경계 차이를 "
                    "JSON measurement_scope로 표시하고 서로 다른 경계의 표본을 합산하지 않았다.\n\n")
    sections.append("최종 20회 교차 비교\n-------------------\n\n")
    final = trials.get("planning-final20", {}).get("summary", {})
    sections.append(rst_table(["변형/사례", "중앙값 초", "P95 초", "품질/표본", "실행 실패", "RAM/VRAM MiB"], [
        [name, seconds(row["median_seconds"]), seconds(row["p95_seconds"]), f"{row['quality_passes']}/{row['samples']}",
         row["failures"], f"{seconds(row['peak_ram_mb'])}/{seconds(row['peak_gpu_total_mb'])}"] for name, row in final.items()]))
    sections.append("planning은 평가기에만 있는 실험이다. 추가 검색 판단의 중복 query_plan·순위 점수·화면 설명을 "
                    "줄이고 질문·전체 원문·인용·시간·사실 검토 경고·필터·대화 이력은 유지한다. 추가 검색 판단, "
                    "관련성 판정과 독립 근거 검증을 생략하지 않는다. 제품에는 이 입력 축소를 적용하지 않았다.\n\n")
    sections.append("앞선 5회 교차 실험(최종 20회와 합산하지 않음)\n\n")
    pilot = trials.get("baseline-current-comparison", {}).get("summary", {})
    sections.append(rst_table(["변형/사례", "중앙값 초", "P95 초", "품질/표본"], [
        [key, seconds(row["median_seconds"]), seconds(row["p95_seconds"]), f"{row['quality_passes']}/{row['samples']}"]
        for key, row in pilot.items()]))
    sections.append("기준선과 복합 품질\n-----------------\n\n")
    for name in ("baseline-gpu-full", "planning-critical"):
        sections.append(name + "\n\n")
        rows = trials.get(name, {}).get("summary", {})
        sections.append(rst_table(["변형/사례", "중앙값 초", "P95 초", "품질/표본", "실행 실패"], [
            [key, seconds(row["median_seconds"]), seconds(row["p95_seconds"]), f"{row['quality_passes']}/{row['samples']}", row["failures"]]
            for key, row in rows.items()]))
    sections.append("학습 중단 질문에서는 기준선과 planning 모두 '중단한 기록은 없다'고 말하면서 "
                    "'공부를 접었다'는 기록을 설명했다. 인용이 정확해도 의미가 모순되어 양쪽 모두 0/5다. "
                    "직접 답변 대조에서 발견한 이 오류를 scoring_version=5에 반영해 모든 고정 응답을 같은 기준으로 "
                    "읽기 전용 재채점했다. 중단 사건을 부정하는 것과 중단 날짜가 불명인 것은 구분한다. "
                    "기준선의 plan은 2/5만 계획과 실행 불확실성을 모두 설명했고 나머지는 근거 부족으로 거절했다. "
                    "followup은 회사 동료를 지정한 앞선 답변 이후 동아리 친구의 수학 교사 직업을 답하거나 "
                    "두 직업을 한 사람에게 합쳐 0/5였다. 새 정답 검사는 기대 직업 구절과 허용 원문 범위도 확인한다. "
                    "이 보조 검사만으로 일반적인 답변 정확성·완전성을 보장하지 않으며, 실패 응답을 원문과 함께 확인했다. "
                    "concurrent는 실제 배경 추출 진행 중 요청 도착과 배경 저장 성공을 확인한다. 날짜 조건이 있는 "
                    "simple_answer와 다른 질문이므로 두 전체 시간의 차이를 대기 비용으로 해석하지 않는다.\n\n")
    sections.append("생성·임베딩 모델 비교\n---------------------\n\n")
    model_rows = []
    for name in ("baseline-current-comparison", "q4-gpu-full", "q8-gpu-full", "qwen-embedding-gpu-full"):
        trial = trials.get(name, {})
        multi = trial.get("multilingual", {}).get("summary", {})
        pos = multi.get("positive", {}).get("expanded", {})
        neg = multi.get("negative", {}).get("expanded", {})
        model_rows.append([name, seconds(pos.get("precision_at_8")), seconds(pos.get("recall_at_8")),
                           f"{seconds(neg.get('precision_at_8'))}/{seconds(neg.get('recall_at_8'))}",
                           len((trial.get("retrieval_gate") or {}).get("regressed_cases", [])),
                           trial.get("screen_rejected", False)])
    sections.append(rst_table(["실험", "양성 P@8", "양성 R@8", "음성 P/R", "회귀 질문 수", "제외"], model_rows))
    sections.append("모델별 기본 응답 5회(별도 서버 실행 간 비율을 최종 개선율로 사용하지 않음)\n\n")
    model_timing_rows = []
    for name in ("baseline-current-comparison", "q4-gpu-full", "q8-gpu-full", "qwen-embedding-gpu-full"):
        for case in ("simple_search", "simple_answer"):
            row = trials.get(name, {}).get("summary", {}).get("baseline/" + case)
            if row:
                model_timing_rows.append([f"{name}/{case}", seconds(row["median_seconds"]), seconds(row["p95_seconds"]),
                                          f"{row['quality_passes']}/{row['samples']}", row["failures"],
                                          f"{seconds(row['peak_ram_mb'])}/{seconds(row['peak_gpu_total_mb'])}"])
    sections.append(rst_table(["실험/사례", "중앙값 초", "P95 초", "품질/표본", "실행 실패", "RAM/VRAM MiB"], model_timing_rows))
    sections.append("각 모델의 90개 질문 이해를 새로 실행했다. 이 지표는 기존 다국어 평가와 같은 "
                    "선택적 LLM 관련성 검토 전의 검색·융합·상위 8개 단계다. 전체 관련성 판정과 답변·독립 검증은 "
                    "별도 11원문 시나리오에서 측정한다. 평균이 아니라 질문별 P@8·R@8 비하락과 "
                    "Python/API/ML 별칭 동등성을 검사했다. 회귀한 모델은 단순 검색·답변 5회만 추가 측정하고 "
                    "복합 사례는 생략했다. 실행하지 않은 사례는 통과로 세지 않는다. 설정·코드·모델을 함께 바꾼 "
                    "조합은 개별 후보가 품질을 통과한 뒤에만 채택 평가 대상이다.\n\n")
    sections.append("호출 병목과 선택 옵션\n---------------------\n\n")
    controls = trials.get("planning-final20", trials.get("baseline-current-comparison", {}))
    rows = []
    for name in ("baseline/simple_answer", "planning/simple_answer"):
        part = controls.get("breakdown", {}).get(name, {})
        http = part.get("http", {})
        calls = http.get("/v1/chat/completions", {})
        rows.append([name, calls.get("calls_median"), seconds(calls.get("seconds_median")),
                     part.get("counters", {}).get("search_iterations", {}).get("median"),
                     seconds(http.get("/tokenize", {}).get("seconds_median"))])
    sections.append(rst_table(["변형/사례", "생성 호출 중앙값", "생성 HTTP 초", "검색 반복 중앙값", "토큰 계산 HTTP 초"], rows))
    sections.append("기존 경로는 충분한 초기 근거가 있어도 추가 검색과 후보 판정 배치를 수행하는 경우가 있었다. "
                    "병목의 우선순위는 생성·관련성 판정·추가 검색 판단이며 토큰 계산 단축만으로 20%를 설명하기 어렵다. "
                    "단계 포함 시간은 중복되므로 합산하지 않는다. JSON에는 단계별 exclusive 값, 반복 횟수, "
                    "HTTP 호출 시간·횟수·서버가 제공한 토큰 수와 표본별 측정값을 남겼다. 단계별 중앙값 역시 "
                    "서로 다른 표본에서 나올 수 있어 합계가 전체 중앙값과 같지 않다.\n\n")
    sections.append("기준선의 주요 병목(각 단계의 exclusive 중앙값, 상위 3개)\n\n")
    bottlenecks = []
    full = trials.get("baseline-gpu-full", {}).get("breakdown", {})
    for case in ("simple_search", "long_evidence", "followup", "plan", "concurrent"):
        part = full.get("baseline/" + case, {})
        top = sorted(part.get("stages", {}).items(), key=lambda item: -item[1]["exclusive_seconds_median"])[:3]
        counts = part.get("counters", {})
        bottlenecks.append([case, ", ".join(f"{key} {row['exclusive_seconds_median']:.3f}" for key, row in top),
                            "/".join(str(counts.get(key, {}).get("median", "미계측")) for key in (
                                "search_iterations", "generation_attempts", "review_attempts"))])
    sections.append(rst_table(["사례", "상위 단계 초", "검색/생성/검증 반복 중앙값"], bottlenecks))
    sections.append("긴 근거와 후속 질문은 관련성 판정 비용이 컸고 계획 질문은 생성·검증을 두 번 수행했다. "
                    "배경 처리 중 요청의 model_wait는 실제 모델 차례 대기다. 독립 검증을 없애거나 다른 질문·정책의 "
                    "판정 결과를 재사용해 이 시간을 줄이는 방식은 채택하지 않았다.\n\n")
    for group, names in (("판정 배치와 캐시", ("selection-batches",)),
                         ("실행 설정", ("gpu-flash-auto-basic", "gpu-flash-on", "gpu-flash-off", "hybrid-basic", "cpu-basic",
                                    "gpu-flash-on-quality-screen"))):
        sections.append(group + "\n\n")
        rows = []
        for name in names:
            for key, row in trials.get(name, {}).get("summary", {}).items():
                rows.append([f"{name}/{key}", seconds(row["median_seconds"]), seconds(row["p95_seconds"]),
                             f"{row['quality_passes']}/{row['samples']}", row["failures"],
                             f"{seconds(row['peak_ram_mb'])}/{seconds(row['peak_gpu_total_mb'])}"])
        sections.append(rst_table(["변형/사례", "중앙값 초", "P95 초", "품질/표본", "실행 실패", "RAM/VRAM MiB"], rows))
        if group == "판정 배치와 캐시":
            calls = []
            for key, part in trials.get("selection-batches", {}).get("breakdown", {}).items():
                http = part.get("http", {})
                calls.append([key, http.get("/v1/chat/completions", {}).get("calls_median", "미측정"),
                              http.get("/tokenize", {}).get("calls_median", "미측정"),
                              part.get("counters", {}).get("token_cache_hits", {}).get("median", 0)])
            sections.append(rst_table(["변형/사례", "생성 호출 중앙값", "토큰 계산 호출 중앙값", "캐시 적중 중앙값"], calls))
    sections.append("selection_batch는 11개 모든 후보를 기존 인용 문맥 범위로 판정하는 구성 요소 실험이며 최종 답변 지연이 아니다. "
                    "관련성 판정은 기존 compact_evidence의 인용 시작 200자 전부터 600자 뒤까지인 범위를 유지한다. "
                    "추가 검색 판단의 전체 source_text와 최종 원문 인용 검증 범위는 줄이지 않았다. "
                    "cached는 정확히 같은 토큰 계산 입력에만 요청 내부 128개 LRU를 적용한다. "
                    "질문·원문 버전·정책이 달라진 판정 결과를 재사용하는 캐시는 추가하지 않았다. "
                    "plain은 별도의 5회 교차 실험에서 planning 17.670초 대비 15.812초였지만 단순 답변의 "
                    "제한된 결과이므로 표시 형식의 기본값을 바꾸지 않았다.\n\n")
    sections.append("준비 시간·재색인 비용\n---------------------\n\n")
    rows = []
    for name, trial in trials.items():
        prep = trial["preparation"]
        rows.append([name, seconds(prep["artifact_verification_seconds"]), seconds(trial["model_startup_seconds"]),
                     seconds(prep["index_seconds"]), seconds(trial.get("multilingual", {}).get("document_embedding_seconds"))])
    sections.append(rst_table(["실험", "해시 확인 초", "서버 시작 초", "11개 색인 준비 초", "216개 문서 임베딩 초"], rows))
    sections.append("같은 임베딩 프로필은 기존 합성 색인을 복사하므로 11개 준비 시간이 재임베딩 속도는 아니다. "
                    "Qwen 임베딩은 별도 실험 DB에서만 새 벡터를 만들었다. 양쪽 벡터는 1024차원 float32로 "
                    "원시 벡터 저장량은 기억당 4096바이트이며 DB·색인 부가 비용은 별도다. 실제 재색인은 원문 길이·" 
                    "분할 수·추출 및 검증·동시 작업에 따라 달라지므로 216개 문서 임베딩만으로 개인 DB 총 소요 시간을 "
                    "확정할 수 없다. 이번 작업은 개인 DB 재색인을 실행하지 않았다.\n\n"
                    "해시 확인이 OS 파일 캐시를 데우므로 시작 시간은 콜드 부팅 측정이 아니다. RAM은 평가 Python과 "
                    "소유한 서버의 작업 집합 합계로 공유 페이지가 중복될 수 있다. VRAM은 바탕화면 등을 포함한 GPU "
                    "전체 사용량을 1초마다 관측한 최댓값이며 순간 절대 최대는 아니다.\n\n")
    sections.append("재현성과 한계\n-------------\n\n"
                    "response_latency_results.json에는 파일 SHA-256·서버 인자·코드 해시·표본과 질문별 지표가 있다. "
                    "response_latency_seed.json은 측정 당시의 합성 원문·ID·시각·벡터를 논리 행으로 저장한다. "
                    "처음 14사례 기준선은 종료 시 코드 검사가 추가되기 전 실행이므로 종료 해시 검증 값은 null이다. "
                    "표본 84개 완주와 후속 기준선의 동일 제품 소스 목록을 확인하고 최신 scoring_version=5로 "
                    "읽기 전용 재채점했다. 후속 실험은 제품·평가 코드 종료 해시 검사를 통과해야 집계했다.\n\n"
                    "최종 20회 전에 독립 검색의 요청 범위 계측 연결과 반환 시점 타이머를 보완하고 테스트한 뒤 "
                    "소스를 다시 고정했다. 이 계측 연결의 시간을 별도의 속도 개선으로 주장하지 않는다. "
                    "각 실행의 Git 참조와 실제 파일 해시를 JSON에 남겼다.\n\n"
                    "초기 C 드라이브 CPU 실행은 다운로드 중 공간 부족으로 중단되어 통계에서 제외했다. "
                    "두 초기 시험의 합성 스키마 오류와 이전 채점기 파일도 제외했다. D 드라이브로 옮긴 것은 "
                    "이번 작업에서 만든 다운로드 파일이며 이후 여유 공간 검사와 원자적 결과 저장을 추가했다.\n\n"
                    "생성 후보는 공식 Qwen 원본 참조 리비전과 Unsloth GGUF 배포 리비전·파일 해시를 고정했다. "
                    "배포자가 정확한 변환 도구 리비전을 공개하지 않아 변환 재빌드까지 재현 가능하다고 주장하지 않는다. "
                    "런타임 버전은 변환 도구 버전의 증거가 아니다. 이 제한은 모델 채택 검토에 남긴다. "
                    "임베딩 후보는 Qwen 공식 GGUF 배포 파일이다. 고정 주소·크기·해시는 latency_models.py와 JSON에 있다.\n\n")
    sections.append("적용·복구 절차\n-------------\n\n"
                    "현재 권장 조합은 기존 Qwen3-8B-Q4_K_M + BGE-M3-Q8_0, 4개 판정 배치, 검토된 표시다. "
                    "측정 계측과 명시적 실험 옵션만 추가했고 자동 기본 모델 전환은 하지 않았다. "
                    "planning은 핵심 품질 보강 후 다시 검증할 우선 후보다.\n\n"
                    "별도 적용을 검토할 때는 앱을 정상 종료하고 SQLite backup API 등 일관된 방법으로 DB를 백업한다. "
                    "개인 DB 사본에서 새 프로필 색인을 따로 만들고 질문별 정확도·원문 인용·취소·시간 초과·재처리를 "
                    "검증한 뒤 명시적으로 전환한다. Qwen은 qwen3-retrieval-v1, 질문 지시문, last pooling, L2 정규화가 "
                    "필요하며 raw-v1 BGE 벡터와 섞지 않는다. 질문 지시문 변경도 프로필 버전을 변경해야 한다.\n\n"
                    "복구는 PMA_REQUEST_TOKEN_CACHE·PMA_SELECTION_BATCH_SIZE·PMA_CHAT_PRESENTATION의 실험 설정을 "
                    "해제하고 원래 생성·임베딩 파일과 raw-v1으로 실행한다. 실제 재색인까지 했다면 모델 식별 키를 확인하고 "
                    "보관한 일관된 DB 백업으로 복원한 후 원문·검색·근거를 확인한다. 이번 측정 종료 후에는 기존 앱을 "
                    "원래 설정(-Evaluation -Test, 8765/8081/8082)으로 복구하고 화면·두 모델의 응답을 확인한다.\n\n"
                    "재현 명령과 선택 메타데이터 계약은 docs/response_latency.md를 참고한다. "
                    "JSON 집계는 python -m evaluation.latency_publication <실험 루트> "
                    "--verification evaluation/response_latency_verification.json "
                    "--output evaluation/response_latency_results.json으로 재생성한다. "
                    "미완료 실행은 기본적으로 공개 집계에서 거부한다. 회귀 검사 기록이 없으면 전체 채택 조건을 통과로 표시하지 않는다.\n")
    verification = report.get("verification")
    if verification:
        python = verification["python"]
        mixed = verification["mixed_event_summary"]
        sections.append("\n회귀 검사\n---------\n\n"
                        f"전체 Python {python['passed']}개 통과, 실패 {python['failed']}개({python['seconds']:.2f}초). "
                        f"화면 검사 {len(verification['ui_checks'])}종 {'통과' if verification['ui_all_passed'] else '실패 포함'}: " + ", ".join(verification["ui_checks"]) + ". "
                        f"혼합 사건 평가는 {mixed['exact_sets']}/{mixed['cases']}개 정답 집합 일치, "
                        f"평균 Recall@8 {mixed['mean_recall_at_8']:.3f}, 잘못된 필터 질문 {mixed['wrong_filter_questions']}개다. "
                        "혼합 사건 평가는 결정적 대체 모델을 사용하는 회귀 검사로, 실제 모델 정확도와 구분한다.\n")
    return "".join(sections)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--verification", type=Path, help="Recorded test/UI/offline evaluation results, if available")
    args = parser.parse_args()
    report = publish(args.root, allow_partial=args.allow_partial)
    if args.verification:
        report["verification"] = json.loads(args.verification.read_text(encoding="utf-8"))
        report["verification_passed"] = verification_gate(report["verification"])
        report["overall_qualified"] = report["quality_latency_qualified"] and report["verification_passed"]
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.allow_partial:
        args.output.with_suffix(".rst").write_text(render_report(report), encoding="utf-8")
    print(json.dumps({"completed": list(report["trials"]), "missing": report["missing_or_incomplete"]}))


if __name__ == "__main__":
    main()
