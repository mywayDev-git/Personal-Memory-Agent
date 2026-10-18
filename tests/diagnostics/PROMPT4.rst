Store 검색 스냅샷·관계 조회 계측 — Prompt 4
========================================

2026-10-17 (Asia/Seoul), 개발 브랜치 codex/search-diagnostics-v1.
이전 버전 보관 브랜치와 커밋은 변경하지 않았다.

수정 파일과 동작
----------------

* pma/store.py: snapshot, links 및 진단 전용 helper 2개.
* tests/diagnostics/test_store.py: 실제 SQLite 기반 테스트 19개.
* tests/diagnostics/benchmark_store.py: 합성 Store 단독 측정 도구.
* 이 보고서와 테스트 README의 진행 상태 링크.

snapshot에서는 검색 결과에 실제 포함된 memory/record 가명 참조, fact 보유 여부,
embedding 보유 여부, record 연결 여부, 반환 개수, 조회 시간을 기록한다.
전체 DB 기억 수는 기존 쿼리로 관찰하지 못하므로 input_count=null이다.
INNER JOIN 또는 WHERE 조건에서 사라진 기억의 존재와 제외 이유는 추측하지 않고
unobserved_reason=not_observed로 기록한다. 추가 전체 조회를 실행하지 않는다.

links에서는 기존 코드가 이미 정렬한 조회 대상 ID를 재사용한다. generator를
진단 때문에 먼저 소비하거나 다시 순회하지 않는다. 반환된 관계 ID, 양쪽 기억과
원본 record의 가명 참조, 관계 개수, 조회 시간을 기록한다.
관계 확장이나 관계 추론·저장은 추가하지 않았다.

memory_ids=None이면 기억별 입력 집합이 지정되지 않은 것이므로 input_count와
evidence_refs는 null이다. 명시적인 빈 집합이면 기존처럼 DB 연결 없이 []를 반환하고
input_count=0, output_count=0, executed=False를 기록한다. 이 경우 조회 요청의 결과를
알고 있으므로 status=completed이며, 아예 관찰하지 않은 단계의 not_executed와 구분한다.
record_id로 제한한 조회의 대상 record도 가명으로 기록한다.

트랜잭션 및 오류 격리
--------------------

진단용 후보 생성과 이벤트 저장은 기존 트랜잭션을 닫은 뒤 수행한다.
진단 OFF에서는 Trace 확인 후 바로 통과하며 타이머·가명 ID·후보 목록을 만들지 않는다.
SQL, 쿼리 인자, 정렬, 반환값은 보존했다. DB 연결 실패 시 원래 예외 객체가 그대로
전파되며 진단 코드가 다른 예외로 가리지 않는다. 진단 참조 생성이나 기록 실패는
정상 조회 결과를 바꾸지 않고 trace.recording_failed로 표시한다.

DB 예외 시 성공 snapshot/relation 이벤트를 만들지 않는다. 요청 전체 오류 이벤트는
후속 서비스 생명주기 계측에서 처리해야 한다.

테스트 먼저 작성한 결과
-----------------------

계측 전 신규 Store 테스트 16개 중 10개가 이벤트 미생성으로 실패했고, 기존 오류
보존·OFF 경로 등 6개는 통과했다. 계측 후 16개가 모두 통과했다.
트랜잭션 종료 후 이벤트 생성과 가명 참조 생성 오류의 격리 검증 3개를 추가했고
최종 신규 테스트 19개 모두 통과했다.
Prompt 1의 snapshot fact 누락/embedding 비관찰 계약도 통과했다.

검증한 사례:

