검증·HTTP 연결·오프라인 분석 — Prompt 8~10
========================================

2026-10-18 (Asia/Seoul), codex/search-diagnostics-v1.

Prompt 8
--------

grounding.py의 실제 규칙 분기에서 수량·색상·역할·관계 실패를 관찰한다.
answer_review.py는 기존 검증 실행·항목 판정·질문 미충족·과도한 보류·재생성·최종
결과를 기록한다. validation_type, executed, passed/status, reason_code,
evidence_refs, retry_count, elapsed_ms를 사용한다. 정확한 실패 근거를
연결할 수 없으면 evidence_refs=null이다. 원문/모델 사유 전문은 저장하지 않는다.

서비스는 실제 legacy/review 정책 경로를 표시한다. 기능 플래그를 켜지 않으며,
프롬프트·임계값·최대 재생성 1회·추가 모델 호출 수를 바꾸지 않았다.
정상/수량/색상/역할/관계/없는 ID/오류/재생성 0·1회/보류/수집 실패를 확인했다.
테스트 선행: 신규 5 failed, 1 passed 확인 후 구현. 최종 신규 검증 테스트 10개.

Prompt 9
--------

web.py에 외부 ASGI 진단 middleware를 등록했다. POST /api/v1/search 및
/api/v1/answers만 설정 ON일 때 시작하고 정상·인증 오류·입력 오류·모델 오류·
예외에서 종료한다. 서비스/하위 모듈은 같은 trace_id를 재사용한다.
응답 본문·헤더에 trace_id를 추가하지 않으며 인증·세션·상태 코드를 유지한다.
요청 및 응답 본문을 진단 middleware가 읽거나 저장하지 않는다.
threadpool 전달과 동시 요청 분리, 후속 요청 누수 없음, 파일 기록 실패를 검증했다.
테스트 선행: HTTP lifecycle 1 failed, 저장 실패 격리 1 passed 확인 후 구현.
최종 신규 HTTP 테스트 5개. 기존 HTTP ON/OFF 및 SQL 회귀도 실행했다.

현재 QueryInput은 question/filters/today만 받는다. 대화 이력/이전 질문 문맥을
받지 않으며 이번 단계에서 API를 확장하지 않았다. OFF는 파일을 쓰지 않는다.

Prompt 10
---------

evaluation/diagnose_search.py와 diagnose_search_README.rst 추가.
data/search_diagnostics.json의 relevant는 기록 별칭이고, 시나리오의
supporting_records는 인덱스이며 대시보드 gold_groups는 메모리 그룹임을
먼저 확인했다. ID를 만들어 넣거나 데이터·정답을 수정하지 않았다.

읽기 전용 lookup_ref와 평가에서 명시적으로 호출하는 capture_binding으로
가명 ID를 연결한다. 기본 로그에 매핑을 자동 기록하지 않는다. 연결이 없으면
null/unknown으로 처리한다. 생성물은 diagnostic_summary.json,
diagnostic_cases.json, diagnostic_report.md 세 가지다.

부분·완전 근거 회수, 그룹별 대안, 검색 분기 합집합, fusion 구조 후보 복구,
Recall@K와 실제 탈락 분리, 기록 단위 매핑, 없는 정답/매핑, 잘린 Trace,
누락 순번, 미실행 단계, 보류·재질문 라벨, 잘못된 JSONL, 보고서 출력을 검증했다.
구현 전 신규 테스트는 모듈 부재로 수집 오류, 최종 지표 테스트 11개 통과.

모의 모델 + 실제 임시 SQLite/Service + 기존 합성 질문 24개 통합 확인을 실행했다.
22개 근거 평가 가능, 정답 미지정 2개. 구조 필터 최초 손실 11개가 관찰되었으나
모의 추출/상수 벡터/모의 선정·생성의 결과다. 제품 정확도나 운영 개선 순위로
해석하지 않는다. 확인된 단계가 하나이므로 TOP 5를 채우려고 원인을 만들지 않았다.
실제 LLM End-to-End는 실행하지 않았다. 의미적 정답률은 null이다.

산출물: .local/diagnostics-prompt10/synthetic-usgwtswg/diagnostic_report.md 및
동일 폴더의 JSON 두 개. without-bindings 하위 폴더는 연결 정보 없는 평가 예시다.
CLI도 별도 실행하여 .local/diagnostics-prompt10/cli-verified에 세 파일 생성을 확인했다.

공통 검증 및 성능
----------------

기존 검색 순위·점수·필터·선정·답변·재질문·호출 횟수·SQL 불변성 테스트를 유지한다.
원래 모델 프롬프트나 서비스 정책을 고쳐 테스트를 맞추지 않았다.
전체 회귀 최종 결과: 499 passed, 기존 Starlette 경고 1개, 22.25초.
.local/diagnostics-prompt810.xml에 기록했다. Ruff 및 git diff --check 통과.

30개 합성 근거 서비스 요청, 모의 모델/스토어, 준비 10회 + 5라운드×100회::

    OFF        0.516028 ms, Python peak  74,680 bytes
    ON memory  3.292081 ms, Python peak 264,136 bytes
    ON JSONL   4.467671 ms, Python peak 646,439 bytes

HTTP TestClient, 빈 SQLite 결과, 준비 5회 + 모드별 30회 중앙값::

    OFF        3.449750 ms, Python peak  63,479 bytes
    ON memory  3.850700 ms, Python peak  75,289 bytes
    ON JSONL   4.351950 ms, Python peak 208,219 bytes

HTTP 측정은 모드 순차 실행이며 참고용이다. Python peak는 RSS가 아니다.
실제 모델/서버 지연을 포함하지 않는다. 평가 CLI의 24질문 분석+세 파일 출력은
프로세스 시작 포함 단일 실행 약 166ms였다. 모두 재현용 합성 측정이다.

남은 운영 평가
--------------

실제 모델 실행의 trace와 명시적 ID 연결 파일, 검토된 답변 가능/정답 라벨이 있어야
운영 원인별 TOP 5 및 개선 효과를 평가할 수 있다. 현재 패치는 관찰 기능이며
검색 정확도 개선이나 정책 변경을 수행하지 않는다.
