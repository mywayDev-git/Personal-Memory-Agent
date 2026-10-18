공통 SearchTrace 구현 보고서 — Prompt 2
=====================================

2026-10-17 (Asia/Seoul)

변경 범위
---------

* pma/diagnostics.py: SearchTrace, start_trace/current_trace, record_event,
  record_candidates, JSONL 저장 및 종료, Stage/Reason/Status/Source 상수.
* tests/diagnostics/test_trace_core.py: 추가 안전성 테스트 15개.
* tests/diagnostics/benchmark_trace.py: 합성 입력을 사용하는 수집기 단독 성능 측정.
* 이 보고서 및 기존 README의 진행 상태 링크.

서비스·스토어·모델·설정·프롬프트·API·DB 스키마는 이번 단계에서 수정하지 않았다.
작업 시작 전에 존재하던 미커밋 변경을 유지했다. 새 모듈은 표준 라이브러리만
사용하며 서비스에 아직 연결되지 않았다.

Test-First 및 회귀 결과
----------------------

구현 전에 기존 trace 계약 및 추가 core 테스트를 실행했다.
43개가 모듈/설정 미구현으로 실패했다. 추가 제한값 검증에서도 테스트를 먼저
실행하여, flush 후 잘림 정보 누락 및 첫 이벤트가 너무 클 때 기록이 사라지는
두 실패를 확인하고 수정했다.

최종 전체 실행은 **350 passed, 37 failed, 1 warning, 18.42초**이다.

* 기존 테스트 288개: 통과.
* 기존 동작 기준선 30개: 통과.
* 기존 공통 Trace 계약 16개 + 추가 core 15개: 모두 통과.
* 모델 선택 입력 0개 계약 1개: 통과. 기존 동작상 호출·배치 이벤트가 없어야 한다.
* 필터 계측 12개, Store/HTTP 계측 4개, 모델 계측 6개,
  설정·서비스 계약 15개: 아직 연결하지 않아 실패한다.

실패를 skip/xfail로 가리지 않았다. 전체 명령의 종료 코드는 1이다.
기계 판독 결과는 .local/diagnostics-prompt2.xml 에 저장했다.
Ruff 검사와 형식 정리는 통과했다.
일반 실행 환경에서 비동기·스레드 테스트와 전체 회귀를 수행했다.
제한 환경의 asyncio 대기를 운영 코드 변경으로 우회하지 않았다.

공통 모듈 계약
--------------

start_trace의 기본 enabled는 False이다. OFF에서는 SearchTrace 객체를 만들거나
후보를 순회하거나 파일을 열지 않는다. 호출자는 후보 목록 생성 같은 준비 작업도
current_trace() 확인 뒤에 수행해야 한다. Python이 함수 호출 전에 계산하는 인자까지
수집기가 차단할 수는 없다.

활성 scope는 ContextVar로 연결한다. 중첩 scope 종료 및 예외 시 이전 값을 복원한다.
비활성 중첩 scope는 바깥 수집기에 이벤트를 보내지 않는다. 서로 다른 요청은 각각
start_trace scope를 생성해야 한다. 동일 요청이 만든 async 작업은 문맥을 상속한다.

memory_ref, record_ref, relation_ref는 요청 UUID와 종류별 순번으로 구성한다.
원래 ID와의 대응은 SearchTrace 객체에만 존재한다. 합성 평가에서는 알려진 oracle ID를
trace.memory_ref로 변환해 관찰된 후보와 비교할 수 있다. 종료 이후 이미 발급한 ID의
조회는 가능하며, 새로운 ID는 추가하지 않는다. 종류가 다른 ID를 섞지 않는다.
record_id와 memory_id의 출처 연결 자체는 향후 store 계측에서 관찰해야 한다.

record_event는 허용된 stage, 상태, reason, 숫자, bool, 발급된 가명 참조만 수집한다.
질문·원문·인물·장소·프롬프트·응답·임베딩 필드는 저장하지 않는다. 중첩 후보와
score_components도 허용 목록을 적용한다. 허용된 key에 넣은 임의 문자열이나 다른
요청에서 발급한 참조도 그대로 저장하지 않는다. NaN/Infinity는 저장하지 않는다.
score는 실제 유한 숫자를 보존하며 순위를 새로 계산하지 않는다.
events 속성은 복사본을 반환해 외부 수정이 저장 내용을 바꾸지 못하게 한다.

