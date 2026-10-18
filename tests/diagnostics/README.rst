검색 진단 Test-First 기준선 — Prompt 1
====================================

작성일: 2026-10-17 (Asia/Seoul)

후속 진행: 공통 Trace 모듈은 ``PROMPT2.rst``, 설정은 ``PROMPT3.rst``,
Store 계측은 ``PROMPT4.rst``, 서비스 계측은 ``PROMPT5.rst``,
모델 계측은 ``PROMPT6.rst``, 질문 조건 계측 및 최신 결과는 ``PROMPT7.rst`` 를 참조한다.
검증·HTTP 연결·오프라인 분석과 최종 결과는 ``PROMPT8-10.rst`` 를 참조한다.
아래 결과는 구현 이전 Prompt 1의 기준선 기록이다.

범위와 실행 결과
----------------

운영 코드, 모델, 프롬프트, 설정, DB 스키마, 평가 데이터는 변경하지 않았다.
작업 시작 당시 존재하던 미커밋 변경을 포함한 작업 폴더가 기준선이다.
HEAD는 ``77e15e1ba1812494ceb376b20abf6833add74e6a`` 이다.

Python 3.14.8에서 전체 실행: **318 passed, 54 failed, 1 warning, 17.99초**.
기존 288개가 모두 통과했고 새 기준선 테스트 30개가 통과했다.
새 진단 계약 테스트 54개는 다음과 같이 실패했다.

* 40개: ``pma.diagnostics`` 모듈 미구현 (ModuleNotFoundError).
* 9개: AppSettings 생성자의 ``diagnostics`` 필드 미구현 (TypeError).
* 5개: AppSettings 인스턴스의 ``diagnostics`` 속성 미구현 (AttributeError).

실패를 skip/xfail로 숨기지 않았다. 따라서 이 단계의 전체 pytest 종료 코드는 1이다.
상위 인터페이스가 없어 실패한 테스트의 후속 assertion은 아직 실행되지 않았다.
이 결과는 진단 ON의 동작 동일성이나 개인정보 보호가 이미 검증되었다는 뜻이 아니다.
경고는 기존 Starlette TestClient의 httpx 사용 중단 예정 안내다.
신규 Python 파일의 Ruff 검사 및 형식 검사는 통과했다.

테스트 구성
-----------

* ``helpers.py``: 합성 snapshot, 결정적 모델 응답, 모델 및 Store 호출 기록.
  Store 메서드 호출 수와 실제 SQL 조회 수는 구분한다.
* ``test_baseline.py`` (30개, 통과): RRF 점수, 중복 검색 후보 통합,
  동점 순서, 구조 가산점, 통합 24개/최종 8개 상한, 4개 단위 모델 선택,
  기존 sink의 성공·실패 시 결과 동일성, 예외와 fallback, 근거 없음,
  검증 거부, 재질문, 실제 기존 필터 분기, 네 평가 사례의 검색 경로.
* ``test_filter_contract.py`` (12개, 예상 실패): 최초 제외 이유와 미실행
  단계의 count가 0으로 조작되지 않는지 검증한다.
* ``test_trace_contract.py`` (31개, 예상 실패): 이벤트 스키마와 순서,
  가명 ID, 인메모리 대응, 중첩·비동기·스레드·연속 요청 격리,
  원문 및 중첩 개인정보 제외, 직렬화 실패, 파일 저장 실패,
  환경변수, 전체 응답·모델 호출·Store 호출 ON/OFF 비교,
  단계별 순위·점수·최종 인용, 오류 종료와 ContextVar 정리.
* ``test_io_contract.py`` (4개, 예상 실패): 실제 SQLite trace callback으로
  모든 SQL 문장의 순서와 내용을 비교한다. 실제 HTTP 응답의 상태·본문을
  비교하고, snapshot의 fact 누락 및 관찰 불가능한 제외 원인을 확인한다.
* ``test_model_contract.py`` (7개, 예상 실패): 실제 LocalModels.select의
  배치 처리, 프롬프트·스키마·옵션·호출 수·반환값 동일성, 배치 오류 관찰.
  모델 HTTP 호출만 모의 함수로 대체하며 새 재시도 정책을 요구하지 않는다.

기존 ``tests/test_answer_review.py``의 재생성 상한·검증 오류·잘못된 인용 테스트와
``tests/test_api_search.py``의 HTTP 오류·원본 변경 테스트도 전체 회귀에 포함했다.
모든 신규 테스트는 실제 LLM/임베딩 서버에 접속하지 않는다.

다음 구현 단계의 제안 인터페이스
------------------------------

``pma.diagnostics`` 에 다음 계약을 둔다. 운영 구현은 이번 단계에 추가하지 않았다.

* ``start_trace(enabled=True, path=None)``: context manager.
  종료 시 JSONL 저장 및 context 복원, 예외를 가리지 않아야 한다.
  path 없는 활성 trace는 메모리에서만 수집한다.
* ``current_trace()``: 현재 요청 trace, 없으면 None.
* ``record_event(Stage, **safe_fields)``: 활성 trace에 안전한 값만 기록.
* ``trace.events``, ``trace.trace_id``, ``trace.memory_ref(memory_id)``.
  memory_ref는 요청 안에서 안정적이며 실제 ID를 로그에 노출하지 않는다.
  평가용 실제 ID 대응은 실행 중 trace 객체를 통해서만 사용한다.
