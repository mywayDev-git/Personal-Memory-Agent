# 회귀 검증

현재 저장소의 기존 모드 계약 테스트와 기억 저장 테스트 전체를 실행했다. 기존 변경 `tests/test_chat_mode_api.py`와 `evaluation/conversation_modes_results.rst`는 유지했다. 606개 과거 테스트는 현재 파일이 없어 실행하지 않았다.

실제 Qwen/BGE 합성 DB에서 최초 민수 동행 검색 → 영희로 정정 → 영희 검색 및 민수 제외 → 삭제 후 snapshot 제외를 다시 통과했다. preference/proposal/project_decision 색인은 모두 ready였다. 일반 대화에서 선호를 전달하는 경로도 실행했다. 실제 언어 표현의 품질과 모든 검색 질문의 정확도를 포괄하는 평가는 아니다.

별도 자동 테스트로 주체/수신자 역전, 날짜 차이, 부정, 계획과 완료, AI 제안과 사용자 경험, 프로젝트 범위, 수정 후 이전 버전, 승인 없는 쓰기, 소유권, 출처 변경, 재시도·동시 쓰기·응답 유실 멱등성을 확인했다.

검색의 vector/keyword/RRF, 질의 이해, 근거 검증 알고리즘은 변경하지 않았다. 기억 입력에 출처/사실 상태를 부착하고 기존 기록·revision·job·snapshot 경로를 사용한다. 후보와 archived/deleted/superseded 기록은 검색 대상으로 확정하지 않는다.

초기 발견 실패: legacy record 별칭의 다른 소유자 접근(provenance_error), AI 정정 시 사실 상태 유실(provenance_error), 리뷰 이후 기록 변경 확인 미비(approval_bypass), 보관/만료 정리 미구현(commit_failure). 테스트를 먼저 추가하고 모두 수정했다. 실제 관계 초기 실패는 duplicate_detection_error 및 보완/증거 관계 구분이었으며 지침 수정 후 같은 개발 세트 8/8을 통과했다.
