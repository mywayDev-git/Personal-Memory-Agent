"""Static, source-linked evaluation inventory; no inference or database access."""

import json
from pathlib import Path

DATA = Path(__file__).with_name("data")
VERSION = "main-suite-v6"
PROFILES = {
    "core": {"label": "현재 조합 핵심 평가", "repeats": 1, "split": "development"},
    "compare": {"label": "로컬 모델 비교", "repeats": 3, "split": "development"},
    "extended": {"label": "조합·성능·장애 확장 평가", "repeats": 1, "split": "development"},
    "final": {"label": "최종 후보 검증", "repeats": 5, "split": "final"},
}


def read(name):
    return json.loads((DATA / name).read_text("utf-8"))


def select_cases(profile):
    cases = read("scenarios.json")
    if profile == "final":
        return [c for c in cases if (c["split"] == "final" or c.get("adapter") == "contract_tests")
                and not c.get("extended_only") or c.get("safety_checks")]
    return [c for c in cases if c["split"] == "development"
            and (profile == "extended" or not c.get("extended_only"))
            and (c["priority"] == "P0" or profile == "extended"
                 or c["priority"] == "P1" and c["variant"] == "normal")]


def plan():
    catalog = read("catalog.json")
    cases = read("scenarios.json")
    return {
        "version": VERSION,
        "title": "Personal Memory Agent 메인 테스트",
        "policy": "사용자 명시 요청 또는 관제실 실행 버튼으로만 실행 · 조회·새로고침은 실행하지 않음",
        "baseline": "Qwen3-8B-Q4_K_M / bge-m3-Q8_0",
        "reference_time": "2026-10-20T10:00:00+09:00",
        "threshold_status": "미확정 · 첫 측정은 기준값 수집",
        "profiles": PROFILES,
        "categories": sorted({v["category"] for v in catalog}),
        "variables": catalog,
        "scenario_count": len(cases),
        "consolidated_duplicate_count": sum(len(c.get("source_case_ids", [c["id"]])) - 1 for c in cases),
        "automated_scenario_count": sum(c["adapter"] != "review" for c in cases),
        "fully_covered_variable_count": sum(v.get("automation_status") == "SCENARIO_CONTRACT" for v in catalog),
        "answer_only_variable_count": sum(v.get("automation_status") == "ANSWER_ONLY" for v in catalog),
        "behavior_contract_variable_count": sum(bool(v.get("behavior_contract")) for v in catalog),
        "unsupported_behavior_variable_count": sum(v.get("behavior_contract", {}).get("unsupported", False) for v in catalog),
        "review_scenario_count": sum(c["adapter"] == "review" for c in cases),
        "partial_coverage_scenario_count": sum(bool(c.get("coverage_gaps")) and not c.get("behavior_case_ids") for c in cases),
        "coverage_note": "실제 모델 질문과 저장소·HTTP·검색·화면 동작 검사를 구분합니다. 대체 모델을 쓰는 기능 검사는 모델 정확도에 포함하지 않습니다. 지원 밖 기능은 실제 거절을 검사하고 UNSUPPORTED로 표시합니다.",
    }


def validate():
    variables, cases = read("catalog.json"), read("scenarios.json")
    from .sources import resolve_sources, source_dataset
    corpus = source_dataset()
    by_id = {c["id"]: c for c in cases}
    assert len(by_id) == len(cases), "DUPLICATE_CASE"
    assert len({v["variable_id"] for v in variables}) == len(variables), "DUPLICATE_VARIABLE"
    assert len({v["category"] for v in variables}) == 15, "MISSING_CATEGORY"
    families = {}
    for case in cases:
        resolve_sources(case, corpus)
        assert case["split"] in {"development", "final"}
        if not case.get("catalog_only") and not case.get("extended_only"):
            for family in case.get("related_families", [case["family"]]):
                previous = families.setdefault(family, case["split"])
                assert previous == case["split"], "FAMILY_LEAKAGE"
        for record in case["records"]:
            assert record["owner"] in {"user-a", "user-b", "user-c"}
        sources = {r["id"]: r for r in case["records"]}
        for group in [*case.get("gold_groups", {}).values(), *case.get("optional_gold_groups", {}).values()]:
            assert group, "EMPTY_GOLD_GROUP"
            for ref in group:
                source = sources[ref["record_id"]]
                text = source["text"]
                assert ref["version"] >= 1
                assert text[ref["start"]:ref["end"]] == ref["quote"] and ref["quote"]
        assert case["adapter"] == "review" or case["steps"], "EMPTY_EXECUTION"
        assert case.get("expected_answer"), "MISSING_EXPECTED_ANSWER"
        if case.get("automated_from_review"):
            assert case["question"] == case["steps"][-1]["question"], "QUESTION_NOT_EXECUTED"
            assert (case["adapter"] == "product" and case.get("accepted_answers")
                    or case["adapter"] == "contract_probe" and case.get("input_contract")), "MISSING_ANSWER_ORACLE"
    for variable in variables:
        assert variable["cases"] and set(variable["cases"]) <= by_id.keys()
        assert all(variable["variable_id"] in by_id[k]["variables"] for k in variable["cases"]), "LOST_VARIABLE_MAPPING"
        if variable["priority"] == "P0":
            assert {variant for k in variable["cases"] for variant in
                    by_id[k].get("variable_variants", {}).get(variable["variable_id"], [by_id[k]["variant"]])} >= {"normal", "boundary"}
    from .deduplication import execution_key
    assert len({execution_key(c) for c in cases}) == len(cases), "DUPLICATE_EXECUTION"
    final = sum(split == "final" for split in families.values())
    assert abs(final / len(families) - .3) < .02, "SPLIT_RATIO"
    signatures = {"development": set(), "final": set()}
    cluster_splits = {}
    for case in cases:
        if case.get("catalog_only"):
            continue
        signatures[case["split"]].add("question:" + case["question"])
        signatures[case["split"]].update("source:" + r["text"] for r in case["records"] if r["id"] != "distractor")
        if case.get("evaluation_family"):
            previous = cluster_splits.setdefault(case["evaluation_family"], case["split"])
            assert previous == case["split"], "FIXTURE_CLUSTER_LEAKAGE"
    assert not signatures["development"] & signatures["final"], "SHARED_QUESTION_OR_SOURCE_ACROSS_SPLITS"
    return {"variables": len(variables), "cases": len(cases), "families": len(families),
            "final_families": final, "status": "VALID"}
