CPU·GPU 10초 목표 검증
=======================

현재 16GB 환경에서 다른 앱을 유지했습니다. 개인 DB는 사용하지 않았습니다.
검증 완료 기억 답변의 10초 목표는 CPU·GPU 모두 달성하지 못했습니다.
모델·검증 기준은 그대로이며, 검증 완료 응답까지의 시간을 측정했습니다.

Qwen3-8B Q4_K_M / BGE-M3 Q8_0, 생성 문맥 16,384·임베딩 문맥 8,192를 유지했습니다.
호출용 ID 단축과 원문 기반 답변안은 선택 옵션이며 제품 기본값은 비활성입니다.

직접 비교
---------

.. list-table::
   :header-rows: 1

   * - 조건
     - 기준 중앙/최대(초)
     - 후보 중앙/최대(초)
     - 중앙값 감소
     - 자동 품질 기준/후보
   * - GPU compact IDs only/simple_search
     - 3.173/3.381
     - 3.175/3.196
     - -0.1%
     - 5/5 · 5/5
   * - GPU compact IDs only/simple_answer
     - 22.848/22.964
     - 20.549/20.563
     - 10.1%
     - 5/5 · 5/5
   * - GPU compact IDs only/stopped
     - 28.981/30.109
     - 23.071/23.383
     - 20.4%
     - 5/5 · 5/5
   * - CPU paired validated drafts/simple_answer
     - 205.168/207.221
     - 147.197/149.992
     - 28.3%
     - 5/5 · 5/5
   * - GPU paired validated drafts/simple_answer
     - 22.817/23.064
     - 16.284/16.566
     - 28.6%
     - 20/20 · 20/20

검색은 CPU 입력 스레드 순차 비교에서 25.101초에서 22.064초였고 양쪽 5/5가 통과했습니다.
GPU 검색은 약 3.173초로, ID 단축 전후의 차이는 없었습니다. 재배치 비활성 옵션의 16초 검색은 아래의 실패 판정으로 최종 설정에서 제외했습니다.

메모리 관측
-----------

.. list-table::
   :header-rows: 1

   * - 조건
     - RAM 상주 관측 최대 기준/후보(GiB)
     - Private commit 최대 기준/후보(GiB)
     - 장치 VRAM 최대 기준/후보(GiB)
   * - CPU paired validated drafts
     - 5.27/5.24
     - 8.01/8.00
     - 0.71/0.87
   * - GPU paired validated drafts
     - 6.20/6.33
     - 10.23/10.24
     - 7.59/7.59

일관된 RAM·VRAM 절감은 확인하지 못했습니다. CPU 장치 VRAM은 다른 앱·데스크톱을 포함하며 모델 GPU 사용량이 아닙니다.
Private commit을 물리 RAM 사용량으로 해석하지 않습니다. 시스템 여유 RAM은 응답 비교 중 최소 약 13.6 MiB였습니다.

해석
----

* 기준/후보는 같은 모델·스레드·DB에서 순서를 교대했습니다. 서로 다른 실행의 백분율은 합치지 않습니다.
* 남은 시간은 모델의 질문 해석·검색 계획·문맥 해석·독립 검토가 대부분입니다. 이 소규모 DB의 DB·행렬·검색어 매칭은 수 밀리초 수준입니다. 기존 C++ 검색어 경로는 유지했고 추가 C++ 확장은 하지 않았습니다.
* CPU 스레드 선별은 순차 실행입니다. 상주 메모리와 시스템 상태 변화가 있어 그 효과를 순수하게 분리하지 못했습니다.
* 이전 -ngl 0만 사용한 CPU 수치는 엄격한 CPU 비교에서 제외했습니다. 새 CPU는 장치·연산·KV 오프로딩을 모두 끕니다.
* 추출형 답변안은 하나의 짧은 확정 선물 기록에만 해당합니다. 동일한 독립 검토가 거절하면 기존 생성 경로로 돌아갑니다.
* 호출용 ID는 모델 호출 뒤 원래 ID로 되돌리고 원래 스키마·인용·출처 검사를 적용합니다.
* 11개 고정 합성 기록의 반복 결과이며, 대량 DB·기록 추출 처리·모든 질문·첫 시작 시간을 대표하지 않습니다.
* 기본 기능 플래그는 유지했습니다. 전 범위 품질과 앱 전체 10초 보장을 이 실험만으로 승인하지 않습니다.
* 큰 캐시를 추가하지 않았습니다. 작업 집합과 private commit은 별개이며 VRAM은 장치 전체 값입니다.
* 메모리는 요청 구간에서 약 1초 간격으로 관측했습니다. 모델 로딩 최대치와 관측 사이의 짧은 최대치는 포함하지 않습니다.
* 표본 1회인 메모리/스레드 실험은 선별 결과입니다. 빠른 오류는 목표 달성이 아닙니다.

