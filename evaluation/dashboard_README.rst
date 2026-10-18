평가 관제실
===========

기존 FastAPI 앱에 평가 조회 화면을 추가합니다. 검색 순위·Top-K·프롬프트는
바꾸지 않습니다. 별도 프런트엔드 설치는 필요하지 않습니다.

화면 열기
---------

PowerShell에서 기존 모델 설정을 유지한 채 실행합니다::

    pwsh -File ./run_app.ps1 -Evaluation

이 실행기는 생성·검색 모델 서버를 함께 시작하고 임베딩 파일 버전을 설정합니다.
``python -m pma``는 웹 앱만 시작하므로 모델 서버가 없는 상태에서는 연결되지 않습니다.
이미 호환 모델 서버가 실행 중이라면 ``-ExternalServers``를 추가하세요.

실행기가 연 인증된 화면에서 **평가 관제실**을 선택합니다.
기본값은 비활성화이며, 끈 상태에서는 평가 DB를 만들지 않습니다.
활성화해도 질문·기대 답·실제 답 원문은 숨겨지고 상세 trace는 403을 반환합니다.
테스트 원문까지 보려면 앱 실행 전에 다음 설정을 명시합니다::

    $env:PMA_EVALUATION_DETAILS = "1"

이 설정은 해당 로컬 앱 세션에 상세 조회 권한을 부여합니다.
기존 Host/Origin/세션 검사를 그대로 적용하며, 평가 API는 읽기 전용입니다.
기존 기록 처리 진행률과 실패 목록도 그대로 사용할 수 있습니다.

평가 실행
---------

웹과 CLI는 같은 PMA_DATA_DIR을 사용해야 합니다. 기본 평가 DB 위치는
PMA_DATA_DIR/evaluation/evaluation.db입니다. 전역 --db 옵션으로 변경할 수 있습니다::

    .venv/Scripts/python.exe -m evaluation.runner variants
    .venv/Scripts/python.exe -m evaluation.runner validate my-dataset.json
    .venv/Scripts/python.exe -m evaluation.runner run my-dataset.json --memory-db C:/path/to/memory.db

run은 SQLite backup API로 일관된 임시 복사본을 만들고 그 복사본만 사용합니다.
원본 기억 DB를 수정하지 않으며, 기억 DB를 평가 DB로 지정하면 거부합니다.
현재 실행 지원 구성은 pma이며 baseline/pma_a/pma_b/pma_c는 unsupported입니다.
매 실행마다 새 run_id가 출력됩니다. 웹에서 현재 질문과 관측된 단계를 3초마다 갱신합니다.

데이터셋 예시 (ID와 정답을 실제 자료로 교체)::

    {
      "id": "my-dataset-v1", "name": "내 검색 평가", "version": "1",
      "cases": [{
        "id": "T01", "question": "회의에서 정한 담당자는 누구야?",
        "expected_answer": "김OO", "question_type": "relation",
        "ambiguity_class": "clear", "answerability": "answerable",
        "expected_behavior": "answer",
        "gold_groups": {"decision": ["실제-memory-id"]},
        "metadata": {
          "reference_time": "2026-10-15T00:00:00+09:00",
          "grading_method": "exact_match"
        }
      }]
    }

같은 근거 그룹 안에서는 하나만 충족하면 되고, 그룹 간에는 모두 충족해야 합니다.
같은 데이터셋 ID의 내용은 변경할 수 없습니다. 변경 시 ID와 version을 올립니다.
metadata.required_evidence_groups 형식도 읽습니다. 날짜 기준은 timezone이 필요합니다.
대화 문맥이 필요한 사례는 현재 Service API가 지원하지 않아 not_applicable입니다.

채점과 비교
-----------

exact_match 사례만 문자열 일치로 answer_correct를 자동 판정합니다.
의미가 같은 다른 표현을 자동 오답 처리하지 않으려면 옵션을 생략합니다.
그때 답변 판정은 pending_review입니다. 주장별 의미 검증은 자동 확정하지 않으므로
정답 일치·근거 ID 충족만으로 종합 통과를 만들지 않습니다.
사람이 검토한 Result JSONL은 evaluation.grading_method="human", grading_version,
answer_correct, final_evidence_complete, claims_supported 및 claims를 포함해 가져올 수
있습니다. import는 원래 실행을 덮어쓰지 않고 새 실행으로 보존합니다.

