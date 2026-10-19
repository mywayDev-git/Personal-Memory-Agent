# Chat + Memory 통합 결과 — 2026-10-19

작업 브랜치: `codex/chat-memory-integration`. 시작 시 개발 중이던 변경과 미추적
파일을 보존했다. 커밋/푸시는 하지 않았다. 운영 DB와 개인 기록을 열거나 수정하지
않았고 `.local`, `.venv` 내용 및 모델 설정을 변경하지 않았다.

## 단계별 결과

| 단계 | 결과 |
|---|---|
| 0 | 실제 검색/대화/DB/보안 구조 조사 및 `00_contract.md` 작성. 기존 구현 재사용 결정 |
| 1 | 상태 모델, 부가 마이그레이션, owner 격리, 상태 version 충돌 검사, 메시지 페이지 조회 |
| 2 | 네 가지 routing mode, reason_code, 규칙 우선 분류, 분류 실패 시 기억 검색 fallback |
| 3 | 공개 슬롯 내 검색 어댑터, 기존 검색 코어 재사용, 명시 필터 우선 병합, 인용 원본 재검증 |
| 4 | ChatOrchestrator를 실제 웹 앱에 연결, 생성 진입점 분리, bounded 질문 요약·주제·근거 ID·검색 이력 저장 |
| 5 | 메시지/확인 질문/인용 API, client_message_id 별칭, 채팅 기본 화면, 인용 열기 시 재검증 |
| 6 | 오프라인 통합·회귀 테스트 및 고정 검색 fixture 비교. 실모델/브라우저 평가는 미실행으로 구분 |

기존 ChatEngine/automatic의 일반 대화, 기억 답변, 혼합 답변, 확인 질문, 검토,
최대 검색 3회, 원본 변경 재시도 1회, 취소·시간 제한 기능을 그대로 재사용한다.
기존 `answer_validation=False`, QUERY_SCHEMA/ANSWER_SCHEMA, Vector+Keyword+RRF
설정을 유지했다. `init.py` 대신 실제 Python 패키지 이름인 기존 `__init__.py`를 유지한다.

## API 계약

- 기존 `/api/v1/search`, `/api/v1/answers`, 채팅 세션 생성/목록/상세/삭제 및 메시지
  POST 계약 유지.
- `GET /api/v1/chat/sessions/{id}/messages?offset=0&limit=50`:
  `items`, `total`, `next_offset`; limit은 1..100. DB에서 페이지 범위만 읽는다.
- `POST /api/v1/chat/sessions/{id}/messages`: 기존 request_id 또는
  client_message_id 별칭, question, mode, today, context_message_id, 선택적
  filters(date_from/date_to). 동일 요청 ID의 입력 변경은 409.
- `POST /api/v1/chat/sessions/{id}/clarifications`: 같은 메시지 스키마,
  유효한 확인 질문의 context_message_id 필수. 만료된 선택은 409.
- `GET /api/v1/chat/citations/{id}`: ID는 `message_id:item_index:memory_id`.
  `citation_details[].citation_id`로 제공. 현재 원본 version·revision·quote를
  확인한 `source`, `references` 반환. 변경/삭제 시 SOURCE_CHANGED 409.
- 기존 인증 cookie/CSRF/Origin/Host 정책을 그대로 적용한다. 서버의 신뢰된
  단일 로컬 계정은 local-account이며 클라이언트가 owner를 정할 수 없다.
- 다른 소유자 세션은 404. 다른 소유자에게 등록된 기록은 검색용 snapshot에서
  제외하여 모델 입력 전 차단하고, 인용 저장/조회에서도 재확인한다.

## DB 마이그레이션

동일 memory.db의 기존 원자적 원본 무효화 구조를 유지한다. 원본 records/revisions
스키마는 변경하지 않는다. 기존 chat_sessions/messages/citations는 유지하고
chat_context, chat_retrieval_runs, chat_clarifications, chat_schema_migrations를 추가했다.
확장 버전은 chat_schema_migrations=1이며 호스트 user_version=5와 분리한다.
부가 테이블은 JSON 유효성/FK 검사, 세션 삭제 cascade를 적용한다. 신규 대화에
owner 매핑을 저장하고 기존 매핑 backfill을 재사용한다.

최종 응답·인용·대화 상태·검색 이력은 같은 쓰기 transaction에서 저장한다.
생성 중 외부 상태 갱신이 발생하면 STATE_CONFLICT로 덮어쓰기를 막는다.
원문은 기존 호환용 snapshot 경로를 유지하며 새 context에는 원본을 복제하지 않고
근거 ID만 저장한다. 과거 메시지를 새 기억 DB에 복제하지 않는다.

## 실행한 검사