* ``Stage`` 및 ``Reason`` enum. 이벤트의 stage/reason 값은 문자열로 저장한다.
* AppSettings: ``diagnostics=False``, ``diagnostics_path=None``.
  ``PMA_DIAGNOSTICS`` 는 기존 bool 설정처럼 정확히 ``1`` 일 때만 활성화한다.
  경로만 지정해서 진단이 켜져서는 안 된다.

서비스는 외부에서 시작한 활성 trace가 있으면 이를 사용하고, 설정에 의해
직접 시작한 요청 trace는 정상/오류 종료 시 정리한다. HTTP 요청당 final_decision은
한 번만 기록한다. 기존 API 응답에는 trace_id 등 진단 필드를 추가하지 않는다.

이벤트의 공통 필드는 schema_version=pma.search_trace.v1, trace_id, stage,
event_sequence(1부터), status, elapsed_ms이다. 후보 이벤트는 input_count,
output_count, candidates를 사용한다. 후보별 필드는 memory_ref, status,
reason, rank, score, score_components 중 해당되는 값이다.
rank_fusion의 구성 요소 키는 vector, keyword, role, structure이다.
최종 이벤트의 citation_refs는 최종 답변에서 실제로 인용한 기억의 가명 ID다.

evidence_selection 집계 이벤트는 최종 선택된 후보와 evidence_limit으로
잘린 후보를 구분한다. 모델 내부 배치는 evidence_selection_batch로 분리한다.
하위 모듈의 이벤트와 서비스 요약을 중복 집계하지 않도록 구현해야 한다.
미실행 단계는 생략하거나 status=not_executed, count=null로 기록한다.
서비스의 시간 기준 재질문은 현재 검색 후 결정되므로 검색 미실행으로 기록하지 않는다.

필터 reason과 실제 코드의 대응
-----------------------------

* fact_missing: fact가 없음.
* relation_mismatch: compatible의 관계 조건 불일치.
* person_mismatch: compatible의 self 역할 또는 서비스의 명시 인물 불일치.
* status_mismatch: compatible의 event_listing/달리기 상태 조건 불일치.
* quantity_mismatch: quantity_matches 실패.
* requested_object, preference_change, activity_state: 기존 서비스의 해당 분기.
* place_mismatch: 기존 location 제외 분기.
* time_unknown: 날짜 필터가 있지만 사건 날짜가 없거나 불확실함.
* time_mismatch: 사건 날짜가 필터 범위 밖임.

현재 relation_state_or_quantity로 합쳐진 이유를 실제 분기에서 구분하도록 요구한다.
없는 필터를 추가하거나 조건을 재평가하라는 요구가 아니다.
여러 조건이 동시에 어긋난 합성 후보로 최초 제외 순서를 고정했다.

평가 사례 해석과 한계
--------------------

data/search_diagnostics.json의 synthetic 표기와 records/questions/relevant 구조를
확인하여 네 질문을 그대로 읽었다. relevant는 record 별칭이다. 테스트가 만든
record_id와 별칭 사이의 명시적 매핑으로 비교하며 DB ID라고 가정하지 않는다.

* synonym_when: 모의 질문 분석 및 선택에서 fight가 검색 결과에 남는다.
* number_less: units만 검색 결과에 남는다.
* unit_conversion: units만 검색 결과에 남는다.
* unknown_when: unknown_date가 검색 결과에 남는다.

이 테스트는 4개의 합성 projected fact로 검색 경로를 확인한다. 전체 데이터셋의
실제 추출·LLM 선정·최종 답변 정확도 평가가 아니다. 과거 오류의 현재 재현이나
정확도 개선 효과를 확정하지 않는다. 새 계측이 없으므로 단계별 실제 손실 보고와
ON/OFF 성능·메모리 오버헤드는 아직 측정할 수 없다.

실행 명령
---------

저장소 루트 PowerShell에서 실행한다. basetemp는 테스트 전용 경로만 지정한다.
pytest가 재실행 시 해당 경로를 정리하므로 사용자 자료를 넣지 않는다.

기존 동작 기준선만::

    .\.venv\Scripts\python.exe -B -m pytest -q tests/diagnostics/test_baseline.py --basetemp=.local/pytest-diagnostics-baseline

신규 테스트 전체 (현재 예상 종료 코드 1)::

    .\.venv\Scripts\python.exe -B -m pytest -q tests/diagnostics --basetemp=.local/pytest-diagnostics-red --tb=short

전체 회귀 및 기계 판독 결과::

    .\.venv\Scripts\python.exe -B -m pytest -q --basetemp=.local/pytest-diagnostics-full --tb=line --junitxml=.local/diagnostics-test-first.xml

현재 실행의 XML은 ``.local/diagnostics-test-first.xml`` 에 저장했다.
이번 전체 회귀는 앞 단계에서 확인한 제한 환경의 HTTP 테스트 대기를 피하기 위해
일반 권한 실행 환경에서 수행했다. 소스나 테스트를 변경해 환경 오류를 숨기지 않았다.

다음 단계
---------

Prompt 2에서 공통 Trace 모듈을 구현하고 해당 계약 테스트를 통과시킨다.
설정·서비스·스토어·모델 통합 테스트는 Prompt 3 이후 각 계측 단계가 완료될 때까지
실패가 남는 것이 정상이다. 새로운 알고리즘 또는 답변 정책을 도입해 테스트를
맞추지 않는다. 현재 실패는 임시 skip으로 처리하지 않는다.