지표는 독립적으로 확정된 판정만 집계합니다. 분모 0은 null/N/A이며 실행 오류와
검토 대기를 오답으로 섞지 않습니다. 답변 정확도와 종합 verdict는 다를 수 있습니다.
P95는 실제 관측 지연 시간의 nearest-rank 방식이며 표본 수를 함께 저장합니다.
후보 병합 결과 상위 20개를 근거 검색률에 사용합니다. 개별 의미 검색·시간 필터·
재정렬 내부 단계는 not_instrumented입니다. 확인 못 한 탈락 원인은 unknown입니다.

버전 비교는 데이터셋 해시, 기억 스냅샷, 모델·임베딩, 평가 버전, 검색 설정,
실행 환경을 확인합니다. 모델 ID 미설정·미완료 실행도 비교 불가입니다.
공통 pass/fail 사례만 회귀 비교하며, 지표 차이는 퍼센트포인트(%p)로 표시합니다.
서로 다른 variant의 ablation 비교는 현재 비활성화입니다.

기존 결과 가져오기 / 상태 관리
------------------------------

기존 scenario_cases.json 및 memory_validation_cases.json 목록을 읽을 수 있습니다.
원본 기록 텍스트는 변환 데이터셋에 복사하지 않습니다. 기존 실행기는 유지합니다::

    .venv/Scripts/python.exe -m evaluation.runner import data/scenario_cases.json output/scenario-results.jsonl
    .venv/Scripts/python.exe -m evaluation.runner inspect RUN_ID
    .venv/Scripts/python.exe -m evaluation.runner reaggregate RUN_ID
    .venv/Scripts/python.exe -m evaluation.runner cancel RUN_ID

legacy PASS_EXISTING은 의미 정확도 통과로 바꾸지 않고 검토 대기로 남깁니다.
UNASSESSED는 평가 불가, BLOCKED는 실행 오류입니다. 누락 사례가 있는 import는 failed입니다.
Ctrl+C는 cancelled로 기록합니다. 강제 종료/정전은 자동 감지하지 않으므로 최근 단계
시각을 확인하고 cancel 후 새 실행을 시작합니다. 동일 실행 이어받기는 지원하지 않습니다.
취소는 진행 중인 모델 호출을 강제 종료하지 않고 다음 사례부터 중단합니다.

저장 구조 / API
---------------

001_initial.sql: eval_datasets, eval_cases, eval_gold_evidence, eval_runs,
eval_case_results, eval_metrics, eval_trace_events, eval_claims.
002_progress.sql: eval_run_progress. eval_migrations에서 버전을 추적합니다.
마이그레이션은 트랜잭션으로 직렬화되고 재실행할 수 있습니다.
trace는 SQLite에 저장하며 JSONL 이중 저장은 하지 않습니다.
수집 기본 상한은 질문별 256 KiB, 실행별 8 MiB입니다. 기억 원문은 trace에서 제외합니다.
평가 DB의 질문·답변 자체도 민감할 수 있으므로 개인 DB와 같은 보관 정책을 적용하세요.

GET /api/eval/datasets, /runs, /runs/{id}, /runs/{id}/summary,
/runs/{id}/cases, /runs/{id}/cases/{case_id}, /runs/{id}/cases/{case_id}/trace,
/runs/{id}/failures, /runs/{id}/scenarios, /compare를 제공합니다.
페이지 크기는 최대 100이며 고정 보조 키 정렬과 서버 측 필터를 사용합니다.
strict=1 비교 불가는 409, 잘못된 페이지는 400, 미인가 상세는 403,
없는 실행/질문은 404입니다. 세션이 없으면 기존 정책대로 401입니다.

검증 및 한계
------------

    .venv/Scripts/python.exe -m pytest tests/evaluation -q
    .venv/Scripts/python.exe -m pytest -q

Windows 제한 환경에서 TestClient 로컬 소켓이 차단되면 일반 로컬 터미널에서 실행하세요.
테스트는 실제 모델 없이 수행합니다. 실제 모델 품질·지연 시간은 CLI로 별도 측정합니다.
진단 OFF에서는 후보 목록 생성·DB 진단 쓰기를 하지 않습니다. ON에서는 후보 복사와
단계별 SQLite 쓰기가 추가되므로 지연 시간은 계측 비용을 포함합니다.
시나리오 화면은 질문 유형별 분포이며 전체 변수 히트맵은 후속 범위입니다.
원문 기억 출처 패널, 웹 평가 시작·판정 수정, 자동 재개, ablation 실행은 미지원입니다.