* 재배치 비활성 후보의 검색 5회는 약 16초였지만 답변 준비 실행과 본 측정 첫 회가 모두 300초 CHAT_TIMEOUT으로 실패했습니다. 재검색 2회와 근거 선택 호출이 늘어 제품 실행기에는 적용하지 않았고, 남은 반복을 중단했습니다. 미완료는 통과가 아닙니다.

재현: docs/latency_goal_validation.rst 및 scripts/run_latency_goal.ps1. 기본 실행은 계획만 표시합니다.
오프라인 테스트: 839개 / 실패 0 / 오류 0 / 건너뜀 0.
일반 모델 서버의 원래 명령·건강 상태와 앱 응답은 복구 기록으로 확인했습니다.

10초 응답 목표 비교
===================

모델·실행 조건은 각 results.json의 해시와 명세로 확인합니다. 합성 DB만 사용합니다.
준비 실행·색인·모델 로딩은 응답 시간에서 제외. 각 요청 전 실험 슬롯을 비웁니다.
품질 통과 수는 자동 선별 검사입니다. 공식 메인 평가나 전 범위 의미 검증이 아닙니다.
RAM은 Python·실험 모델 서버 작업 집합 합계, VRAM은 장치 전체 관측 최댓값입니다.
검증·원문·인용 검사를 생략하지 않습니다. 성능 보고서에 기록 원문을 넣지 않습니다.

GPU cache/batch screen (rejected)
---------------------------------

실행 완료: True / 가속: gpu
제품 소스 고정: True / 측정 코드 고정: True

* candidate/simple_answer: 중앙값 22.732초, 최대 22.877초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 4904.21875 MiB / 장치 VRAM 최대 7767.0 MiB.
  단계별 중앙값(배타 시간): question_understanding 6.427초, generation 4.955초, review 4.228초, search_planning 2.512초
* candidate/simple_search: 중앙값 3.263초, 최대 3.279초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 5/5.
  RAM 최대 6626.625 MiB / 장치 VRAM 최대 7762.0 MiB.
  단계별 중앙값(배타 시간): question_understanding 3.114초, embedding 0.061초, token_budget 0.019초, retrieval 0.005초
* candidate/stopped: 중앙값 28.580초, 최대 28.851초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 3862.92578125 MiB / 장치 VRAM 최대 7774.0 MiB.
  단계별 중앙값(배타 시간): context_resolution 7.675초, relevance_selection 7.409초, question_understanding 5.808초, review 4.746초
* current/simple_answer: 중앙값 22.802초, 최대 23.127초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 4653.3046875 MiB / 장치 VRAM 최대 7767.0 MiB.
  단계별 중앙값(배타 시간): question_understanding 6.427초, generation 4.959초, review 4.239초, search_planning 2.668초