elapsed_ms는 요청 trace 생성 이후의 시간이다. 호출자가 측정한 단계별 시간은
duration_ms에 넣는다. 측정하지 않은 실행 시간을 임의 추정하지 않는다.
not_executed의 input_count/output_count는 null이다. 빈 검색 결과인 0과 구분한다.

JSONL 및 실패 처리
-----------------

path가 명시된 경우에만 종료 시 저장한다. 경로 미지정은 인메모리 수집만 수행한다.
부모 디렉터리를 자동 생성하지 않는다. 잘못된 경로, 기록·직렬화 오류가 호출자의
정상 반환이나 원래 예외를 바꾸지 않는다. 실패 메시지 원문을 로그에 남기지 않는다.
recording_failed/storage_failed는 메모리상의 상태로 확인할 수 있다.

write_jsonl은 성공적으로 저장한 이벤트를 다시 저장하지 않는다. finish_trace는
반복 호출해도 중복 저장하지 않는다. 쓰기 실패 후 파일에는 부분 기록이 남을 수
있으므로, 향후 오프라인 분석기는 손상된 JSONL을 완전한 trace로 간주하면 안 된다.

파일 쓰기는 프로세스 안의 스레드 간 잠금으로 보호한다. 여러 프로세스가 하나의
파일에 동시에 기록하는 기능은 보장하지 않으며 프로세스별 경로를 사용해야 한다.
이 단계에서는 파일 회전·보존 기간 정책을 추가하지 않았다.

기본 이벤트 한도는 4,096개, 직렬화 크기 한도는 4MiB이다. 이벤트별 후보·참조 목록은
각각 4,096개까지만 관찰하고, 종류별 가명 매핑도 상한을 둔다. 한도 초과 시
truncated=True를 기록한다. 마지막에 한도와 별도로 작은 trace_summary 이벤트를
남겨 첫 이벤트가 저장되지 못했거나 이전 이벤트를 이미 flush한 경우에도 잘림을
관찰할 수 있다. 잘린 trace의 후보 부재를 검색 탈락으로 확정해서는 안 된다.

성능 측정
---------

수집기만 측정했다. LLM/DB/서비스 응답 시간 또는 실제 요청의 성능 보장은 아니다.
합성 요청당 이벤트 5개, 그중 4개에 후보 24개를 넣었다. 10회 예열 후 100회씩
5개 묶음을 실행한 요청당 평균의 중앙값이다. 시간 측정에서는 tracemalloc을 끈다.

================= ==================== ==============================
모드              요청당 시간 중앙값   별도 1회 Python 할당 최대값
================= ==================== ==============================
OFF               0.000874 ms          1,264 bytes
ON / 메모리       0.262382 ms          47,336 bytes
ON / JSONL 저장   0.606341 ms          213,313 bytes
================= ==================== ==============================

메모리 값은 tracemalloc으로 관찰한 Python 할당 최대값이며 프로세스 RSS가 아니다.
실제 애플리케이션에 아직 연결하지 않아 검색·답변의 ON/OFF 오버헤드는 미측정이다.
측정치로 임의의 성능 합격 기준을 만들지 않았다.
원시 측정값은 .local/trace-benchmark/result.json 에 저장했다.

재실행 명령
-----------

저장소 루트에서::

    .\.venv\Scripts\python.exe -B -m pytest -q tests/diagnostics/test_trace_core.py --basetemp=.local/pytest-core
    .\.venv\Scripts\python.exe -B -m pytest -q --basetemp=.local/pytest-trace-full --tb=line --junitxml=.local/diagnostics-prompt2.xml
    .\.venv\Scripts\python.exe -B -m tests.diagnostics.benchmark_trace
    .\.venv\Scripts\python.exe -B -m ruff check pma/diagnostics.py tests/diagnostics

테스트 전용 basetemp만 지정한다. pytest는 해당 경로를 재실행 시 정리한다.
다음 Prompt 3에서 설정을 연결한다. 현재 검색 결과의 단계별 추적 및 API 자동
수집은 아직 구현 완료가 아니며, 후속 계측 테스트의 실패를 그대로 유지한다.