* 정상 snapshot: 후보 순서, generation, 모든 반환 필드 동일.
* fact 누락: 후보는 남고 has_fact=False.
* embedding 누락: 기존 JOIN 때문에 후보가 사라져도 이유를 새로 추정하지 않음.
* record 연결 누락: fixture에서 만든 dangling FK를 기존 JOIN이 제외하며, 추가 조회 없음.
* 관계 0개/복수 관계/전체 조회/부분 집합/record 제한/빈 집합/generator 입력.
* SQL 문장·순서·연결 횟수의 ON/OFF 동일성. PRAGMA, BEGIN, COMMIT도 비교.
* 트랜잭션 종료 뒤 이벤트 작성, 원문·실제 ID 비노출.
* 진단 기록·준비 오류 격리, DB 예외 객체 보존.

별도 소스 대조에서 Store의 SQL 문자열 79개가 HEAD와 동일함을 확인했다.
검색 순위·점수·Top-K·근거·답변·모델 호출 수는 기존 기준선 30개가 계속 통과했다.
이번 단계에 모델 호출이나 DB 스키마 변경은 없다.

전체 회귀 결과
--------------

**389 passed, 30 failed, 1 warning, 26.39초**.
기존 288개와 기준선 30개를 포함해 기존 통과 테스트가 유지되었다.
남은 실패는 필터 12개, 서비스 기반 SQL/HTTP 통합 3개, 모델 6개,
서비스 단계 추적 9개다. 설정 ON만으로 요청 trace가 아직 시작되지 않아서 남는
통합 실패이며, 이번 Store 직접 호출 테스트에서는 명시적인 활성 trace로 검증했다.
실패를 skip/xfail로 가리지 않았다. 전체 명령의 종료 코드는 1이다.
XML: .local/diagnostics-prompt4.xml. Ruff 검사 및 형식 검사 통과.
경고는 기존 Starlette/httpx 사용 중단 예정 안내다.

성능 측정과 한계
---------------

합성 기억 24개와 명시적 관계 23개에 대해 snapshot 1회 + links 1회를 묶어 측정했다.
모델 서버는 사용하지 않았다. 다른 회귀 테스트가 끝난 뒤 단독 실행 결과를 기록한다.
모드별 10회 예열 후 100묶음씩 5회 측정한 평균의 중앙값이다.

================= ============= ======================== =====================
모드              중앙값        5회 측정의 범위          Python 할당 최대값
================= ============= ======================== =====================
OFF               4.483 ms      4.316 ~ 8.758 ms         270,147 bytes
ON / 메모리       9.084 ms      8.755 ~ 9.222 ms         316,288 bytes
ON / JSONL        5.162 ms      4.918 ~ 7.209 ms         316,284 bytes
================= ============= ======================== =====================

시간 측정 중 tracemalloc은 비활성이다. 메모리 값은 별도 한 묶음에서 관찰한 Python
할당 최대값이며 프로세스 RSS가 아니다. 시간은 실제 SQLite I/O를 포함하며 환경
변동이 크다. 파일 저장 모드가 메모리 모드보다 빠르게 측정된 점에서도 이 값의
차이를 순수 계측 오버헤드나 성능 개선 효과로 해석할 수 없다. 임의의 성능 합격
기준을 만들지 않았다. 실제 서비스 요청 전체의 오버헤드는 아직 미측정이다.
원시 결과: .local/store-benchmark/result.json.

재실행 및 다음 단계
-------------------

저장소 루트에서 테스트 전용 basetemp만 지정한다::

    .\.venv\Scripts\python.exe -B -m pytest -q tests/diagnostics/test_store.py --basetemp=.local/pytest-store
    .\.venv\Scripts\python.exe -B -m pytest -q --basetemp=.local/pytest-prompt4-full --tb=line --junitxml=.local/diagnostics-prompt4.xml
    .\.venv\Scripts\python.exe -B -m tests.diagnostics.benchmark_store

다음은 Prompt 5의 서비스 필터·검색·순위·최종 답변 계측이다.
Store 이벤트가 활성 trace에 연결되지만, 환경변수만 켜서 HTTP 질문의 JSONL이
자동 수집되는 기능은 아직 완료되지 않았다. 서비스 계측 시 기존 Store 이벤트와
중복 집계하지 않아야 한다.
