서비스 검색·근거·최종 응답 계측 — Prompt 5
========================================

2026-10-17 (Asia/Seoul), codex/search-diagnostics-v1.

완료 범위
---------

Service.search/answer가 진단 설정을 읽어 요청 scope를 시작하고 정상·예외 경로에서
종료한다. 외부에서 이미 시작한 trace가 있으면 재사용한다. 기존 API에는 trace_id나
진단 필드를 추가하지 않는다. ContextVar는 같은 Service의 동시 요청에서도 분리된다.
모델 잠금의 기존 대기·획득·해제 순서를 유지한다.

설정에서 PMA_DIAGNOSTICS=1과 PMA_DIAGNOSTICS_PATH를 지정하고 앱을 시작하면,
서비스에 도달한 검색·질문 요청을 JSONL로 기록할 수 있다. 경로의 부모 디렉터리는
이미 존재해야 한다. 경로 미지정은 메모리 수집만 하며 기본값은 여전히 OFF이다.
인증·입력 검증 등 서비스에 도달하기 전에 발생하는 HTTP 오류는 이 단계의 범위가 아니다.

수정 파일
---------

* pma/service.py: 기존 실행 지점에서 관찰값 전달, 공개 요청 함수의 scope 연결.
* pma/service_diagnostics.py: 개인정보를 제외한 관찰값 조립, 요청별 상태·시간 관리,
  기존 진단 sink 이벤트를 새 스키마로 변환, 최종 결정·예외 기록.
* pma/facts.py: compatible에 선택적 on_exclude 콜백 추가. 실제 첫 실패 분기에서
  reason을 전달한다. 기존 비교 조건·순서·기본 bool 반환은 유지한다.
* pma/diagnostics.py: 모델 선정 ID 가명 목록, 원본 일관성 검증 단계 및 관련 reason,
  Store와의 중복 이벤트 방지를 위한 읽기 전용 이벤트 확인 기능 추가.
* tests/diagnostics/test_service.py: 서비스 추가 테스트 15개.
* tests/diagnostics/benchmark_service.py: 모의 서비스 성능 측정.

왜 facts.py도 수정했는가
-----------------------

기존 compatible은 여러 실패 분기를 False 하나로 합쳤다. 서비스에서 조건을 다시
평가하면 실제 최초 제외 순서를 보장할 수 없으므로, 각 기존 실패 분기에 reason
전달만 넣었다. 새로운 필터나 조건 완화는 추가하지 않았다. 다른 compatible 호출자는
기존 두 인자 방식 그대로 사용할 수 있고, 콜백 오류도 원래 bool 결과를 바꾸지 않는다.
query_plan 생성 및 시간 앵커 정책은 수정하지 않았다.

관찰되는 정보
-------------

* query_understanding: 분석 성공/fallback, 조건 존재 여부, 시간 앵커 필요 여부.
  규칙·모델·명시 입력이 섞인 계획 전체의 출처는 unknown으로 두며 추측하지 않는다.
* structure_filter: 입력·출력 수, 후보별 포함 또는 실제 첫 제외 이유.
* vector_retrieval/keyword_retrieval: 실제 순위·점수·각 20개 상한.
* rank_fusion: 실제 계산에 사용한 벡터/키워드 RRF 기여, 역할/구조 가산점,
  최종 점수·순위. 24개 제한 밖 후보도 candidate_limit으로 표시한다.
* evidence_selection: 모델에 전달할 후보, 모델이 반환한 ID, 최종 선택 ID,
  모델 미선정과 서비스의 8개 제한에 의한 제외를 구분한다.
* relation_lookup: Store 이벤트가 있으면 재기록하지 않는다. 주입된 테스트 gateway에
  Store 계측이 없으면 반환된 결과로만 요약한다. 추가 관계 조회를 하지 않는다.
* answer_generation/answer_validation: 실제 생성·규칙/인용 검사·기존 모델 검증 이벤트,
  재생성 횟수, 거부 및 최종 인용 가명 ID. 검증을 다시 실행하지 않는다.
* source_validation: 이미 존재하는 generation 일관성 검사에서 난 오류를 관계 조회
  오류로 잘못 분류하지 않도록 구분한다. 검사 쿼리를 추가하지 않는다.
* final_decision: answer/clarification/abstention/error. 검색 전용 응답은 completed.
  unsupported_intent는 별도 reason으로 보존한다. 총 서비스 처리 시간도 기록한다.

모든 후보 및 인용 ID는 가명이다. 질문·원문·응답·프롬프트를 새 JSONL에 저장하지 않는다.
기존 diagnostic_sink 인터페이스와 데이터 계약은 그대로 유지한다. 이 기존 sink는
새 기본 JSONL과 별개이며, 원래 전달받던 원문 데이터 정책을 이번 패치에서 바꾸지 않았다.

