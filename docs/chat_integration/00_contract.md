# 채팅 통합 구현 계약 (2026-10-19)

## Step 0 — 실제 코드 조사

시작 브랜치 `codex/figma-redesign`의 HEAD와 모든 미커밋 변경을 유지하여
`codex/chat-memory-integration`을 생성했다. 기존 사용자 변경을 리셋하지 않는다.

- Python 요구 버전은 3.14이다. `except TypeError, ValueError:`는 이 버전에서
  유효한 구문이며 compileall이 통과했다. Windows 기본 python 별칭은 실행 불가하여
  기존 `.venv/Scripts/python.exe`를 읽어 사용한다. 환경 설치/변경은 하지 않는다.
- `Service.search(question, filters=None, today=None)`는 모델 슬롯을 획득하고
  `_search(...)[1]` 사전을 반환한다. `_search`는 `(generation, result)` 튜플이다.
  `answer` → `_answer`는 같은 검색 결과에 status/items 등을 추가한 사전이다.
- 검색 입력: question(1..1000), filters(date_from/date_to ISO 날짜), today(ISO 날짜).
  결과: status, filters, results, query_plan, search_keywords, keyword_terms,
  search_audit, facts_pending, connections. results의 id는 memory ID이며 record_id,
  version, source_text, evidence(quote/start/end)를 포함한다. revision_id는 freeze에서
  실제 revisions와 대조해 추가한다. 기존 API와 Vector/Keyword/RRF는 유지한다.
- LocalModels.understand/answer/structured는 기존 로컬 Qwen 호출 경로이며
  ChatLocalModels가 채팅 전용 검토를 추가한다. QUERY/ANSWER 스키마는 유지한다.
- 이미 ChatEngine, automatic.run, ChatStore, 자동/일반/기억/혼합 모드, 출처 검증,
  요청 중복 방지, 동시 생성 차단, 재시도/취소, 채팅 UI가 있다. 최초 진입은 기록
  화면이므로 Step 5에서 채팅 기본 진입으로 변경한다.
- DB는 settings.data_dir/memory.db, WAL, 연결당 FK/secure_delete 설정,
  쓰기는 BEGIN IMMEDIATE, 예외 시 rollback, 종료 시 close. 현재 user_version=5.
  채팅 원문 변경/삭제 트리거가 같은 transaction에서 무효화하므로 같은 파일을
  확장한다. 별도 DB는 현재 원자성을 잃는다. 원본 기록 테이블은 변경하지 않는다.
- 인증은 단일 로컬 계정 bootstrap/cookie/CSRF, 정확한 Host/Origin 검증이다.
  다중 사용자 로그인은 없다. 신뢰된 서버 owner는 local-account이며 API 입력으로
  owner를 받지 않는다. 기존 capture_session_owners를 재사용해 채팅 접근을 격리한다.
- UI는 빌드 없는 JS module/CSS/HTML. 기존 검색/답변 화면과 채팅 화면을 유지한다.
- facts.query_plan/compatible, grounding.claims_supported/grounded_response,
  answer_review 검토는 기존 경로를 재사용한다. evaluation에는 저장소/지표 및
  합성 평가 스크립트가 있으며 실모델 결과를 mock 결과로 대체 보고하지 않는다.

## 순차 구현 계획

1. schemas에 상태 계약 추가, migrations에 재실행 가능한 부가 테이블 추가.
   chat_context/version, chat_retrieval_runs, chat_clarifications. 기존 메시지는
   사용자 질문+assistant 응답을 한 행에 보관하는 계약을 유지한다.
   client_message_id는 기존 request_id의 API 별칭이다. 별도 합의 DDL은 첨부되지
   않았으므로 실제 기존 스키마와 충돌하지 않는 확장만 한다.
2. context/router 모듈: bounded context, 보수적인 규칙 분류, reason_code,
   모델 실패 안전 fallback. 기존 automatic 경로에 연결한다.
3. retrieval 모듈과 공개 locked-search 어댑터: 이미 모델 슬롯을 보유한 채팅에서
   Service.search를 재호출하면 비재진입 슬롯에 걸리므로 슬롯 내 공개 경로를 추가한다.
   검색 코어/랭킹 변경 없이 원문 freeze를 재사용한다.
4. 기존 ChatEngine을 ChatOrchestrator로 호환 노출하고 상태/검색 이력을 원자 저장.
   오래된 대화는 사용자 질문만 제한 길이로 요약하며 사실 근거로 취급하지 않는다.
5. 메시지 페이지 조회, 확인 응답, 인용 조회 API 추가. 기존 UI 경로 유지,
   인용 열기 시 현재 원문 유효성 확인.
6. 임시 DB 기반 store/router/API/통합 테스트 및 기존 회귀, 정량값/미실행 구분 보고.

## 초기 검사

- compileall: 통과.
- Ruff: 기존 tests/test_startup_lock.py import 순서 I001 1건.
- pytest: 127개 수집. 기본 임시 폴더 사용 실행에서 오류/지연이 발생하여
  저장소 내 전용 임시 폴더로 재실행하고 최종 보고서에 기록한다.
- `.local`, `.venv`, 운영 DB, 개인 기록은 수정하지 않는다.
