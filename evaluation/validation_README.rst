기억 검색·질문 분해 단계별 검증
================================

범위와 데이터
--------------

운영 모듈과 개인 기억 DB를 수정하지 않는 합성 평가다. 기존 118문항은 회귀 자료이며,
기존 holdout도 이미 관찰한 회귀 자료로 취급한다. correction-2의 기존 제외는 유지한다.
data/memory_validation_cases.json은 6유형 × 10개 사건 묶음 × 2질문 = 120문항이다.
각 유형 앞 5묶음은 개발, 뒤 5묶음은 최종 검증이다. 원문/사건은 분할 간 공유하지
않지만 시나리오 틀은 공유한다. 자연 사용자 분포나 통계적 독립성을 주장하지 않는다.
각 묶음에는 top-8보다 많은 기억을 만들도록 유사 인물/물건/사건 방해 문장을 넣었다.

필수 근거 구간, 답변 가능 여부, 기대 답변, 질문 조건, 시간 기준, 확인 질문 예시를
모델 실행 전에 고정한다. reference_memories는 평가 작성자가 원문에 맞춰 작성한
비교용 기억이다. 독립적인 사람의 검수가 아니며 운영 성능으로 보고하지 않는다.
내용 지지 여부는 추출 기억과 동일하게 review-queue에서 다시 검토한다.

재현과 실행
------------

프로젝트 가상환경과 기존 로컬 모델 서버 8081/8082를 사용한다. 모델 파일과 임베딩
해시는 기존 동결 실행과 동일해야 한다. PowerShell에서 PMA_MODEL=qwen3을 설정한다.
기존 answer-validation-v1/final-1/fixed/manifest.json에서 임베딩 식별자를 가져온다.
아래 명령은 프로젝트 루트에서 실행한다. 데이터 재생성은 최종 검증 실행 전에만 한다::

    .venv/Scripts/python.exe -X utf8 -B -m evaluation.validation_cases
    .venv/Scripts/python.exe -X utf8 -u -B -m evaluation.query_tree_run --paired --data data/memory_validation_cases.json --split development --tag validation-dev-raw --trace-extraction
    .venv/Scripts/python.exe -X utf8 -u -B -m evaluation.query_tree_run --paired --data data/memory_validation_cases.json --split development --tag validation-dev-reference --memory-source reference

모든 질문에 V/M/G/H × 분해 off/on의 8조건을 실행한다. 전체 질문과 동일한 기억,
top-8, 실제 토크나이저 기준 6000토큰 예산을 공유한다. direct_selected와 packed
selected를 모두 보존한다. 근거 확장의 효과를 직접 기억 회수 성능과 혼동하지 않는다.
--limit는 실행량만 제한하고 manifest의 전체 분모는 유지한다. --ids는 별도 소규모
디버그 실행용이며 완전한 개발 실행을 대신하지 못한다.

변경 사례 답변과 보고서::

    .venv/Scripts/python.exe -X utf8 -u -B -m evaluation.query_paired_selective --run-dir output/query-tree-v1/validation-dev-raw
    .venv/Scripts/python.exe -X utf8 -B -m evaluation.validation_audit --run-dir output/query-tree-v1/validation-dev-raw --output output/memory-validation-v1/development-raw

reference 실행도 동일한 두 명령에 대응 폴더를 지정한다. audit에
--compare-run output/query-tree-v1/validation-dev-reference를 추가하면 같은 코드·모델·원문인
두 기억 출처의 직접/확장 근거 회수를 extraction-comparison.json으로 비교한다.
답변 선별 기본값은
compact_evidence의 실제 입력 변화(내용·순서·시간·상충 정보 포함) 또는 필수 근거
hit 변화다. 분해 전후뿐 아니라 V0와 다른 검색 방식도 비교하고 비교 기준인 V도
함께 선택한다. --rule gold는 이전 실행의 좁은 off/on 기준을 재현할 때만 사용한다.
정답은 평가 선별/채점에서만 사용하며 검색·답변 모델에 넣지 않는다. 입력이 정확히
같을 때만 답변을 재사용하며, 미실행은 시간 null로 남긴다. 재사용 시간 0은 추가
실행 비용 0이라는 뜻이고 모델 응답 시간으로 해석하지 않는다. 새 보고서의 답변 지연
중앙값에서는 재사용 결과도 제외한다.

추적과 검토
------------

--trace-extraction은 평가 프로세스 안에서만 임시 계측한다. 모델 요청/원시 응답,
문장 ID와 위치, 인용문 복원 결과, chunk cache, 중복 제거 후 publish 입력을 보존한다.
최종 저장 snapshot은 frozen_memories, 재생 후 기억은 direct_selected에 남는다.
실패 추출의 trace와 재실행 전 실패 결과도 보존한다. 기존 캐시에 trace가 없으면
원인은 미확정이다. 정확한 quote가 존재한다고 기억 내용이 맞다고 간주하지 않는다.

