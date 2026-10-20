# 대화 환경 통합 구현 명세

## 기준과 구성

기준 커밋은 `28d9672`이며 `codex/chat-memory-integration`을 해당 커밋까지 fast-forward해 기존 작업을 보존했다. 개인 DB·모델·실행 설정은 변경하지 않는다. 별도 기억 저장소·프런트엔드 프레임워크·외부 서비스는 추가하지 않는다.

기존 `ChatOrchestrator → ChatEngine → automatic.run`이 단일 실행 경로다. 검색은 기존 Service, 인용·사실 검증은 기존 독립 검토, 기록 변경은 기존 Store/MemoryRepository가 담당한다.

| 구성 | 구현 위치 | 역할 |
|---|---|---|
| 정책 | `pma/chat/policy.py` | 명시적 기억 거부, 개인 맥락 제거, 민감 주제의 보수적 제한 |
| 기억 해석 | `pma/chat/interpretation.py` | 정확한 원문 인용, 상태·사건일·주체·조건, 관계 후보 |
| 응답 계획 | `pma/chat/planner.py` | 주 응답 유형·특성, 공개 응답, 서버 액션 생성 |
| 실행·검증 | `pma/chat/automatic.py`, `engine.py` | 검색 질문 구성, 해석→생성→독립 검토 연결 |
| 액션 | `pma/chat/actions.py`, `store.py` | 인증 범위, 버전 검증, 중복 요청, 서버 저장·실행 |
| 업로드 | `pma/imports.py` | 원문 미리보기·원자적 분할 저장·파일 위치 |
| 화면 | `pma/static/conversation-ui.js`, `chat.js`, `imports.js` | 탐색, 근거 패널, 입력, 선택·승인 |

관찰은 사실 검증 완료를 뜻하지 않는다. 해석 모델의 문구는 원문 안에 실제 존재하는 연속 인용이어야 하며, 상태·시각·주체·조건도 그 인용에서 확인한다. 불명인 필드는 비워 둔다. 최종 facts는 독립 검토를 통과한 답변에서만 생성한다.

검증 전 해석·원문 관찰은 일반 설명·제안 모델의 입력에서 제거한다. 제안은 검증된 답변 사실만 참조한다. 개인 기록을 인용했던 과거 AI 답변도 제안 단계의 사실 근거로 재사용하지 않는다. 기억 사용을 끈 경우에는 일반 설명으로 명시된 안전한 대화 맥락만 유지한다. Part/파트·단계 번호와 명시적 완료 날짜를 인용한 원문과 다르게 답하지 않는 독립 검사도 적용한다. 통합 대화 프롬프트 버전은 6이다.

서로 다른 날짜·프로젝트·측정 조건은 합치지 않는다. 관계 후보는 최종 답변 검증을 대체하지 않는다. 동일한 명시적 ISO 날짜·대상·조건의 완료/미완료 문장이 반대인 좁은 경우는 독립적인 문자열·범위 검사로 상대 근거가 누락되지 않게 보존한다. 이 경우도 원문 인용 초안을 기존 독립 검토에 통과시킨다. 일반적인 충돌·정정·시간 관계는 기존 모델 검토와 검증된 표시 메타데이터를 사용한다.

## 응답 유형 계약

유형은 주 유형 하나와 특성 배열을 조합한다. 여러 검색 결과 자체는 명확화 조건이 아니다.