시간 기준 재질문은 현재 정책대로 검색 후 결정한다. 따라서 실제 검색 이벤트를 남긴다.
후보 없음·지원하지 않는 집계처럼 검색을 실행하지 않은 경로는 retrieval_not_executed와
null count를 남긴다. 실행하지 않은 단계의 후보 수를 0으로 조작하지 않는다.
duration_ms는 해당 단계 begin 이후 관찰 시점까지의 시간이다. 여러 검증 이벤트는
같은 검증 단계 시작점을 공유할 수 있으므로 시간을 합산하면 안 된다. 단계 시작이
관찰되지 않은 요약에는 duration_ms를 임의로 붙이지 않는다.

Test-First 및 동작 불변성
------------------------

먼저 기존 기준선과 신규 서비스 테스트를 실행했다: 31 passed, 5 failed,
동시 요청 1개 deselected. 실패는 통합 순위·미실행 검색·실패 단계·역할 가산점 이벤트가
없기 때문이었다. 기존 Prompt 1의 서비스·필터·IO 계약도 구현 기준으로 사용했다.

최종 전체 실행: **428 passed, 6 failed, 1 warning, 22.12초**.
기존 288개와 동작 기준선 30개 모두 통과했다.
남은 6개는 다음 Prompt 6의 LocalModels.select 내부 배치 이벤트 미구현이다.
서비스·필터·HTTP·SQL ON/OFF 계약은 모두 통과했다. skip/xfail로 숨기지 않았으며
전체 테스트의 종료 코드는 1이다. XML은 .local/diagnostics-prompt5.xml에 저장했다.
Ruff 및 형식 검사 통과. 경고는 기존 Starlette/httpx 안내다.

확인한 불변성:

* RRF 점수와 동점 순서, 구조 가산점, 통합 24개 및 근거 8개 상한.
* 같은 모의 응답에서 최종 응답 전체, 근거·인용 ID, 재질문 여부 동일.
* LLM/임베딩 호출 목록과 횟수 동일. 기존 검증의 재생성 0/1회 및 최종 보류 경로 동일.
* 실제 SQLite SQL 문장·순서·횟수 동일. HTTP 상태 코드 및 JSON 본문 동일.
* 동시 요청 6개가 같은 Service를 사용해도 trace별 최종 이벤트 1개씩 분리.
* 진단 준비/저장 오류가 응답을 바꾸지 않음. 원본 변경 오류가 원래 객체로 전파됨.

네 평가 사례의 단계별 근거 보존
------------------------------

data/search_diagnostics.json의 질문·relevant 별칭을 그대로 읽고, 합성 projected fact
4개 및 결정적 모의 모델로 검증했다. record 별칭과 합성 memory ID는 명시적으로 연결했다.

================= ====== =============== ====== ======== ========
사례              필터   벡터/키워드 합집합 통합   최종 근거 최종 인용
================= ====== =============== ====== ======== ========
synonym_when      유지   유지            유지   유지     유지
number_less       유지   유지            유지   유지     유지
unit_conversion   유지   유지            유지   유지     유지
unknown_when      유지   유지            유지   유지     유지
================= ====== =============== ====== ======== ========

이 제한된 조건에서 관찰된 최초 손실 단계는 없다. 실제 추출·실제 LLM·전체 평가 데이터의
End-to-End 실행은 아니므로 과거 실패가 해결됐다거나 정확도가 개선됐다고 주장하지 않는다.

성능 측정
---------

합성 기억 30개, 모의 모델/Store, 실제 Service.answer 경로를 측정했다.
모드별 10회 예열 후 100회씩 5라운드 실행했고 순서를 교차했다. 시간 측정 때는
tracemalloc을 끄고, 메모리는 별도 요청 1회의 Python 할당 최대값을 측정했다.

================= ===================== =====================
모드              요청당 시간 중앙값    Python 할당 최대값
================= ===================== =====================
OFF               0.494480 ms           71,080 bytes
ON / 메모리       1.128347 ms           130,375 bytes
ON / JSONL        1.611303 ms           289,401 bytes
================= ===================== =====================

실제 DB/모델 서버/HTTP 비용을 포함하지 않으며 메모리 값은 RSS가 아니다.
실서비스 오버헤드 비율이나 성능 합격 기준으로 일반화하지 않는다.
원시 측정값: .local/service-benchmark/result.json.

다음 단계 및 실행
-----------------

Prompt 6에서 모델 내부 4개 단위 배치의 전달/선정/배치 통합/내부 상한 손실을 계측한다.
현재 서비스는 모델이 이미 잘라 반환한 ID 이전의 배치 결과를 관찰하지 못한다.
facts의 상세 query_plan 출처와 grounding/answer_review의 더 세밀한 검증 분기는
후속 단계에 남아 있다. 실패 원인 전체 집계·오프라인 분석 도구도 아직 미구현이다.

저장소 루트에서 테스트 전용 basetemp를 사용한다::

    .\.venv\Scripts\python.exe -B -m pytest -q --basetemp=.local/pytest-prompt5-final --tb=line --junitxml=.local/diagnostics-prompt5.xml
    .\.venv\Scripts\python.exe -B -m tests.diagnostics.benchmark_service

이번 변경은 아직 커밋하지 않았다. 이전 버전 보관 브랜치는 유지했다.
