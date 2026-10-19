# 실행한 테스트 결과

2026-10-18, Python 3.14.8, Windows, 브랜치 codex/selective-memory-capture.

## 자동 테스트

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/Scripts/python.exe -m pytest tests -q --basetemp .test-tmp-complete-delivery`

**59 passed, 1 warning, 3.02초**. 경고는 기존 Starlette/httpx TestClient 사용 중단 예정 안내다. 승인, 원자성, 재시작, 동시성, 실패 재시도, 정정·삭제 색인, 만료, 소유권, 원문 해시, 원문 선택, 정책, 보관·복구, HTTP 계약, 프로젝트 범위, 모델 실패, 원문 근거 위조, legacy 별칭 출처 보존을 포함한다. 초기 기준 31개에서 28개를 확장했다.

Ruff 검사와 Python 구문 검사, memory.js 및 E2E 모듈의 Node 구문 검사가 통과했다. git diff --check도 통과했다.

## 실제 로컬 모델

- 관계 8종: 개발 평가 1차 6/8 → 2차 7/8 → 3차 **8/8**. 원자료 output/memory-relations-live-01~03.json. 처음 실패한 단계는 duplicate_detection_error/관계 분류였다. 동일 개발 사례 재평가이며 별도 홀드아웃 성능으로 주장하지 않는다.
- Qwen/BGE 저장·검색 회귀: **6/6**. 최초 동행자 민수 검색, 영희 정정 검색, preference/proposal/project_decision, 삭제 제외. output/memory-capture-live-03.json.
- 정확한 실제 모델 HTTP 요청 **46회**, 검색 API **2회**. 별도 관계 평가 HTTP 14회. 게이트웨이 호출 수와 HTTP 횟수를 혼동하지 않는다.

## 브라우저

`evaluation.memory_ui_server`가 생성한 임시 DB와 결정적 모델을 사용하고 실제 인증·CSRF·HTTP·SQLite 경로를 통과했다. `tests/memory_capture_ui.mjs`는 CUA tab을 받아 반복 실행하는 스크립트다.

- 주요 시나리오 20개: GENERAL/MEMORY/HYBRID 각각 비교 전 승인 비활성, 비교, 저장, 이력, 보관, 보관 해제; AI 유형 제한; 정책 새로고침 유지.
- 추가 6개: 중복 승인 차단, 편집 후 재비교, 색인 실패 표시, 재시도 대기 전환, 정정 버전 2, Escape 닫기.
- 390×844 뷰포트에서 기억 관리 대화상자 폭 339px, 가로 넘침 없음. output/memory-capture-mobile.png.
- 대화 추출 버튼의 후보 표시 확인. UI 결과는 output/memory-capture-ui-results.json.

마지막 삭제 확인에서 브라우저의 native confirm이 도구를 정지시켰다(ui_state_error). 이를 접근 가능한 HTML dialog로 바꾸었고 구문 검사를 통과했다. 도구의 기존 모달 정지 상태가 새 탭에도 영향을 주어, **변경 후 삭제 확인 버튼 클릭의 최종 브라우저 재실행은 완료하지 못했다**. 삭제 API와 삭제 후 검색 제외는 위 자동/실모델 검증을 통과했다. 서로 다른 역할을 함께 선택할 때는 별도 후보 선택창으로 보여주도록 마지막 UI 보완을 했으며 이 경로 역시 최종 브라우저 재실행 범위에 포함되지 않는다.

## 재현

1. Python 테스트는 매 실행마다 새 basetemp를 사용한다.
2. 모델 관계 평가: `python -m evaluation.memory_relations_eval --output output/새이름.json`.
3. 저장·검색 평가: `python -m evaluation.memory_capture_eval --embedding-revision BGE모델_SHA256 --output output/새이름.json`.
4. UI: `python -m evaluation.memory_ui_server`로 새 임시 서버를 시작하고 출력된 인증 URL을 CUA로 연 뒤 AI 대화 화면에서 `runMemoryUI(tab)`, 이어 `runMemoryEdges(tab)`를 실행한다. 모델을 가짜로 대체한 UI 테스트와 실제 모델 평가를 구분한다.
5. 서버를 종료하면 해당 임시 DB의 수명도 끝난다. 운영 데이터·기존 모델 서버는 변경하지 않는다.