보고서는 다음을 생성한다.

* validation-report.html / validation-summary.json: 8조건·단계·비용·미완료 분모.
* conditions.csv / paired-changes.json: 질문별 직접/확장 근거와 개선·악화·동일.
* answer-comparisons.json / deferrals.json: 변경 사례의 답변, 검증 trace, 보류 사유.
* stage-errors.json / review-queue.json: 기계적 오류와 의미 검토 대상.

review-queue.json에서 판정한 항목을 실행 폴더의 validation-reviews.json에 저장하고
audit를 다시 실행한다. id와 payload는 수정하지 않는다. judgment는 correct, wrong,
appropriate_abstention, excessive_abstention, unclear 또는 needs_review이며 판정에는
reviewer와 reason이 필수다. 평가 작성자가 검토했다면 reviewer에 그 사실을 명시한다.
단순 정규식이나 같은 모델의 verify=true는 정답 판정이 아니다.

retrieval_constraints 판정에는 direct_conditions와 delivered_conditions를 추가한다.
각 조건 field를 키로 하고 satisfied / missing / contradictory 중 하나를 기록한다.
주변 원문에 정답이 있어도 선택 기억의 직접 조건 충족으로 기록하지 않는다.
decomposition은 필드별 의미 정확성과 __overall__ 전체 해석을 검토한다. 전체 해석은
추가된 잘못된 역할, 행동/부정/의도/관계 누락까지 포함한다. answer는 원문과 요구한
시간 기준, 적절한 보류, 이유/확인 질문을 검토한다. 오류를 근거 부족으로 감추면 안 된다.
미검토/모호한 항목은 통과로 세지 않는다. 지표의 reviewed 분모를 반드시 같이 읽는다.

개선 후보와 최종 검증
----------------------

현재 baseline 측정 → 질문 분해 검증 개선 → 조건 충족/누락/모순 검색 결합 → 시간
기준 답변 검증 순서다. 각 개선은 평가 전용 후보로 하나씩 추가하고 새 tag에서 개발
자료로만 비교한다. 앞 단계의 코드·설정·데이터·모델을 manifest로 고정한 뒤 다음
후보를 비교한다. 이 도구 추가 자체가 해당 개선 알고리즘의 효과를 증명하지 않는다.

완료한 동일 설정의 개발 실행을 지정해야 최종 검증을 시작할 수 있다::

    .venv/Scripts/python.exe -X utf8 -u -B -m evaluation.query_tree_run --paired --data data/memory_validation_cases.json --split holdout --tag validation-held-raw --trace-extraction --freeze-from output/query-tree-v1/validation-dev-raw

reference는 대응 development/reference 실행과 --memory-source reference를 지정한다.
최종 검증은 데이터/기억 출처별 한 실행만 허용하며 완료 사례는 재실행하지 않는다.
첫 기억 출처의 최종 검증을 열면 다른 출처에도 같은 코드·설정·모델 동결이 적용된다.
중단/실패 사례 재개는 허용하지만 새 tag나 바뀐 코드로 같은 holdout을 다시 소비할 수
없다. 최종 결과를 보고 수정했다면 새 사건 자료가 필요하다. ledger를 삭제해 재사용하지
않는다. 최종 검증 결과를 개발용 튜닝에 사용하지 않는다.

통과는 기계적 오류 0, 지정 필수 사례의 오답 승인/과도한 보류 0, 요청된 변경 사례
답변 완료, 의미 검토 완료가 모두 충족되어야 한다. 선택된 답변 부분집합에 대한 판정이며
전체 질문의 답변 정확도를 뜻하지 않는다. 실패/미실행/미검토는 각각 따로 표시한다.
아이디어는 유지 / 수정 후 재검증 / 효과 미확인으로 결론 내리고 운영 배포는 하지 않는다.
현재 그래프는 어휘 기반 사건 연결 확장이다. 구조 유사도 검색이나 부족한 조건의 추가
탐색을 구현·평가한 것으로 해석하지 않는다.

기존 결과 재검토(모델 호출 없음)::

    .venv/Scripts/python.exe -X utf8 -B -m evaluation.validation_audit --run-dir output/query-tree-v1/paired-search-1 --data data/query_tree_cases.json --output output/memory-validation-v1/legacy-audit

기존 실행은 당시 코드와 provenance를 보존한다. 새 코드로 manifest를 덮어쓰거나
기존 실행에 답변을 억지로 추가하지 않는다. 새로운 회귀 실행은 새 tag를 사용한다.
