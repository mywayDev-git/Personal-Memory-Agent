"""Report registered, exercised and verified coverage separately."""

import json
import platform
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from evaluation.scenario_contract import load

METRICS = [
    "Retrieval Recall@8",
    "All-required-evidence Recall@8",
    "Evidence Precision",
    "Citation Accuracy",
    "Answer Correctness (answered)",
    "Answer Correctness (all)",
    "Unsupported Claim Rate",
    "Confident Wrong Answer Rate",
    "Answer Coverage",
    "Appropriate Abstention Rate",
    "Over-abstention Rate",
    "Ambiguity Resolution Accuracy",
    "Unnecessary Clarification Rate",
    "Relation Link Precision",
    "Relation Link Recall",
    "Stale Memory Usage Rate",
]


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def report(root):
    variables, cases = load()
    before, after = read(root / "baseline_results.jsonl"), read(root / "patch_results.jsonl")
    old = {r["case_id"]: r for r in before}
    comparisons = []
    for row in after:
        row = dict(row)
        row["before_status"] = old[row["case_id"]]["status"]
        row["code_modified"] = row["case_id"] == "T03"
        if row["status"] == "PASS_EXISTING" and row["before_status"] == "RED":
            row["status"] = "GREEN"
        elif row["status"] == "RED" and row["before_status"] == "PASS_EXISTING":
            row["status"] = "REGRESSION"
        comparisons.append(row)
    for filename, rows in [
        ("regression_results.jsonl", comparisons),
        ("failure_cases.jsonl", [r for r in before if r["status"] == "RED"]),
    ]:
        (root / filename).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
    exercised = {r["case_id"] for r in after if r["status"] in {"RED", "PASS_EXISTING"}}
    coverage = [
        dict(
            id=v["id"],
            name=v["name"],
            registered=True,
            related_case_count=len(v["case_ids"]),
            current_support="unassessed",
            exercised_projection_cases=sorted(set(v["case_ids"]) & exercised),
            verified_variant_count=0,
            variants=[dict(value=x, status="UNASSESSED") for x in v["variants"]],
        )
        for v in variables
    ]
    write(root / "variable_coverage.json", coverage)
    metrics = {
        name: dict(
            before=None,
            after=None,
            valid_n=0,
            reason="Projection probes do not establish semantic answer quality",
        )
        for name in METRICS
    }
    timings = sorted(r["latency_seconds"] for r in after if "latency_seconds" in r)
    for label, percentile in [("P50 Latency", 0.5), ("P95 Latency", 0.95)]:
        import math

        metrics[label] = dict(
            after=timings[max(0, math.ceil(len(timings) * percentile) - 1)] if timings else None,
            valid_n=len(timings),
            scope="deterministic projection probes; seconds",
        )
    metrics["projection_checks"] = dict(
        before=dict(Counter(r["status"] for r in before)),
        after=dict(Counter(r["status"] for r in comparisons)),
    )
    write(root / "metrics_before_after.json", metrics)
    regression_file = root / "regression-pytest.xml"
    regression = None
    if regression_file.exists():
        suite = ET.parse(regression_file).getroot().find("testsuite")
        regression = dict(suite.attrib) if suite is not None else None
    write(
        root / "execution_environment.json",
        dict(
            python=sys.version,
            platform=platform.platform(),
            models="existing tests/conftest.py FakeModels; fixed [1,0,0] embeddings",
            extraction="injected event Memory Units, not real model extraction",
            real_model_evaluation="NOT_RUN",
            holdout="NOT_RUN",
            regression=regression,
            baseline_environment_issue="150 passed / 110 setup errors under restricted default temp; "
            "subsequent restricted API tests blocked in asyncio socketpair; "
            "full regression succeeded with permitted local execution",
        ),
    )
    (root / "report.md").write_text(
        """# 상황 변수 평가: 1차 구현 결과

## 범위와 결과

- R 68 / S 62 / L 80 / D 25: 총 235개 등록. 값별 검증 완료 0개.
- 대표 복합 사례 T01–T48: 48개 작성. 모두 development이며 독립 holdout은 아직 없다.
- 명세의 ID, 참조, 원문 인용 위치, 버전, 교차 split 중복 검사 구현.
- 의미상 정답 검토는 별도 필요하다. 자동 인용 검사만으로 정답의 의미적 타당성을 보증하지 않는다.
- T01–T05: 임시 SQLite + 기존 FakeModels + 고정 추출/임베딩으로 실제 검색·답변 경로 호출.
- 판정 대상은 fact 상태 투영이다. 기존 4 PASS / 1 RED → 4 PASS_EXISTING / 1 GREEN.
- T03: event로 추출된 “주려고 했다”를 observed로 분류. 원문에 명시된 의도를 planned로 제한.
- pma/facts.py FACT_VERSION 7로 올려 기존 투영이 새 규칙으로 재구축되도록 했다.
- 실제 전달, 명시적 부정, 미결정 및 의도 뒤 실제 전달의 반대 사례 포함.
- 나머지 43개 대표 사례는 실행 어댑터 미구현으로 UNASSESSED.

## 게이트 진행

GATE 1: 등록부·48개 명세·기존 코드 인터페이스 확인. 기존 120문항은 덮어쓰지 않고 별도 경로로 재생성.
GATE 2: 기계적 명세 검사와 P0 5개 투영 재현. 전체 답변·검색 품질 평가는 미완료.
GATE 3: T03의 최소 패치와 Red → Green 완료. 다른 P0 원인의 완전 검증은 남아 있음.
GATE 4: 미실행. 모호성·관계 요구사항을 성공으로 표시하지 않음.
GATE 5: 회귀 테스트 결과는 pytest 실행 로그 참조. 독립 holdout 및 실제 모델 통합 평가 미실행.

## 실행

```powershell
.\\.venv\\Scripts\\python.exe -m evaluation.scenario_contract
.\\.venv\\Scripts\\python.exe -m evaluation.scenario_runner --output output/scenario-evaluation/patch_results.jsonl
.\\.venv\\Scripts\\python.exe -m evaluation.scenario_report
.\\.venv\\Scripts\\python.exe -m pytest -q --basetemp output/scenario-evaluation/tmp-new-run
.\\.venv\\Scripts\\python.exe -m evaluation.validation_cases --output output/scenario-evaluation/legacy-validation-cases.json
```

baseline_results.jsonl은 수정 전 기록이다. 수정 후 실행으로 덮어쓰지 않는다.
등록부 재생성은 `python -m evaluation.scenario_registry <원본 프롬프트 경로>`로 가능하다.

## 한계와 다음 작업

각 변수 값별 추가 단일 사례, 43개 대표 사례 실행 어댑터, 인과·모호성·관계 검증,
최신 버전/삭제/확인 질문 중 변경의 lifecycle 실행, 사건 단위 독립 holdout을 추가해야 한다.
현재 T48의 변경 단계는 명세에만 있으며 실제 API 대화 절차가 구현된 것은 아니다.
T17·T21의 관계 요구는 원문으로 설명하지만 그래프 관계 채점은 아직 없다.
답변·검색·인용·관계 지표는 유효 채점 0건이므로 N/A이며 0%가 아니다.
지연시간은 고정 모델 실험 5건에 한정하며 실제 모델의 성능 수치가 아니다.
235개 변수 및 48개 사례 전체 검증 완료로 해석해서는 안 된다.
""",
        encoding="utf-8",
    )
    if regression:
        with (root / "report.md").open("a", encoding="utf-8") as handle:
            handle.write(
                "\n## 최종 회귀 실행\n\n"
                f"전체 {regression['tests']}건, 실패 {regression['failures']}건, "
                f"오류 {regression['errors']}건, 건너뜀 {regression['skipped']}건. "
                "regression-pytest.xml에 결과를 저장했다.\n\n"
                "초기 제한 환경에서는 기본 임시 디렉터리 오류와 로컬 API의 "
                "asyncio socketpair 대기가 발생했다. 허용된 로컬 실행으로 재검증했다. "
                "환경 오류를 제품 실패 또는 개선 수치에 포함하지 않았다.\n"
            )


if __name__ == "__main__":
    report(Path("output/scenario-evaluation"))