- 최종 pytest: **143 passed**, 10.03초. 원래 127개 + 신규 16개.
- Ruff: 초기 기존 import 순서 오류 1건을 수정. 최종 검사 결과는 아래 실행 명령으로 재현 가능.
- compileall, 변경된 JS 두 파일의 `node --check`, `git diff --check` 통과.
- TestClient의 httpx 사용 중단 예정 경고 1건. 의존성은 변경하지 않았다.
- 초기 기본 Python 별칭은 실행 불가. 기존 가상환경 Python 3.14.8 사용.
- 초기 sandbox pytest는 임시 폴더 오류 및 Windows asyncio 로컬 socketpair에서
  정지했다. 스택으로 환경 원인을 확인하고 임시 DB 테스트를 권한 조정 후 실행했다.
  변경 전 전체 pytest 완료 결과는 확보하지 못했으며, 통과한 것으로 보고하지 않는다.
  이번 작업에서 멈춘 테스트 프로세스는 확인 후 종료했다.

주요 재현 기준: 다른 owner 접근 404, 동일 요청 재생성 없음, 동시 version 갱신
1건만 성공, 실행 중 메시지 중복 차단, 재시작 시 interrupted 처리, 원본 수정 후
인용 및 캐시 재사용 차단, JSON/FK/SQL 문자열 처리, 마이그레이션 반복 보존,
일반 대화 10턴 검색 0회, 기억 질문 5턴 검색 발생, 모델 오류 후 같은 요청 복구,
기존 검색/답변 API 호환, 인증/CSRF/Host 차단.

재현 명령(저장소 루트, 기존 가상환경 사용):

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .test-tmp-chat-check
.\.venv\Scripts\python.exe -m ruff check pma scripts tests evaluation
.\.venv\Scripts\python.exe -m compileall -q pma scripts tests evaluation
.\.venv\Scripts\python.exe -m evaluation.chat_integration_eval --output docs/chat_integration/offline_metrics.json
node --check pma/static/app.js
node --check pma/static/chat.js
```

## 정량 결과와 해석

`offline_metrics.json`은 기존 tests/test_search_explain.py의 고정 검색 fixture를
사용했다. 실제 검색 코어를 실행하지만 모델과 corpus는 합성 fixture이다.
비교 대상은 현재 기존 공개 검색 경로와 새 어댑터이며 변경 전 실모델 비교가 아니다.

- Routing Accuracy: 10/10. Memory-required Recall: 6/6.
- corpus 크기 1/2/8/12에서 기존/채팅 결과 순서 모두 동일.
- Recall@8: 각각 1/1/1/0.6667, 양 경로 동일. 12건 사례의 4건 누락은 기존
  8건 제한과 같으며 새 회귀가 아니다. 무관 근거 포함 0건.
- MRR: 양 경로 4개 사례 모두 1.0.
- mock 검색 평균/중앙/P95(ms): 기존 0.521/0.453/0.718,
  채팅 0.522/0.459/0.964. 각 경로 20회, 모델 추론 시간은 포함하지 않는다.
- 일반 대화 10턴에서 검색 0회, mock structured 호출 20회(생성+안전 검토).
  동일 request_id 재전송은 추가 생성 0회.

실모델 Citation Precision, Grounded Claim Rate, Unsupported Claim Rate,
Context Continuity Accuracy, Clarification Necessity, 실제 Qwen 호출 횟수와
추론 latency는 **미측정**이다. 원문/인용 단위 검증 통과를 생성 정확도 100%로
해석하면 안 된다. 기존 검색과 신규 대화의 실모델 정확도 향상/하락은 아직 판정 불가다.

## 수정 파일 (이번 작업)

- pma/store.py, pma/service.py, pma/web.py
- pma/chat/api.py, automatic.py, engine.py, schemas.py, store.py
- pma/static/app.js, chat.js
- tests/test_memory_capture.py (owner snapshot 검증 추가)
- tests/test_memory_complete.py (타 owner fixture를 해당 owner 저장소로 생성)
- tests/test_startup_lock.py (기존 Ruff import 순서 수정)

신규: pma/chat/context.py, router.py, retrieval.py, generator.py, orchestrator.py,
migrations/__init__.py; tests/chat/test_integration.py;
evaluation/chat_integration_eval.py; docs/chat_integration/{00_contract.md,REPORT.md,offline_metrics.json}.
시작 전부터 존재하던 다른 수정·미추적 파일은 이번 작업 결과로 계산하지 않는다.

## 알려진 한계와 다음 검증

- 실제 Qwen/BGE 서버를 사용하는 장시간 평가와 브라우저 상호작용/화면 검증은
  실행하지 않았다. JS 구문 검사와 API 테스트만 수행했다.
- 규칙 라우팅은 명확한 경우를 절약하고 나머지는 기존 모델 분류로 넘긴다.
  고정된 10개 사례만으로 실제 한국어 질의 전체 성능을 보장할 수 없다.
- 대화 요약은 최근 오래된 사용자 질문 최대 16개/2,000자 발췌이며, 모델이
  작성하는 의미 요약은 아니다. 개인정보를 확정된 사실로 재사용하지 않는다.
- 저장소 owner 격리는 구현했지만 앱 자체는 기존 단일 로컬 로그인 모델이다.
  다중 계정 로그인/사용자별 모델 인덱스 제품 기능을 새로 만든 것은 아니다.
- 다음 검증은 합성된 인물·시간·부정·동명이인·갈등 기록으로 실모델 평가 후
  인용 클릭/확인 선택/검색 화면 전환/새로고침 복구를 브라우저에서 확인하는 것이다.