* current/simple_search: 중앙값 3.243초, 최대 3.502초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 5/5.
  RAM 최대 6626.7578125 MiB / 장치 VRAM 최대 7762.0 MiB.
  단계별 중앙값(배타 시간): question_understanding 3.125초, embedding 0.094초, token_budget 0.017초, retrieval 0.005초
* current/stopped: 중앙값 28.668초, 최대 29.098초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 3438.60546875 MiB / 장치 VRAM 최대 7774.0 MiB.
  단계별 중앙값(배타 시간): context_resolution 7.679초, relevance_selection 7.417초, question_understanding 5.807초, review 4.742초

GPU compact IDs only
--------------------

실행 완료: True / 가속: gpu
제품 소스 고정: True / 측정 코드 고정: True

* candidate/simple_answer: 중앙값 20.549초, 최대 20.563초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 5926.37890625 MiB / 장치 VRAM 최대 7727.0 MiB.
  단계별 중앙값(배타 시간): question_understanding 6.427초, generation 4.200초, review 3.346초, search_planning 2.663초
* candidate/simple_search: 중앙값 3.175초, 최대 3.196초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 5/5.
  RAM 최대 6532.5234375 MiB / 장치 VRAM 최대 7725.0 MiB.
  단계별 중앙값(배타 시간): question_understanding 3.117초, embedding 0.051초, retrieval 0.005초, candidate_snapshot 0.004초
* candidate/stopped: 중앙값 23.071초, 최대 23.383초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 5103.3125 MiB / 장치 VRAM 최대 7773.0 MiB.
  단계별 중앙값(배타 시간): context_resolution 5.991초, question_understanding 5.821초, relevance_selection 4.471초, review 3.719초
* current/simple_answer: 중앙값 22.848초, 최대 22.964초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 5549.87890625 MiB / 장치 VRAM 최대 7727.0 MiB.
  단계별 중앙값(배타 시간): question_understanding 6.428초, generation 4.958초, review 4.231초, search_planning 2.649초
* current/simple_search: 중앙값 3.173초, 최대 3.381초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 5/5.
  RAM 최대 6520.6015625 MiB / 장치 VRAM 최대 7725.0 MiB.
  단계별 중앙값(배타 시간): question_understanding 3.093초, embedding 0.060초, token_budget 0.018초, retrieval 0.004초
* current/stopped: 중앙값 28.981초, 최대 30.109초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 5013.64453125 MiB / 장치 VRAM 최대 7777.0 MiB.
  단계별 중앙값(배타 시간): context_resolution 7.686초, relevance_selection 7.454초, question_understanding 5.816초, review 4.748초

CPU batch 8 reference
---------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 25.101초, 최대 25.416초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 5948.9296875 MiB / 장치 VRAM 최대 669.0 MiB.
  Private commit 최대 8157.7109375 MiB / 시스템 여유 RAM 최소 213.72265625 MiB.
  단계별 중앙값(배타 시간): question_understanding 25.035초, embedding 0.032초, token_budget 0.028초, retrieval 0.007초

CPU batch 16 screen
-------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 23.254초, 최대 23.254초; 완료 1/1; 자동 품질 1/1; 10초 이내·품질 충족 0/1.
  RAM 최대 8176.29296875 MiB / 장치 VRAM 최대 665.0 MiB.
  Private commit 최대 8168.12890625 MiB / 시스템 여유 RAM 최소 99.12890625 MiB.
  단계별 중앙값(배타 시간): question_understanding 23.190초, embedding 0.029초, token_budget 0.022초, retrieval 0.008초

CPU batch 24 screen
-------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 21.552초, 최대 21.552초; 완료 1/1; 자동 품질 1/1; 10초 이내·품질 충족 0/1.
  RAM 최대 6099.23046875 MiB / 장치 VRAM 최대 665.0 MiB.
  Private commit 최대 8167.19921875 MiB / 시스템 여유 RAM 최소 1253.265625 MiB.
  단계별 중앙값(배타 시간): question_understanding 21.501초, embedding 0.033초, retrieval 0.008초, token_budget 0.007초