| ID | 유형 | 선택 조건·화면 |
|---|---|---|
| R01 | DIRECT | 검증된 직접 답변, 기본 버튼 없음 |
| R02 | CLARIFY | 원문으로 확인된 실제 복수 대상, 선택 목록 |
| R03 | MULTI_RESULT | 여러 사건을 설명하는 일반 조회 |
| R04 | LATEST | 최신·마지막 상태 질문, 변경 이력 |
| R05 | CONFLICT | 검증된 충돌, 비교·이력 |
| R06 | TIMELINE | 시간순·변경 과정 요청 |
| R07 | PARTIAL | 확인·미확인 항목을 분리 |
| R08 | NO_EVIDENCE | 정상 검색의 근거 부재, 재검색 |
| R09 | LOW_CONFIDENCE | 후보가 있어도 최종 근거가 부족 |
| R10 | COMPARE | 비교 요청, 조건과 출처 구분 |
| R11 | SUMMARY | 기록 요약 |
| R12 | GENERAL | 자동 경로의 일반 대화 |
| R13 | HYBRID | 개인 사실과 일반 제안을 분리하는 특성 |
| R14 | SAVE_CONFIRM | 저장 미리보기·승인, 저장 완료 추정 금지 |
| R15 | CORRECTION | 대상·버전 확인 후 수정 절차 |
| R16 | DELETE_CONFIRM | 대상 원문 확인 후 휴지통 이동 |
| R17 | ERROR | 장애, 재시도 가능 여부·오류 코드 |
| R18 | ACCESS_DENIED | 인증·권한 거부 |
| R19 | FOLLOW_UP | 후속 맥락을 반영한 특성 |
| R20 | ACTION_CHOICES | 액션 선택이라는 정책 분류; 실행 API는 effect로 결과 표현 |
| R21 | MEMORY_CONNECTED | 관련 기억을 연결한 특성 |
| R22 | RESUME_ACTIVITY | 학습·작업 재개, 이어가기·복습 |
| R23 | PAST_EXPERIENCE | 과거 해결 사례, 현재 적용 검토 |
| R24 | NEXT_STEP_SUGGESTION | 다음 단계 요청·선택 가능한 제안 |
| R25 | PROGRESS_REVIEW | 진도 확인·정정 |
| R26 | PLAN_RECONSIDERATION | 기존 결정 재검토 |
| R27 | MEMORY_SUPPRESSED | 명시적 거부·일반 모드, 검색·저장 선호 조회 차단 |

개인 사실·일반 지식·제안은 기존 items와 source_type을 유지한다. 날짜·진도를 반복하는 장황한 제안 대신 짧은 후속 도움을 생성하도록 지시한다. 커리큘럼이 없으면 다음 Part를 사실로 만들지 않는다. 거절·실패한 추천은 재검토하도록 하고, 실제 적용 가능성은 확정하지 않는다.

## API·SQLite

기존 `/api/v1/chat` API를 유지하며 응답에 `response_id`, `conversation_id`, `response_version`, `primary_response_type`, `response_features`, `answer_text`, `grounding_status`, `evidence_refs`, `uncertainty`, `memory_context`, `interpretation`, `ui_actions`, `context_update`, `error_state`를 추가한다. response_id는 메시지 ID, conversation_id는 세션 ID다. 이전 응답에 추가 필드가 없어도 기존 화면이 표시한다.

`evidence_refs`는 기록·버전·원문 위치·사건일·저장일·관련도·인용 구간을 보존한다. 해석의 공개 관찰·관계는 최종 인용 출처로 제한한다. 업로드 출처는 파일명·Unicode 코드 포인트 기준 시작/끝 위치와 원본 기록 버전을 제공한다. 수정된 버전에 원본 파일 위치를 새 위치처럼 적용하지 않는다.

`POST /api/v1/chat/sessions/{sid}/actions/{action_id}`

요청은 `request_id`, `expected_context_version`만 받는다. 클라이언트의 임의 대상·질문·액션 종류는 허용하지 않는다. 서버 액션에는 세션·메시지·대상·질문·원문 버전·권한·만료 정책을 저장한다.

지원 종류: CHOOSE_TARGET, CHOOSE_DATE, CONTINUE, REVIEW, RESUME_TASK, COMPARE, SHOW_HISTORY, SHOW_EVIDENCE, EXPLAIN, PLAN_NEXT, CONFIRM_PROGRESS, SAVE_PROGRESS, CORRECT_RECORD, RETRY_SEARCH, EXPAND_SCOPE, DISMISS. 화면에는 현재 의도에 필요한 종류만 생성한다. CONTINUE는 특정 다음 Part를 추정하지 않는 후속 요청으로 연결한다.

