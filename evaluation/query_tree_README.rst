질문 분해·주제 트리 검색 실험
============================

운영 앱에서 import하지 않는 독립 평가 도구다. 개인 DB를 열지 않고,
기존 동결 추출 결과와 새 합성 원문으로 임시 SQLite를 만든다.
운영 적용이나 트리 방식 채택을 의미하지 않는다.

실행
----

기존 프로젝트 의존성과 설정된 생성·임베딩 서버가 필요하다. Kiwi는 필요 없다.
저장소 루트에서 실행한다::

    .venv\Scripts\python.exe -m evaluation.query_tree_run --tag development-1 --split development --answers
    .venv\Scripts\python.exe -m evaluation.query_tree_run --tag regression-1 --split regression --answers
    .venv\Scripts\python.exe -m evaluation.query_tree_run --tag holdout-1 --split holdout --answers
    .venv\Scripts\python.exe -m evaluation.query_tree_run --tag scale-1 --split holdout --ids qt-phrasing-4 qt-roles-4 qt-scope-4 qt-multitopic-4 qt-context-4 qt-multihop-4 --scale 100 --answers
    .venv\Scripts\python.exe -m evaluation.query_tree_run --tag scale-1 --split holdout --ids qt-phrasing-4 qt-roles-4 qt-scope-4 qt-multitopic-4 qt-context-4 qt-multihop-4 --scale 1000 --answers
    .venv\Scripts\python.exe -m evaluation.query_tree_run --phase report --tag development-1

``--answers``를 생략하면 검색만 평가한다. 모델·코드·데이터·동결 추출 해시가
같은 완료 사례만 재사용한다. 코드나 answers 설정을 바꾸면 새 tag를 사용한다.
재실행 안정성은 별도 tag로 반복해 비교한다. 모델 요청은 직렬이며,
사례별 조건 순서는 seed 42와 사례 ID로 섞는다.

비교군
------

* A: 현재 Service._search에 진단만 삽입한 검색.
* B: 원래 질문의 벡터·키워드 검색. 의미 제외와 LLM 선택 없음.
* C: B + 질문 원문의 행동·대상·시간·범위·관계 구간 검색.
* D: C + 상위 두 주제 경로. 기억은 두 주제에 다중 소속.
* E: C + 원문 문단 검색.
* F: D + 원문 문단 검색 + 문단·인접 문단·날짜 제목 확장.

원래 질문의 전역 경로는 B~F에 항상 남긴다. 트리 경로의 사람 언급은
후보 확장을 위한 힌트이고 인물 동일성을 확정하지 않는다. SQL 주제 인덱스와
벡터 계산을 결합하며, 키워드는 원문 근거/문단 안에서만 센다.
동일 주제 경로를 중복 가산하지 않고, 동률은 원문 위치·내용으로 정렬한다.
원문 안의 지시는 모델에게 데이터로 전달한다.

평가와 한계
-----------

118개 = 기존 70개 + 새 48개. correction-2는 점수에서 제외한다.
새 사례는 개발/보류 평가 각 24개이나, 두 합성 원문과 병렬 질문 틀을 사용한다.
독립적인 실제 사용자 분포나 새로운 언어 유형으로 일반화하는 성능은 아니다.
주제·질문 분석 품질은 형식 검증만으로 의미 정확도를 주장하지 않는다.
analysis_gold는 제한적인 검토 보조값이며 완전한 분석 정답이 아니다.

필수 원문 구간 전체 포함률, 구간 회수율, 관련 구간과 겹치는 후보 비율을
후보/선택/실제 전달 단계별로 저장한다. 넓은 문맥은 회수율을 쉽게 올리므로
최종 답변 및 불필요 근거의 수동 검토가 함께 필요하다. precision은 의미적
정답률이 아닌 구간 겹침 지표다. 정답 조건은 모델에 전달하지 않는다.

답변 비교는 모든 조건에 같은 기존 LLM 답변·verify 프롬프트를 사용한다.
운영의 코드 생성 답변까지 그대로 재현하는 전체 앱 종단 평가는 아니다.
답변 생성 또는 검증 통과를 정확도로 세지 않고 needs_review로 남긴다.
수동 검토는 tag 디렉터리의 reviews.json 배열에 case, scale, condition,
response_hash(digest(response)), judgment, reason을 기록한다. 지원 판정은
correct/wrong/appropriate_abstention/excessive_abstention/needs_review다.
답변 해시가 맞고 사유가 있는 검토만 report 단계가 반영한다.
현재 포함된 초기 답변 검토는 보조자의 원문 대조이며 독립 평가자 합의가 아니다.
현재 데이터에 사용자 명시 필터 조건은 없다. 새 검색군의 명시 필터 동작은
운영 적용 전에 별도 구현·검증해야 한다.

임베딩은 공유 캐시를 사용하므로 조건별 실측 비용은 캐시가 있는 비용이다.
question_analysis와 index/preparation 비용은 공유 단계로 따로 기록한다.
이를 조건마다 무조건 반복하거나, B에도 질문 분석 비용을 붙이지 않는다.
HTTP usage가 없는 호출은 0토큰으로 단정하지 않고 usage_missing에 표시한다.
주제 구축 비용과 원문 검색 비용이 합산된 index 시간은 개별 모듈 제거 실험의
정밀한 구축 비용 차이를 대신하지 않는다.

출력
----

output/query-tree-v1/<tag>/ 아래에 manifest.json, snapshot/, results/,
diagnostics.jsonl, comparison.csv, costs.csv, summary.json, report.html을 만든다.
results에는 원문·동결 기억·질문 분석·주제 소속·후보·탈락 이유·전달 구간·
답변과 검증·모델 원응답·호출 비용을 보존한다. 임시 DB는 종료 시 정리한다.
vectors.sqlite와 extractions/는 합성 실험 재개 캐시다.

채택은 D 대 C의 필수 근거 포함 개선과 수동 답변 평가를 함께 확인한 뒤 결정한다.
동률이면 단순한 방식을 우선하고, 운영 기본값은 자동 변경하지 않는다.

보류 평가의 답변 검토 보고서
---------------------------

``holdout-final-1``은 개발 시 고정한 코드·데이터·모델 설정을 유지한 24개 × 6조건
답변 실행이다. 실행 전에 ``review-protocol.json``에 판정 기준을 기록하고,
원문 및 실제 전달된 인용 구간과 대조한 ``reviews.json``을 별도로 저장한다.
질문의 필수 부분을 누락한 미완답은 사실·근거 오류와 구분한다.
인용 주변 문맥이 뒷받침하더라도 직접 인용 구절이 다른 사건인 경우도 표시한다.

모든 결과와 수동 판정이 준비되면 다음 명령으로 검토 보고서를 만든다::

    .venv\Scripts\python.exe -m evaluation.query_tree_run --phase report --tag holdout-final-1
    .venv\Scripts\python.exe -m evaluation.retrieval_audit --tag holdout-final-1 --strict

strict 검사는 동결 파일 해시, 24개 사례·6조건의 완료, 판정 중복·누락,
답변 해시와 검토 사유를 확인한다. 검토 필요로 남긴 사례는 성공으로 계산하지 않는다.
이 보고서 도구는 모델을 호출하거나 답변을 수정하지 않는다. ``answer-audit.html``,
``answer-audit.csv``, ``answer-audit.json``에 판정·종료 단계·비용을 출력한다.
