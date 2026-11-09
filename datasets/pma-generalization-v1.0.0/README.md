# v3 기반 일반화 최소 기준점 v1.0.0

개발용 30문항과 확인용 30문항입니다. 실제 모델 평가는 실행하지 않았습니다.

각 목록: 여섯 능력 × 기본·질문 바꿔쓰기·유사 방해 기록·핵심 조건 변경 = 24문항, 실제 답변을 이어받는 대화 5턴, 빈 기억 1문항. 총 30문항은 독립 사례 30개가 아닙니다.

개발용은 v3 원문의 사례별 원문 범위를 유지하고 변형을 추가했습니다. 확인용의 질문과 핵심 이야기는 기존 최종 자료의 사용 이력이 확인되어 별개로 새로 작성했습니다. 검색 범위를 맞추는 배경은 v3 최종용의 원문 기록을 재사용하며 provenance.role=background로 표시합니다. 확인용 전체 원문이 미사용 자료라는 주장은 하지 않습니다. 인물·주제·원문은 두 목록 사이에 공유하지 않습니다. 상위 v3 원본 파일은 변경하지 않습니다.

기본·바꿔쓰기·방해 기록은 필수 답변 의미를 유지해야 합니다. 핵심 조건 변경에서는 새로운 사실에 맞는 답변이나 정보 부족 안내가 필요합니다. 정확 문자열 일치는 의미 판정이 아닙니다.

개발용 30개로 수정한 뒤 별도 확인용 30개를 실행하세요. 확인용 결과로 수정하면 그 확인용은 이후 회귀용이며 새 확인용을 마련해야 합니다. 전체 60개를 개발에 사용한 뒤 확인용 성능이라고 발표하지 마세요.

정답은 작성 과정에서 다시 읽어 검토했고 UTF-16 근거 구간과 접근 가능한 근거를 기계 검사합니다. 독립 사람 검토는 미완료입니다. 주어진 질문 범위 밖의 배경을 필수로 요구하지 않습니다. 대화의 일반 산술 턴은 개인 기록 인용을 요구하지 않습니다.

v3 자연 장문 NR-D-01-Q2의 선택 장소 근거를 문단 6·7, 배제 이유를 문단 3에 연결했습니다. 기존 v3 파일은 보존합니다.

상태 검사는 materialize fixture에 한정됩니다. 실제 DB 삭제·권한·검색 캐시·제품 저장 동의를 검증했다고 주장할 수 없습니다. 토큰수와 실제 시간은 미측정입니다. 긴 입력 예산 초과는 오답이나 통과로 합산하지 않습니다.

## 목록

