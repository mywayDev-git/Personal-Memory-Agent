# 기억 저장 API 계약

기존 `/api/v1` 인증, Origin 검사, CSRF 정책을 유지한다. owner_id는 입력받지 않고 로컬 계정으로 결정한다. 기존 Search/Chat 핵심 응답 필드는 유지하며 Chat에는 선택적인 memory_candidates와 memory_capture_error만 추가한다.

| 경로(`/api/v1/memory`) | 메서드 | 요청/결과 |
|---|---|---|
| `/candidates` | POST | session_id, message_ids, source_type(user_message/assistant_message), selected_text. 원문 출처를 서버에서 조회 |
| `/extract` | POST | session_id. 최근 완료된 최대 30개 발화에서 최대 12개 원문 후보 |
| `/candidates` | GET | 유효한 pending 후보 |
| `/candidates/{id}/review` | POST | content, memory_type, project_scope, event_time, candidate_version. review_id/status/comparisons/coverage 반환 |
| `/candidates/{id}/target` | POST | memory_id, expected_version, content. 원래 후보 출처를 보존하는 정정 후보 |
| `/candidates/{id}/commit` | POST | approved=true, request_id, candidate_version, review_id, 편집 필드, resolution(add/add_confirmed/correct), link_memory_ids |
| `/candidates/{id}/reject` | POST | 후보 취소 |
| `/policy` | GET/PUT | MANUAL 또는 SUGGEST. AUTO 허용 안 함 |
| `` | GET | include_inactive=true로 이력·보관·삭제 항목 포함 |
| `/{id}` | GET/DELETE | 상세 / expected_version으로 휴지통 이동 |
| `/{id}/corrections` | POST | content, expected_version. 새 승인 후보 |
| `/{id}` | PATCH | corrections와 동일 |
| `/{id}/history` | GET | 원문 버전 이력 |
| `/{id}/retry` | POST | 실패한 색인 재시도 |
| `/{id}/archive`, `/{id}/unarchive` | POST | expected_version. 보관 / 재활성화 |

저장과 색인 상태는 committed/indexing/searchable/index_failed/inactive로 구분한다. 승인 요청의 동일 request_id는 같은 응답을 반환하고 다른 본문 재사용은 REQUEST_CONFLICT이다. REVIEW_CHANGED/REVIEW_STALE/REVIEW_INCOMPLETE는 재검토가 필요하다. EXACT_DUPLICATE/SEMANTIC_DUPLICATE는 기존 기억 확인이 필요하다. SOURCE_CHANGED/소유권/버전 실패는 기록을 쓰지 않는다.

관계 링크는 supporting/complementary/temporal_update로 검토된 활성 기록만 허용한다. 링크에는 승인 시점의 대상 버전을 저장한다. 기존 검색의 자동 추론 링크와는 별도의 사용자 승인 관계다.
