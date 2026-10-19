> 초기 설계 기록입니다. 최종 구현·API·실행 결과는 implementation_report.md, api_contract.md, test_results.md를 확인하세요.

# Chat/API/UI 계약

기존 chat_messages 한 행은 사용자 question과 AI response를 함께 보존한다. 따라서 같은 message_id에 source_type을 함께 기록한다. 출처 ID는 서버가 지정한 session_id 범위에서 재조회하며, 정상 완료되지 않았거나 근거가 변경·삭제된 턴은 저장하지 않는다. 선택 문장은 해당 출처 원문에 실제로 있어야 한다.

GENERAL/MEMORY/HYBRID는 같은 저장 API를 사용한다. 자연어 요청은 응답 이후 후보만 생성하며 실패가 대화 응답을 무효화하지 않는다. ‘이거 기억해’는 앞선 사용자 발언과 AI 답변을 서로 다른 후보로 제시한다. 일반 질문에서는 후보를 생성하지 않는다. 저장 선호는 일반 답변의 표현 방식 입력에 전달하며 개인 사실 검색을 추가하지 않는다.

## API

| 메서드·경로 (/api/v1 기준) | 동작 |
|---|---|
| POST /memory/candidates | session_id, message_ids, user_message/assistant_message, 선택적 selected_text로 후보 생성 |
| GET /memory/candidates | 아직 유효한 pending 후보 |
| POST /memory/candidates/{id}/commit | approved=true, request_id, candidate_version, 선택적 content/memory_type/resolution |
| POST /memory/candidates/{id}/reject | 후보 취소 |
| GET /memory | 활성 기억·기존 기록 목록, policy=MANUAL |
| GET /memory/{id} | 내용·출처·버전·검색 처리 상태 |
| PATCH /memory/{id}, POST /memory/{id}/corrections | expected_version/content로 정정 후보 생성; 즉시 저장하지 않음 |
| GET /memory/{id}/history | 이전 원문과 승인 버전 |
| DELETE /memory/{id}?expected_version=N | 버전 검사 후 휴지통 이동 및 검색 제외 |
| POST /memory/{id}/retry | 기존 인덱싱 작업 재시도 |

resolution은 add, add_confirmed, correct다. 같은 내용은 exact_duplicate로 차단한다. 관련 기록이 있으면 사용자가 비교한 후 별도 추가 또는 정확한 대상의 새 버전 정정을 선택해야 한다. AI 출처는 proposal/hypothesis/conversation_summary 유형만 허용한다.

기존 Host/Origin, 로그인 쿠키, CSRF, 입력 크기, CSP 정책이 새 라우트에도 적용된다. 사용자 소유자·사실 검증 상태·출처 내용은 요청에서 받지 않는다.

## UI

`pma/static/memory.js`에 저장 버튼, 선택 문장/복수 메시지, 후보 편집, 유형 선택, 원문 확인, 관련 기억 비교, 승인·취소·보류, 처리 상태·재시도, 관리·정정·삭제·이력을 구현했다. 기존 chat.js와 index.html에 연결했다. native dialog와 label을 사용하며 원문은 textContent로만 렌더링한다. Hybrid 선택 항목도 화면에 노출했다.

저장 취소는 rejected 상태로 만들고, 결정 보류는 pending 상태로 남겨 새로고침 후 관리 화면에서 다시 열 수 있다. 후보 유효기간은 24시간이다.
