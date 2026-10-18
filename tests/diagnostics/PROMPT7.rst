질문 해석·시간 조건·사실 비교 계측 — Prompt 7
===========================================

2026-10-18 (Asia/Seoul), codex/search-diagnostics-v1.

완료 범위
---------

facts.py의 explicit_dates/query_plan/compatible 실제 호출을 관찰한다.
원래 조건식·날짜 파싱·조건 비교 순서·반환값·확인 질문 정책은 유지한다.
facts_diagnostics.py가 개인정보 없는 기록을 조립하며 오류를 격리한다.
compatible의 선택적 diagnostic_id는 서비스 후보의 가명 ID 연결에만 사용한다.

* date_parsing: 기존 파서가 반환한 날짜 조건 유무와 date_certain.
  날짜 값은 저장하지 않는다. 확정된 경계가 없다는 표시는 파서 결과에 대한
  설명이며, 유효하지 않은 날짜와 날짜 표현 부재를 별도 분류하지 않는다.
* query_plan: 관계 종류, 질문 종류, 수량 연산자, 자기 자신·상태 조건,
  시간 앵커, 역할 힌트, 요청 슬롯 및 부정 표현 유무.
* query_condition: 생성 후 날짜 경계별 rule/explicit_input 출처,
  장소·인물·대상 조건 유무, 실제 후보 비교와 적용 또는 우회 이유.
* fact_comparison: 기존 compatible 반환값과 첫 실패 이유를 가명 ID에 연결.
  앞 조건에서 탈락하면 뒤 조건을 평가했다고 기록하지 않는다.
* 최종 확인 질문 이유는 기존 final_decision의 unresolved_time_anchor와 연결된다.

phase=generated/resolved는 조건 생성·정리 단계이며 applied=false이다.
phase=compared에서 실제 수행된 비교만 applied=true로 기록한다.
comparison_bypass는 적용하지 않은 비교이며 passed 필드도 생략한다.
역할 힌트는 hint_only이며 인물에 대한 강제 필터로 표시하지 않는다.
직접 query_plan 호출의 입력 출처는 unknown이다. 서비스에서는 실제 성공한
model_understanding 호출 기록이 있어야 llm으로 표시하며, 규칙 fallback은 rule이다.
날짜 비교는 양쪽 경계가 서로 다른 출처일 수 있어 비교 이벤트 source=unknown,
resolved의 date_from/date_to 이벤트에서 각 경계의 실제 출처를 확인한다.

확인한 기존 동작
----------------

A. 그때 서울숲에서 지연이 원한 선물이 뭐였지?
   날짜가 없으면 needs_time_anchor=true이며 사건 식별 단서가 있어도 재질문한다.
   명시 date_to를 전달하면 기존처럼 시간 앵커 요구를 해제한다.
B. 2026년 10월 3일 달린 기록: 기존 날짜 경계 그대로 생성한다.
C. 그때 없는 장소·인물·사건 질문: 시간 앵커를 요구하지 않는다.
D. 부정 표현: negation_present는 단순 표현 존재 관찰이다. 현재 plan에는
   별도 부정 필터가 없으므로 negation 조건 present=false이다.
   부정문을 새로운 검색 정책으로 해석하거나 기존 상태 필터를 바꾸지 않는다.
E. 5km와 3km 비교 질문: 여러 수량이 있으므로 distance_m=None을 유지한다.
   compare/change에서 기존 관계 필터 우회도 comparison_bypass로 기록한다.

검증
----

먼저 신규 계약 12개가 실패함을 확인한 뒤 구현했다. 최종 신규 테스트 19개.
전체 회귀 473 passed, 기존 Starlette 경고 1개, 21.33초.
결과: .local/diagnostics-prompt7.xml.
마지막 우회 비교의 passed 필드 생략 후 관련 테스트 46개 재검증 통과.
Ruff와 git diff --check 통과.

계획·날짜·필터·재질문 ON/OFF 동일, 부분 날짜 덮어쓰기 출처, 실제 첫 실패,
후속 비교 미실행, 힌트 비강제성, 개인정보 및 임의 문자열 차단,
진단 수집 실패에도 반환·예외가 보존됨을 확인했다.
기존 모델·프롬프트·DB 쿼리·검색 점수·답변 정책은 변경하지 않았다.

성능 및 한계
------------

실행: python -B -m tests.diagnostics.benchmark_service
결과: .local/service-benchmark/result.json.
30개 합성 근거, 모의 모델·스토어, 10회 준비 후 모드별 5라운드 × 100회.

================  ===========  =====================
모드              시간(ms)     Python 최대 할당(bytes)
================  ===========  =====================
OFF               0.521955     74,680
ON 메모리         3.278503     264,087
ON JSONL          4.384234     645,894
================  ===========  =====================

누적 진단의 요청당 추가 시간은 메모리 약 2.757ms, JSONL 약 3.862ms.
후보별 상세 이벤트로 이전 단계보다 기록량이 증가한다. 수집 한도에 도달하면
기존 truncated 요약을 남기므로 이벤트 부재를 탈락 증거로 해석하면 안 된다.
측정은 실제 LLM·DB 지연이나 RSS가 아니며 모델 서버 E2E는 실행하지 않았다.
마지막 passed 생략 수정 전 측정값이며 성능 측정 자체는 참고용 합성 결과다.

다음: Prompt 8, grounding.py/answer_review.py의 답변 거부·수정 이유 추적.