CPU batch 24 verification
-------------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 22.064초, 최대 22.283초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 7366.015625 MiB / 장치 VRAM 최대 665.0 MiB.
  Private commit 최대 8193.36328125 MiB / 시스템 여유 RAM 최소 15.12890625 MiB.
  단계별 중앙값(배타 시간): question_understanding 21.990초, embedding 0.032초, token_budget 0.029초, retrieval 0.008초

CPU paired validated drafts
---------------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* candidate/simple_answer: 중앙값 147.197초, 최대 149.992초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 5364.5546875 MiB / 장치 VRAM 최대 894.0 MiB.
  Private commit 최대 8189.26953125 MiB / 시스템 여유 RAM 최소 72.09375 MiB.
  단계별 중앙값(배타 시간): review 38.668초, search_planning 35.124초, question_understanding 33.979초, context_resolution 32.012초
* current/simple_answer: 중앙값 205.168초, 최대 207.221초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 5393.66015625 MiB / 장치 VRAM 최대 724.0 MiB.
  Private commit 최대 8203.03515625 MiB / 시스템 여유 RAM 최소 13.6328125 MiB.
  단계별 중앙값(배타 시간): generation 54.294초, search_planning 35.654초, question_understanding 33.849초, context_resolution 30.811초

GPU paired validated drafts
---------------------------

실행 완료: True / 가속: gpu
제품 소스 고정: True / 측정 코드 고정: True

* candidate/simple_answer: 중앙값 16.284초, 최대 16.566초; 완료 20/20; 자동 품질 20/20; 10초 이내·품질 충족 0/20.
  RAM 최대 6486.953125 MiB / 장치 VRAM 최대 7774.0 MiB.
  Private commit 최대 10486.5859375 MiB / 시스템 여유 RAM 최소 154.97265625 MiB.
  단계별 중앙값(배타 시간): question_understanding 6.434초, review 4.167초, search_planning 2.667초, context_resolution 2.213초
* current/simple_answer: 중앙값 22.817초, 최대 23.064초; 완료 20/20; 자동 품질 20/20; 10초 이내·품질 충족 0/20.
  RAM 최대 6351.58984375 MiB / 장치 VRAM 최대 7774.0 MiB.
  Private commit 최대 10473.83984375 MiB / 시스템 여유 RAM 최소 50.84375 MiB.
  단계별 중앙값(배타 시간): question_understanding 6.435초, generation 4.967초, review 4.232초, search_planning 2.657초

Rejected CPU no-repack verification
-----------------------------------

실행 완료: False / 가속: cpu
제품 소스 고정: None / 측정 코드 고정: None

* candidate/simple_answer: 완료된 시간 표본 없음; 완료 0/1; 자동 품질 0/1; 10초 이내·품질 충족 0/1.
  RAM 최대 5637.21875 MiB / 장치 VRAM 최대 589.0 MiB.
  Private commit 최대 5024.96875 MiB / 시스템 여유 RAM 최소 197.98046875 MiB.
  단계별 중앙값(배타 시간): 
* candidate/simple_search: 중앙값 15.969초, 최대 16.540초; 완료 5/5; 자동 품질 5/5; 10초 이내·품질 충족 0/5.
  RAM 최대 7695.796875 MiB / 장치 VRAM 최대 583.0 MiB.
  Private commit 최대 4960.78515625 MiB / 시스템 여유 RAM 최소 9.390625 MiB.
  단계별 중앙값(배타 시간): question_understanding 15.891초, embedding 0.030초, token_budget 0.026초, retrieval 0.007초

cpu-memory-default-before
-------------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 21.345초, 최대 21.345초; 완료 1/1; 자동 품질 1/1; 10초 이내·품질 충족 0/1.
  RAM 최대 8522.28515625 MiB / 장치 VRAM 최대 583.0 MiB.
  Private commit 최대 8166.26953125 MiB / 시스템 여유 RAM 최소 329.09765625 MiB.
  단계별 중앙값(배타 시간): question_understanding 21.293초, embedding 0.030초, retrieval 0.010초, candidate_snapshot 0.007초