- ACTIVE → LOADING → RESOLVED. 대화·기록 변경 시 EXPIRED.
- 같은 요청 ID 재전송은 같은 결과를 반환한다. 다른 액션에서 같은 요청 ID를 재사용하면 REQUEST_CONFLICT.
- 실행 중인 재클릭은 ACTION_BUSY. 만료는 ACTION_EXPIRED. 처리 실패는 다시 실행할 수 있게 복구한다.
- 후속 메시지는 액션 ID에서 파생한 안정된 요청 ID를 사용하고, 메시지 시작 트랜잭션에서도 맥락 버전을 검사한다.
- 원문 수정·삭제는 저장된 결과를 지우고 액션을 만료시킨다. 삭제된 출처를 캐시 결과로 다시 노출하지 않는다.
- 저장·진도 정정은 기존 미리보기·승인으로 위임한다. 액션 실행 자체가 완료 상태를 DB에 쓰지 않는다.

추가 테이블은 같은 DB의 `chat_ui_actions`, `record_imports`, `record_import_locations`다. 기존 대화·기록은 보존하는 재실행 가능한 추가 마이그레이션이다. 영구 삭제·기억 복원은 기존 생명주기를 따른다.

파일 업로드는 `POST /api/v1/imports/preview`의 filename/text → `POST /api/v1/imports/{id}/commit`의 request_id 순서다. UTF-8 `.txt`·`.md`, 1MiB 이하, 기록당 4,000자다. 미리보기 취소는 DELETE로 원문을 폐기하며, 승인된 가져오기는 한 트랜잭션으로 모든 원문·작업·위치를 저장한다. 작업 큐 생성 실패는 전체 롤백한다. 커밋 후 별도 원문 복사본은 제거한다. 저장됨과 검색 가능함을 구분한다.

## 화면과 운영

기본 진입은 대화다. 새 대화는 첫 전송 또는 명시적 새 대화 선택 시 생성한다. 왼쪽에는 브랜드·대화·기록·보조 메뉴·대화 검색·목록을 통합했다. 입력창 도구에서 검색·기록 저장·파일 가져오기로 접근한다. 기존 질문 API는 유지한다.

대화 본문은 16px, 폭 약 760px, 배경은 크림색·강조는 짙은 초록색이다. 상단 장식·푸터를 대화 화면에서 줄였다. 검색 상세와 답변 복사·저장 도구는 기본 접힘이다. 상황별 선택은 1~3개, 더 많은 대상은 목록으로 표시한다.

1440px 이상은 오른쪽 근거 패널을 열며 대화 영역을 확보한다. 좁은 화면은 native dialog로 전환해 초점·Escape를 관리한다. 모바일 사이드바는 닫기·배경·Escape로 닫으며 초점을 제한한다. 변화 없는 갱신은 읽는 중인 근거 패널을 닫지 않는다. 세션별 초안·스크롤 위치·실패 재시도·한국어 조합 중 전송 방지를 유지한다.

실제 모델·온도·생성 문맥·검증 수준을 낮추지 않는다. 자연스러움과 사실성 평가는 분리하며, 미통과 실제 모델 사례는 테스트 성공으로 보고하지 않는다. 상세 실행 결과와 남은 제약은 평가 보고서에 기록한다.

실제 모델 평가의 필수 출처 사례는 인용이 없으면 실패다. 단순히 답변에 기대 단어가 있다는 이유로 검증에 실패한 내용을 통과시키지 않는다. 초회 평가와 원인 수정 후 평가, 모델 응답과 결정적 검사, 디스크 공간 부족에 따른 테스트 실행 실패를 각각 구분해 보고한다.
