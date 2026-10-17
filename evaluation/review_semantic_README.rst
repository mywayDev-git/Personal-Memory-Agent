의미 대조 검증기 재시험
=====================

evaluation.review_semantic_candidate는 평가 전용 LocalModels 하위 클래스다.
운영 검증기와 기본 설정은 변경하지 않는다. 기존 33문항, 195개 고유 입력,
248개 검색 조건별 결과를 재사용한다. 검색이 달라져 이미 선정된 입력만 대상으로
하며 추가 검색, 질문 분해, 새 초안 생성은 하지 않는다.

실행::

    python -m evaluation.review_semantic_run prepare
    python -m evaluation.review_semantic_run run
    python -m evaluation.fixed_answer_report pending --output output/fixed-answer-replay-v1/semantic-review-1
    python -m evaluation.fixed_answer_report record --output output/fixed-answer-replay-v1/semantic-review-1 --id <ID> --judgment <판정> --reason <원문대조>
    python -m evaluation.review_semantic_report

동일 모델 설정을 확인하고 이전 draft와 legacy_verify 성공 단계를 그대로 가져온다.
새 검증과 D의 조건부 1회 수정·재검증만 호출한다. 동일 응답·인용 원문의 기존
검토는 재사용하고 새로운 응답은 원문과 실제 제공된 주변 문맥을 대조해 검토한다.

검증 응답은 사건일, 정정 관계, 부정 범위의 원문 의미·답변 의미·인용·판정을
먼저 낸다. 적용되는 검사에 유효한 인용이 없으면 처리 오류로 구분한다.
실패 판정이 하나라도 있으면 최종 승인하지 못한다. 각 검사의 의미 판정 자체는
모델이 수행하므로 코드의 차단 테스트 통과만으로 의미 정확성을 주장하지 않는다.
기존 검증 호출의 2048 토큰 한도를 유지하며 스키마·출력 오류를 임의 재시도하지 않는다.

원시 확장 검사 결과는 journal의 모델 응답에 보존한다. 모델이 내는 검증 사유와
최종 사용자 응답을 구별하며, 빈 응답은 사유가 전달된 것으로 세지 않는다.
보고서는 이전 C/D와 새 C/D를 직접 대조하고 기존 A/B도 함께 표시한다.
실제 비용에서는 가져온 단계의 과거 호출을 제외한다.

원본 run-1 결과와 개인 기억 저장소를 수정하지 않는다. 수정에 사용한 진단 자료의
성능은 최종 검증 성능이 아니며 운영 적용 승인도 아니다.