cpu-memory-no-repack
--------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 16.020초, 최대 16.020초; 완료 1/1; 자동 품질 1/1; 10초 이내·품질 충족 0/1.
  RAM 최대 7929.68359375 MiB / 장치 VRAM 최대 583.0 MiB.
  Private commit 최대 4960.484375 MiB / 시스템 여유 RAM 최소 81.09765625 MiB.
  단계별 중앙값(배타 시간): question_understanding 15.952초, embedding 0.031초, token_budget 0.022초, retrieval 0.008초

cpu-decode-4-screen
-------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 24.834초, 최대 24.834초; 완료 1/1; 자동 품질 1/1; 10초 이내·품질 충족 0/1.
  RAM 최대 5624.765625 MiB / 장치 VRAM 최대 583.0 MiB.
  Private commit 최대 8192.3203125 MiB / 시스템 여유 RAM 최소 1258.65625 MiB.
  단계별 중앙값(배타 시간): question_understanding 24.774초, embedding 0.031초, token_budget 0.021초, retrieval 0.005초

cpu-decode-16-screen
--------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 20.417초, 최대 20.417초; 완료 1/1; 자동 품질 1/1; 10초 이내·품질 충족 0/1.
  RAM 최대 6689.86328125 MiB / 장치 VRAM 최대 589.0 MiB.
  Private commit 최대 8194.84375 MiB / 시스템 여유 RAM 최소 128.03125 MiB.
  단계별 중앙값(배타 시간): question_understanding 20.330초, token_budget 0.042초, embedding 0.030초, retrieval 0.007초

cpu-server-default-screen
-------------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 21.490초, 최대 21.490초; 완료 1/1; 자동 품질 1/1; 10초 이내·품질 충족 0/1.
  RAM 최대 8059.03515625 MiB / 장치 VRAM 최대 583.0 MiB.
  Private commit 최대 8162.3671875 MiB / 시스템 여유 RAM 최소 112.79296875 MiB.
  단계별 중앙값(배타 시간): question_understanding 21.430초, embedding 0.040초, candidate_snapshot 0.008초, retrieval 0.007초

cpu-memory-default-after
------------------------

실행 완료: True / 가속: cpu
제품 소스 고정: True / 측정 코드 고정: True

* current/simple_search: 중앙값 21.987초, 최대 21.987초; 완료 1/1; 자동 품질 1/1; 10초 이내·품질 충족 0/1.
  RAM 최대 7295.2734375 MiB / 장치 VRAM 최대 583.0 MiB.
  Private commit 최대 8167.265625 MiB / 시스템 여유 RAM 최소 5.296875 MiB.
  단계별 중앙값(배타 시간): question_understanding 21.926초, embedding 0.031초, token_budget 0.017초, retrieval 0.008초

판정 주의
---------

* 같은 조건의 current/candidate만 직접 비교합니다. 서로 다른 실행의 숫자는 참고 비교입니다.
* 5회 반복의 최댓값은 긴 꼬리를 추정하는 데 부족합니다. 전체 앱의 95% 보장으로 해석하지 않습니다.
* 빨리 실패한 요청은 목표 달성으로 계산하지 않습니다. 오류·미완료·검토 대기는 통과가 아닙니다.
* 조건부 선별 검사의 통과만으로 모델 품질의 일반적 동등성이나 제품 기본값 변경을 승인하지 않습니다.

CPU 격리는 서버 실행 명령으로 확인합니다. GPU가 물리적으로 없는 PC의 검증은 별도입니다.
Private commit은 물리 RAM과 다릅니다. page_fault_delta는 소프트 폴트를 포함하므로 디스크 페이징 횟수가 아닙니다.

