전체 질문 분해 짝지은 비교
========================

후속 검증 도구와 새 120문항의 실행 방법은 evaluation/validation_README.rst를 참조한다.
현재 selective의 기본 기준은 전달 입력 및 검색 방식 차이까지 포함한다. 아래 과거
paired-search-1의 gold-hit 선별을 재현할 때는 --rule gold를 명시한다.

운영 앱에서 사용하지 않는 합성 평가다. 기존 질문 118개 모두에 동일한 분해기를
실행하고 분해 미적용/적용 검색을 짝지어 비교한다. correction-2는 기존 기준에 따라
실행하되 채점에서 제외한다. 기존 70개 회귀와 새 48개(개발 24/보류 24)를 사용한다.
새 48개는 두 원문과 표현 틀을 공유하므로 독립적인 사용자 분포 평가가 아니다.

조건
----

V0/V1: 문장 벡터 및 키워드 검색. 운영 Service의 의미 필터/후처리와 동일하지 않다.
M0/M1: 기억 내용, 역할을 유지한 사실 표현, 근거 구절, 명시적 시점 표현을 각각
임베딩하고 기억별 최대 유사도를 사용한다. 토큰 수준 ColBERT나 새 사실 추출이 아니다.
G0/G1: 벡터 없이 추출 사실의 인물·대상·정규화 관계에서 시작점을 찾고 공유 인물/대상
그래프를 최대 2단계 확장한다. 1은 분해 결과의 역할과 검색 구절도 활용한다.
H0/H1: M과 G 검색 순위의 reciprocal rank fusion.

0은 질문 분해 미적용, 1은 단순/복합/모호한 질문 모두에 분해를 시도한다.
원래 질문은 유지한다. 형식/근거 구절/관계 검증 실패 시 원래 질문으로 검색하고
실패 이유와 거절된 모델 출력을 보존한다. 형식 통과가 의미 정확도를 뜻하지 않는다.
그래프 연결은 후보 힌트이며 같은 이름의 인물이나 사건 동일성을 확정하지 않는다.
완전한 부분 그래프 매칭, 강제 시간/부정 제약, 추가 탐색 중단 정책, 기록 간 미해결
항목 갱신, 사용자 확인 UI는 이번 실험에 포함하지 않는다.

실행
----

호환 로컬 Qwen/BGE 서버(8081/8082)가 필요하다. 기존 prepared 추출 캐시와
output/answer-validation-v1/final-1/fixed/manifest.json의 임베딩 식별자를 재사용한다.
기존 실험과 같은 모델 파일을 사용해야 한다. 개인 DB는 열지 않는다::

    .venv/Scripts/python.exe -X utf8 -u -B -m evaluation.query_tree_run --paired --split all --tag paired-all-1 --answers
    .venv/Scripts/python.exe -X utf8 -B -m evaluation.query_paired_report --run-dir output/query-tree-v1/paired-all-1

소스/모델/데이터/설정이 바뀌면 새 tag를 사용한다. 같은 설정으로 재실행하면
완료 사례를 건너뛴다. 실패 사례만 다시 실행한다. 결과 파일은 사례 단위로 원자적으로
저장한다. 실험 중 일부 사례만 끝났으면 보고서는 완료 분모와 미실행 건수를 표시한다.

판정과 비용
----------

같은 추출 기억, 최대 8개 선택, 같은 6000토큰 근거 예산과 기존 답변/검증 함수를 쓴다.
후보/선택/실제 전달 구간의 필수 근거 전체 포함 여부를 각각 보고한다.
실제 전달에는 기존 답변 함수의 주변 원문 문맥이 포함되어 선택 단계보다 높을 수 있다.
원문 포함률은 역할·상태를 올바르게 답한 비율이 아니다. 답변은 원문 대조 검토 전까지
미검토로 남으며 모델의 검증 성공을 정답으로 세지 않는다.

질문 분해는 한 번 측정해 1 조건에만 비용을 귀속한다. 벡터 캐시는 공유하므로
실측 검색 시간은 캐시 상태에 의존한다. 문장/다중 벡터와 그래프 구축 비용은 분리한다.
같은 질문과 완전히 동일한 답변 입력은 해당 사례 안에서 답변을 공유하고
answer_reused_from을 남긴다. 공유된 답변 생성 시간은 effective 비용으로만 계산하며
실제 반복 호출 시간이나 안정성 측정치로 해석하지 않는다. 오류 답변은 재사용하지 않는다.

paired-report.html과 paired-comparison.csv는 짝별 개선/악화, 형식 실패,
질문 분석을 포함한 검색 시간, 원문·질문·예상 답·실제 답을 보여준다.
기존 report.html과 costs.csv에는 전체 진단과 실제 모델 호출 비용도 남는다.

paired-all-1 실행 이력
---------------------

회귀 질문 70개 완료 후 복합 원문의 새 추출을 중단하고 기존 개발/보류 실험의
동결 기억을 가져와 나머지 48개를 진행했다. 원문, 전체 앱/추출 코드, 모델 서버
식별 정보와 생성 설정을 대조했고 요청 model 필드만 null과 qwen3 별칭 차이였다.
캐시의 인용문과 위치도 원문과 대조했다. frozen-imports.json에 출처·해시·검증
내역을 남겼다. 중단한 새 추출의 시간은 재개 후 사례별 비용에 포함하지 않으므로
이 실행으로 신규 원문 최초 처리 비용을 추정하면 안 된다.

사용자가 실행 중 범위를 변경하여 전체 질문 검색 + 근거 회수가 달라진 쌍만 답변
비교하기로 했다. paired-search-1은 완료된 71개를 해시 검증 후 가져오고 나머지
47개는 검색만 실행한다. 기존 답변은 보존한다. 선택/전달 단계 필수 근거별 hit
벡터가 달라진 경우에만 해당 방식의 0/1 답변을 추가 생성한다. 순위/불필요 근거만
달라진 사례는 제외하므로 전체 답변 정확도를 추정하는 표본이 아니다::

    .venv/Scripts/python.exe -X utf8 -B -m evaluation.query_paired_selective --run-dir output/query-tree-v1/paired-search-1 --import-from output/query-tree-v1/paired-all-1
    .venv/Scripts/python.exe -X utf8 -u -B -m evaluation.query_tree_run --paired --split all --tag paired-search-1
    .venv/Scripts/python.exe -X utf8 -u -B -m evaluation.query_paired_selective --run-dir output/query-tree-v1/paired-search-1
    .venv/Scripts/python.exe -X utf8 -B -m evaluation.query_paired_report --run-dir output/query-tree-v1/paired-search-1

첫 import 명령은 새 폴더에 한 번만 실행한다. 모델 별칭은 원래 실행과 동일하게
PMA_MODEL=qwen3으로 설정한다. selective_answers에는 결과 원본 해시와 답변을
별도로 저장하며 원래 검색 결과를 덮어쓰지 않는다. 선별에만 기대 근거를 사용하고
답변 모델에는 전달하지 않는다. resume-imports.json과 answer-selection.json에
각각 재사용 출처와 비교 대상 선정 이유가 남는다.
