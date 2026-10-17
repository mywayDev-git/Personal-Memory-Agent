고정 근거 답변 개선 비교
=======================

실행은 evaluation.fixed_answer_replay, 원문 검토와 보고서는
evaluation.fixed_answer_report로 분리한다. 운영 코드 및 개인 기억 저장소는
수정하지 않는다. 기존 full-120 산출물의 21개 실패 문항과 유형별 서로 다른 사건의
성공 문항 2개씩을 ID 순으로 선정한다. 검색 결과가 달라져 이미 선택된 입력만
재생한다. 33문항은 248개 조건별 결과와 195개 고유 입력에 해당한다.

실행 예::

    python -m evaluation.fixed_answer_replay prepare --output output/fixed-answer-replay-v1/run-1
    python -m evaluation.fixed_answer_replay diagnostic --output output/fixed-answer-replay-v1/run-1
    python -m evaluation.fixed_answer_report pending
    python -m evaluation.fixed_answer_report record --id <검토그룹ID> --judgment correct --reason <원문대조이유>
    python -m evaluation.fixed_answer_report report

PMA_MODEL=qwen3 및 기존 로컬 모델 설정을 사용한다. prepare 후 코드·입력·기존 결과
해시가 바뀌면 재개하지 않는다. 초기 준비용 output/fixed-answer-replay-v1/manifest.json은
실제 실행 이전 버전이며, 완료된 실행의 공식 경로는 하위 run-1이다.

A는 기존 결과다. B는 새 생성과 기존 검증, C는 같은 초안과 새 검증, D는 같은
초안·첫 검증에 최대 한 번 수정·재검증을 추가한다. 새로운 질문 계획이나 구조화
답변 우회를 넣지 않는다. B의 변화에는 기존 개선 프롬프트와 시간 필드 표현이
같이 포함되므로 둘의 개별 효과라고 해석하지 않는다.

단계별 journal에 요청 해시, 원시 모델 출력, 사용량, 시간, 결과를 저장한다.
연결 오류는 중단 후 동일 모델을 확인해 실패 단계만 재개한다. 정상 단계는 다시
호출하지 않는다. 모델의 잘못된 스키마·인용 검증 실패는 처리 오류이며 더 좋은
출력이 나올 때까지 재생성하지 않는다. 중단 시 저장하지 못한 호출은 시간 미상이다.

검토는 응답·인용 원문이 정확히 동일한 경우만 공유한다. 직접 인용과 함께 실제
전달된 source_context를 확인한다. 원문에 있는 문자열만으로 정답을 판정하지
않으며 역할·부정 범위·시간 기준·질문에 필요한 값을 확인한다. 불확실성을 보존하는
관련 간접 답변은 기존 판정 기준을 유지한다. 날짜를 묻는데 발언을 반복하기만 하고
사건 날짜를 답하지 않으면 요청 값 미충족이다. 불필요한 사실 나열·반복은 별도
품질 문제다. 모델의 supported 판정은 정답 주석이 아니다.

오답 승인과 과잉 보류가 각각 기준선 이하이고 합계가 감소한 후보만 확대한다.
처리 오류 및 미검토 항목은 통과로 세지 않는다. 동률이면 오답, 과잉 보류, 빈 응답,
논리적 독립 실행 호출 수 순으로 비교한다. 실제 비용에서는 공유 호출을 한 번만
집계하며 기존 기준선 비용과 합산하지 않는다.

2026-10-15 완료한 진단에서는 적격 후보가 없어 계획대로 확대를 중단했다.
120문항 전체 재생과 새 60문항 최종 검증은 실행하지 않았으며, 새 최종 자료도
소비하지 않았다. 별도 프롬프트·검색 수정이나 운영 적용은 하지 않았다.
