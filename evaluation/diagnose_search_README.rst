검색 Trace 오프라인 분석
=======================

모델 서버나 사용자 DB를 열지 않는다. 기존 JSONL과 평가 자료만 읽는다.
검색·필터·답변 동작을 변경하지 않는다.

실행
----

프로젝트 루트에서::

    .\.venv\Scripts\python.exe -B -m evaluation.diagnose_search --trace TRACE.jsonl --dataset data/search_diagnostics.json --bindings BINDINGS.json --output OUTPUT_DIRECTORY --k 20

출력은 diagnostic_summary.json, diagnostic_cases.json, diagnostic_report.md이다.
원본 질문·원문·기대 답변을 결과에 복사하지 않는다. case_id와 가명 ID는 남는다.
bindings 없이도 실행 가능하지만 연결되지 않은 질문의 Recall은 null이다.

지원 평가 형식
--------------

* data/search_diagnostics.json 및 life_diagnostics.json: questions[].id,
  question, relevant(기록 별칭), expected. relevant의 빈 목록은 정답 근거 미지정이다.
* data/query_tree_cases.json 등 시나리오 배열: case.id, questions[].text,
  supporting_records(시나리오 내부의 기록 인덱스). 질문 ID가 없으면 case.id.index.
* 대시보드 Case: question, expected_answer, gold_groups. 그룹마다 대안 memory_id
  중 하나가 검색되면 충족하고, 모든 그룹을 충족해야 Complete Evidence Recall=1.
* 직접 지정: gold_memory_ids 또는 gold_record_ids.

relevant의 모든 항목을 찾았다는 것은 '주석된 집합 전체 회수'이며 모든 항목이
답변에 필수라는 의미는 아니다. 기대 답변의 의미적 정답률은 자동 추정하지 않는다.
없는 정답 ID를 생성하지 않으며 메모리와 기록 단위를 섞지 않는다.

가명 ID 연결
------------

기본 Trace는 원본 ID 매핑을 저장하지 않는다. 따라서 과거 JSONL만으로 원본
정답 ID를 복원하거나 질문 순서로 요청을 맞추면 안 된다.

평가 실행에서 start_trace scope가 종료된 뒤 capture_binding(trace, case_id,
memory_ids=[실제 정답 memory_id], records={평가 별칭: 실제 저장 record_id})를
호출하면 명시적 sidecar를 만들 수 있다. lookup_ref는 읽기 전용이며 로그에서
관찰하지 못한 ID를 새로 만들지 않고 null로 남긴다. 평가 연결 파일에는 원본
ID/별칭이 있으므로 기본 로그와 분리해서 평가 담당자가 관리한다.

bindings 최상위는 case_id를 키로 하는 객체다. 각 값은 trace_id와 memory_refs,
record_refs 객체를 가진다. 예시 키 구조(실제 값으로 대체해야 함)::

    {
      "synonym_when": {
        "trace_id": "REQUEST_TRACE_ID",
        "record_refs": {"fight": "record-REQUEST_TRACE_ID-1"},
        "answerable": true,
        "expected_verified": true
      }
    }

answer_correct, answerable, expected_verified는 선택적 bool 평가 라벨이다.
이를 답변 결과에 맞춰 자동 생성하지 않는다. 재질문이 불필요하다고 확정하려면
전체 근거, 기대 답변 존재, answerable 및 expected_verified 확인이 필요하다.
라벨 없이 근거만 남고 보류되면 evidence_present_no_answer로 관찰할 뿐,
evidence_present_answer_failed는 null로 남을 수 있다.

지표 해석
---------

* stage_recall: 실제 단계 전체 후보의 그룹 Recall.
* recall_at_k: vector/keyword 각각 상위 K, 두 분기의 합집합(최대 2K), fusion 상위 K.
  K를 바꿔도 실제 최종 근거 및 최초 손실 단계는 바뀌지 않는다.
* evidence_recall: 최종 선정 근거가 충족한 정답 그룹의 비율.
* complete_evidence_recall: 해당 질문의 모든 그룹 충족 여부. 요약은 질문별 평균.
* loss_stage: snapshot → structure_filter → rank_fusion → evidence_selection 중
  복구되지 않은 최초 손실. fusion이 구조 점수로 후보를 추가할 수 있어
  vector/keyword 합집합은 이 직렬 손실 경로와 구분한다.
* 구조 필터가 명시적으로 빈 집합이면 최종 근거도 비어 있음을 알 수 있지만,
  실행하지 않은 검색 분기의 Recall은 null이다.
* 잘린 Trace, 누락 순번, 복수 요청, 없는 ID 연결, record-memory 연결 누락은
  평가 불가이며 검색 실패로 분모에 포함하지 않는다.
* filter_exclusions는 서비스 구조 필터 요약을 사용해 세부 이벤트 중복을 피한다.
  gold_exclusions는 정답 라벨 근거가 제외된 사례이며 곧바로 정책 오류를 뜻하지 않는다.
* duration_ms는 실제 계측 값이다. 중첩된 메서드 시간이므로 합산하지 않는다.
  HTTP 전체 시간이 있으면 우선하고, 없으면 서비스 최종 결정 시간을 사용한다.
* 우선순위는 관찰된 손실/실패 질문 수 기준 최대 5개다. 증거가 1개 단계뿐이면
  1개만 제시한다. 정확도 개선 폭이나 운영 우선순위를 추정하지 않는다.

재현 가능한 합성 통합 확인
-------------------------

python -B -m tests.diagnostics.smoke_report

기존 합성 자료 24개 질문을 임시 SQLite와 실제 Service에서 실행하며 ON/OFF
응답을 비교한다. 추출은 전체 기록 한 개를 사용하는 모의 응답이고 임베딩은
상수, 선정·생성·검증도 모의 모델이다. 사용자 DB나 기존 data는 수정하지 않는다.
새 .local/diagnostics-prompt10/synthetic-* 폴더에 실제 실행 Trace와 보고서를 만든다.
이는 연결·계산 검증이며 실제 모델 End-to-End 평가나 제품 정확도가 아니다.

2026-10-18 실행에서 근거 평가 가능 22/24, 정답 미지정 2개, 구조 필터 최초 손실
11개가 관찰되었다. 모의 추출의 상태 값에 영향을 받으므로 필터 정책을 고칠
근거로 사용할 수 없다. 실제 실행 자료에 기반한 운영 TOP 5는 아직 확정 불가하다.
