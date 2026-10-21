질문·문맥 해석 재사용 비교
==========================

Qwen/BGE 모델과 독립 답변 검증을 유지했습니다. 개인 DB는 사용하지 않았습니다.
같은 입력의 준비 실행 이후 지정 횟수를 반복한 비교입니다. 새 질문의 속도 향상을 뜻하지 않습니다.
기준과 후보 양쪽에 기존 ID 단축·원문 답변안 옵션을 적용하고, 후보에만 해석 재사용을 추가했습니다.
기준/후보 순서를 교대하고 요청마다 모델 프롬프트 슬롯을 비웠습니다.
해석 캐시의 초기화 조건은 실행별로 표시합니다. 첫 요청 관측은 별도로 표시합니다.

CPU
---

원시 결과: C:\development\Personal-Memory-Agent\.local\latency-validated-drafts\.local\latency-goal\interpretation-cpu5\cpu\results.json
측정 완료: True
사례별 준비 실행 제외 반복 수: 5
해석 캐시: 반복 요청 사이에 유지

* candidate/simple_search: 중앙 0.038초 / 최대 0.046초; 품질 5/5; Qwen 호출 중앙 0회.
  RAM 관측 최대 6305.40625 MiB; 장치 VRAM 최대 575.0 MiB.
  Private commit 최대 8167.75390625 MiB; 시스템 여유 RAM 최소 313.21484375 MiB.
  단계별 중앙: 각 단계 0.1초 미만
* current/simple_search: 중앙 22.325초 / 최대 22.802초; 품질 5/5; Qwen 호출 중앙 1회.
  RAM 관측 최대 6304.9296875 MiB; 장치 VRAM 최대 575.0 MiB.
  Private commit 최대 8169.5078125 MiB; 시스템 여유 RAM 최소 163.765625 MiB.
  단계별 중앙: question_understanding 22.238초
* candidate/simple_answer: 중앙 80.338초 / 최대 81.572초; 품질 5/5; Qwen 호출 중앙 3회.
  RAM 관측 최대 5373.8359375 MiB; 장치 VRAM 최대 587.0 MiB.
  Private commit 최대 8177.734375 MiB; 시스템 여유 RAM 최소 17.43359375 MiB.
  단계별 중앙: embedding 0.119초, search_planning 34.769초, context_selection 6.951초, review 38.458초
* current/simple_answer: 중앙 146.842초 / 최대 152.858초; 품질 5/5; Qwen 호출 중앙 5회.
  RAM 관측 최대 5375.9765625 MiB; 장치 VRAM 최대 779.0 MiB.
  Private commit 최대 8178.24609375 MiB; 시스템 여유 RAM 최소 0.62109375 MiB.
  단계별 중앙: question_understanding 33.246초, search_planning 35.004초, context_resolution 32.052초, context_selection 7.119초, review 39.027초

첫 요청 관측(각 1회, 통계적 개선율로 해석하지 않음):

* current/simple_search: 21.971초, Qwen 1회, 독립 답변 검증 0회.
* candidate/simple_search: 22.308초, Qwen 1회, 독립 답변 검증 0회.
* current/simple_answer: 147.912초, Qwen 5회, 독립 답변 검증 1회.
* candidate/simple_answer: 144.339초, Qwen 5회, 독립 답변 검증 1회.

반복 품질 대조:

* simple_search: 답변/검색 순서·인용의 정확 일치 True.
* simple_answer: 답변/검색 순서·인용의 정확 일치 True.

GPU
---

원시 결과: C:\development\Personal-Memory-Agent\.local\latency-validated-drafts\.local\latency-goal\interpretation-gpu5-v3\gpu\results.json
측정 완료: True
사례별 준비 실행 제외 반복 수: 5
해석 캐시: 반복 요청 사이에 유지

* candidate/simple_search: 중앙 0.026초 / 최대 0.033초; 품질 5/5; Qwen 호출 중앙 0회.
  RAM 관측 최대 6387.96484375 MiB; 장치 VRAM 최대 7710.0 MiB.
  Private commit 최대 10467.01171875 MiB; 시스템 여유 RAM 최소 1039.73046875 MiB.
  단계별 중앙: 각 단계 0.1초 미만
* current/simple_search: 중앙 3.015초 / 최대 3.149초; 품질 5/5; Qwen 호출 중앙 1회.
  RAM 관측 최대 6387.66796875 MiB; 장치 VRAM 최대 7710.0 MiB.
  Private commit 최대 10467.2421875 MiB; 시스템 여유 RAM 최소 851.16015625 MiB.
  단계별 중앙: question_understanding 2.937초
* candidate/simple_answer: 중앙 8.005초 / 최대 8.161초; 품질 5/5; Qwen 호출 중앙 3회.
  RAM 관측 최대 4221.41015625 MiB; 장치 VRAM 최대 7721.0 MiB.
  Private commit 최대 10498.89453125 MiB; 시스템 여유 RAM 최소 476.484375 MiB.
  단계별 중앙: embedding 0.397초, search_planning 2.735초, context_selection 0.550초, review 4.169초
