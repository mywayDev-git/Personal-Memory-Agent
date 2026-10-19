> 초기 설계 기록입니다. 최종 구현·API·실행 결과는 implementation_report.md, api_contract.md, test_results.md를 확인하세요.

# 저장·검색 계약

## 기존 경로

`Store.create` → records/revisions/jobs를 한 트랜잭션에 저장 → `Service.run_one` → 기존 추출/검증 → BGE 임베딩 → `Store.publish`.

records는 active/trash, revisions는 원문 버전, jobs는 queued/running/succeeded/failed/cancelled다. evidence, embeddings, facts는 memories에 연결된다. 임베딩 생성과 publish가 성공해야 검색 가능하다.

`Store.snapshot`은 현재 버전이며 active/ready인 기록과 일치하는 embedding_key만 읽는다. 벡터·키워드·RRF 및 기존 답변 검증은 유지했다. 수정·삭제 시 `invalidate`와 generation 증가로 검색 근거와 캐시를 무효화한다.

## 추가 계약

- capture_candidates: 소유자와 후보 원문·유형·인식 상태·출처·만료·대상 버전.
- captured_memories: 기존 record_id와 승인된 기억 메타데이터. 정정 이전 버전도 보존한다.
- capture_requests: 소유자/request_id로 유일한 저장 결과와 정확한 입력 조건을 보존한다.
- 테이블 생성은 기존 시작 트랜잭션에 추가했다. 기존 user_version=5와 기존 테이블을 유지하는 반복 가능한 확장이다.
- 사용자 승인 전에는 records/revisions/jobs에 후보를 등록하지 않는다. 후보 자체는 별도 테이블에 보류 상태로 남는다.
- 승인 시 후보·소유자·만료·출처·버전·중복을 재확인하고 기록, 버전, 출처와 durable jobs를 하나의 SQLite 트랜잭션에 저장한다.
- 기존 jobs가 durable outbox 역할을 한다. 새 중복 큐를 만들지 않았다. 실패 시 원문이 남고 기존 retry 경로로 복구한다.
- 응답 index_status: committed / indexing / searchable / index_failed / inactive. ready_empty를 검색 완료로 오인하지 않는다.
- 기존 일반 기록은 `record:<record_id>`로 관리 화면에서 조회한다. 승인 전에는 해당 기록을 수정하지 않으며 정정 승인 시 새 revision을 만든다.
- 출처 승인과 객관적 검증을 구분하는 라벨을 검색용 원문에 포함한다. AI 제안·가설은 추출 후에도 uncertain 상태와 unknown 주체를 강제해 사용자 실행 사실로 승격하지 않는다.

현재 호스트는 한 Windows 사용자의 로컬 계정 서비스다. HTTP 소유자는 서버가 `local-account`로 지정하며 클라이언트 owner_id를 받지 않는다. 다중 계정 인증 서버는 구현 범위에 포함하지 않았다.