| ID | 목록 | 능력/조건 | 상위 질문 |
|---|---|---|---|
| D-identity-BASE | development | D-identity / base | MC-09-Q1 |
| D-identity-PARAPHRASE | development | D-identity / paraphrase | MC-09-Q1 |
| D-identity-DISTRACTOR | development | D-identity / distractor | MC-09-Q1 |
| D-identity-CONTRAST | development | D-identity / contrast | MC-09-Q1 |
| D-status-BASE | development | D-status / base | MC-02-Q2 |
| D-status-PARAPHRASE | development | D-status / paraphrase | MC-02-Q2 |
| D-status-DISTRACTOR | development | D-status / distractor | MC-02-Q2 |
| D-status-CONTRAST | development | D-status / contrast | MC-02-Q2 |
| D-condition-BASE | development | D-condition / base | MC-08-Q2 |
| D-condition-PARAPHRASE | development | D-condition / paraphrase | MC-08-Q2 |
| D-condition-DISTRACTOR | development | D-condition / distractor | MC-08-Q2 |
| D-condition-CONTRAST | development | D-condition / contrast | MC-08-Q2 |
| D-multievidence-BASE | development | D-multievidence / base | NR-D-01-Q2 |
| D-multievidence-PARAPHRASE | development | D-multievidence / paraphrase | NR-D-01-Q2 |
| D-multievidence-DISTRACTOR | development | D-multievidence / distractor | NR-D-01-Q2 |
| D-multievidence-CONTRAST | development | D-multievidence / contrast | NR-D-01-Q2 |
| D-cumulative-BASE | development | D-cumulative / base | CUM-development-1800 |
| D-cumulative-PARAPHRASE | development | D-cumulative / paraphrase | CUM-development-1800 |
| D-cumulative-DISTRACTOR | development | D-cumulative / distractor | CUM-development-1800 |
| D-cumulative-CONTRAST | development | D-cumulative / contrast | CUM-development-1800 |
| D-access-BASE | development | D-access / base | STATE-development-shared |
| D-access-PARAPHRASE | development | D-access / paraphrase | STATE-development-shared |
| D-access-DISTRACTOR | development | D-access / distractor | STATE-development-shared |
| D-access-CONTRAST | development | D-access / contrast | STATE-development-shared |
| C-identity-BASE | confirmation | C-identity / base | 새 이야기 |
| C-identity-PARAPHRASE | confirmation | C-identity / paraphrase | 새 이야기 |
| C-identity-DISTRACTOR | confirmation | C-identity / distractor | 새 이야기 |
| C-identity-CONTRAST | confirmation | C-identity / contrast | 새 이야기 |
| C-status-BASE | confirmation | C-status / base | 새 이야기 |
| C-status-PARAPHRASE | confirmation | C-status / paraphrase | 새 이야기 |
| C-status-DISTRACTOR | confirmation | C-status / distractor | 새 이야기 |
| C-status-CONTRAST | confirmation | C-status / contrast | 새 이야기 |
| C-condition-BASE | confirmation | C-condition / base | 새 이야기 |
| C-condition-PARAPHRASE | confirmation | C-condition / paraphrase | 새 이야기 |
| C-condition-DISTRACTOR | confirmation | C-condition / distractor | 새 이야기 |
| C-condition-CONTRAST | confirmation | C-condition / contrast | 새 이야기 |
| C-multievidence-BASE | confirmation | C-multievidence / base | 새 이야기 |
| C-multievidence-PARAPHRASE | confirmation | C-multievidence / paraphrase | 새 이야기 |
| C-multievidence-DISTRACTOR | confirmation | C-multievidence / distractor | 새 이야기 |
| C-multievidence-CONTRAST | confirmation | C-multievidence / contrast | 새 이야기 |
| C-cumulative-BASE | confirmation | C-cumulative / base | 새 이야기 |
| C-cumulative-PARAPHRASE | confirmation | C-cumulative / paraphrase | 새 이야기 |
| C-cumulative-DISTRACTOR | confirmation | C-cumulative / distractor | 새 이야기 |
| C-cumulative-CONTRAST | confirmation | C-cumulative / contrast | 새 이야기 |
| C-access-BASE | confirmation | C-access / base | 새 이야기 |
| C-access-PARAPHRASE | confirmation | C-access / paraphrase | 새 이야기 |
| C-access-DISTRACTOR | confirmation | C-access / distractor | 새 이야기 |
| C-access-CONTRAST | confirmation | C-access / contrast | 새 이야기 |
| D-dialogue-T1 | development | generated_followup | CHAT-development-T1 |
| D-dialogue-T2 | development | generated_followup | CHAT-development-T2 |
| D-dialogue-T3 | development | generated_followup | CHAT-development-T3 |
| D-dialogue-T4 | development | generated_followup | CHAT-development-T4 |
| D-dialogue-T5 | development | generated_followup | CHAT-development-T5 |
| C-dialogue-T1 | confirmation | generated_followup | 새 이야기 |
| C-dialogue-T2 | confirmation | generated_followup | 새 이야기 |
| C-dialogue-T3 | confirmation | generated_followup | 새 이야기 |
| C-dialogue-T4 | confirmation | generated_followup | 새 이야기 |
| C-dialogue-T5 | confirmation | generated_followup | 새 이야기 |
| D-empty | development | behavioral_generalization | 새 이야기 |
| C-empty | confirmation | behavioral_generalization | 새 이야기 |