* current/simple_answer: 중앙 16.464초 / 최대 16.917초; 품질 5/5; Qwen 호출 중앙 5회.
  RAM 관측 최대 4234.515625 MiB; 장치 VRAM 최대 7727.0 MiB.
  Private commit 최대 10485.75390625 MiB; 시스템 여유 RAM 최소 262.51171875 MiB.
  단계별 중앙: question_understanding 6.434초, embedding 0.232초, search_planning 2.688초, context_resolution 2.210초, context_selection 0.550초, review 4.221초
* candidate/followup: 중앙 30.323초 / 최대 30.724초; 품질 5/5; Qwen 호출 중앙 8회.
  RAM 관측 최대 2751.265625 MiB; 장치 VRAM 최대 7724.0 MiB.
  Private commit 최대 10516.87109375 MiB; 시스템 여유 RAM 최소 316.80859375 MiB.
  단계별 중앙: embedding 0.170초, relevance_selection 20.129초, search_planning 5.845초, context_selection 0.696초, review 3.338초
* current/followup: 중앙 44.255초 / 최대 44.453초; 품질 5/5; Qwen 호출 중앙 11회.
  RAM 관측 최대 2751.296875 MiB; 장치 VRAM 최대 7724.0 MiB.
  Private commit 최대 10538.26171875 MiB; 시스템 여유 RAM 최소 338.52734375 MiB.
  단계별 중앙: token_budget 0.135초, question_understanding 7.383초, embedding 0.192초, relevance_selection 19.424초, search_planning 5.844초, context_resolution 7.112초, context_selection 0.708초, review 3.337초

첫 요청 관측(각 1회, 통계적 개선율로 해석하지 않음):

* current/simple_search: 3.306초, Qwen 1회, 독립 답변 검증 0회.
* candidate/simple_search: 3.193초, Qwen 1회, 독립 답변 검증 0회.
* current/simple_answer: 17.580초, Qwen 5회, 독립 답변 검증 1회.
* candidate/simple_answer: 17.092초, Qwen 5회, 독립 답변 검증 1회.
* current/followup: 45.038초, Qwen 11회, 독립 답변 검증 1회.
* candidate/followup: 44.408초, Qwen 11회, 독립 답변 검증 1회.

반복 품질 대조:

* simple_search: 답변/검색 순서·인용의 정확 일치 True.
* simple_answer: 답변/검색 순서·인용의 정확 일치 True.
* followup: 답변/검색 순서·인용의 정확 일치 True.

범위와 한계
-----------

11개 합성 기록의 제한된 질문 반복 결과입니다. 자동 품질 검사는 전 범위 의미 품질 보장이 아닙니다.
원문·기록 버전·대화·날짜·모델 설정이 달라지면 재사용하지 않습니다. 처음 묻는 질문에는 이득이 없습니다.
본 비교는 같은 DB를 복제해 동일한 초기 대화에서 실행했습니다. 일반 대화에 새 메시지가 추가되면 문맥 캐시는 미적중할 수 있습니다.
최종 답변 검증과 저장 시 출처 확인은 그대로 수행합니다. 모델 호출 수는 토큰 계산 요청을 제외합니다.
메모리는 약 1초 간격의 요청 중 관측입니다. 짧은 요청의 최대치 및 모델 로딩 최대치를 보장하지 않습니다.
RAM은 실험 Python·모델의 작업 집합, VRAM은 다른 앱을 포함한 장치 전체입니다.
Private commit은 물리 RAM 사용량이 아닙니다. 캐시는 모델을 내리지 않으며 RAM·VRAM 절감을 보장하지 않습니다.
CPU는 GPU 장치·연산·KV 오프로딩을 끕니다. GPU가 물리적으로 없는 PC는 검증하지 않았습니다.
모델 로딩·색인·준비 실행·브라우저 표시 시간은 전체 응답 시간에 포함하지 않습니다.
이 선택 옵션은 제품 기본 비활성입니다. 사용법: docs/interpretation_reuse.rst.

최종 확인 및 적용 상태
----------------------

* 오프라인 전체 테스트 864개 통과, 실패·오류·건너뜀 0. 이후 실행기 인자 정리 관련 4개도 재통과.
* 일반 모델 서버 두 개의 원래 명령·건강 상태 및 앱 응답을 복구 확인. 실험 서버 잔존 0.
* 개인 DB 미사용, 다른 앱 유지, 공식 main_suite 미실행.
* 기본 활성화 및 일반 앱 재시작은 하지 않음. 새 브랜치에서 선택 옵션으로 제공.
* 초기 GPU 실행의 빈 환경변수 오류는 수정·복구했고, 해석 키를 다듬기 전 시제품 결과는 직접 비교에서 제외해 별도 보존.
