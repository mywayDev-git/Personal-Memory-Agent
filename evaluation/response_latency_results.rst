응답 속도와 근거 품질 비교
==========================

2026-10-21 CPU 해석 정정: 아래 과거 ``cpu-basic`` 결과는 ``-ngl 0``만 사용해
보조 GPU 연산·KV 오프로딩을 명시적으로 차단하지 않았습니다. 관측값은 보존하지만
엄격한 CPU 전용 성능으로 해석하지 않습니다. 새 CPU 비교는 ``--device none
--no-op-offload --no-kv-offload``까지 사용합니다. GPU 결과에는 이 정정이 적용되지 않습니다.

개인 DB를 사용하지 않고 합성 원문 11개와 별도 다국어 문서 216개로 측정했다. 기존 변경은 5a57d39로 원래 브랜치에 보존·푸시했고, 성능 작업은 codex/response-latency에 분리했다. 생성·임베딩 모델과 배치·표시·캐시의 제품 기본값은 유지했다.

이전 GPU 보고서의 검색 약 3.1초·기억 답변 약 15.3초는 질문과 실행 조건이 다른 참고값이다. 이번 개선율의 분모로 사용하지 않고 현재 변경이 포함된 새 기준선과 비교했다.

채택 판정
---------

단순 답변 20회 속도 기준: 통과. 핵심 복합 사례 품질 기준: 미충족. 전체 채택 조건: 미충족.

단순 답변 중앙값 감소율은 56.9%다. 이 수치를 복합 질문 전체의 개선율로 해석하지 않는다.

추가한 단일 변형 자동 설정 5회 기준선은 중앙값 17.360초였다. 기존 코드도 이 별도 실행에서는 입력 축소 후보와 비슷한 시간에 답했다. 교차 실행과 단일 변형 실행에서 추가 검색 분기가 달랐으며, 순서·서버 상태 등의 영향을 분리해 확정하지 못했다. 따라서 이 교차 조건의 감소율을 일관된 운영 속도 개선으로 채택하지 않는다.

모든 핵심 사례가 통과해야 기본값 변경 후보가 된다. 인용 위치가 정확하고 독립 모델 검증이 성공해도 동명이인의 직업을 합치거나 반납 계획을 실제 실행으로 해석하면 실패다. 정답 근거 누락·과도한 거절도 품질 실패로 센다.

측정 조건
---------

Intel Core i7-13700(16코어/24스레드), 물리 RAM 16,940,138,496바이트, RTX 3060 8,192 MiB, 드라이버 617.42. llama.cpp 0.6.0-dev build 11524 (86a283532, Clang 20.1.8). 생성 문맥 16,384·임베딩 8,192 토큰을 유지했다. 18181/18182 포트만 실험에 사용했고, 사용자 승인으로 기존 앱을 일시 종료했다.

후보별 준비 실행 1회를 제외하고 5회, 최종 비교는 같은 서버·질문·DB의 두 변형을 반복마다 역순으로 실행해 각각 20회 측정했다. P95는 nearest-rank 방식이며 5회 P95는 최댓값이다. 서로 다른 실행의 표본을 합치지 않았다. 실행 실패는 완주 지연 통계와 분리하고 실패율·품질 실패에 포함했다. 품질 실패한 완주 요청의 시간도 표에는 남기지만, 품질 조건을 통과한 속도 개선으로 세지 않는다.

측정은 모델 서버 HTTP 호출을 포함한 Service.search / ChatEngine.message 함수 호출의 벽시계다. 기억 답변에는 독립 검증과 최종 DB 커밋이 포함된다. FastAPI 전송·브라우저 렌더링, 단순 검색의 검색 결과 세션 저장은 포함하지 않는다. 최종 20회와 이후 실행 설정·배치 비교는 함수 반환 시 시간을 멈추고 정답 채점·평가 파일 저장을 제외한다. 그 이전 기준선·모델·복합 품질 실험의 벽시계에는 평가 파일 저장·채점·메시지 재조회 비용도 소량 포함되었다. 이 측정 경계 차이를 JSON measurement_scope로 표시하고 서로 다른 경계의 표본을 합산하지 않았다.

최종 20회 교차 비교
-------------------

.. list-table::
   :header-rows: 1

   * - 변형/사례
     - 중앙값 초
     - P95 초
     - 품질/표본
     - 실행 실패
     - RAM/VRAM MiB
   * - baseline/simple_search
     - 2.738
     - 2.860
     - 20/20
     - 0
     - 4338.430/7630.000
   * - baseline/simple_answer
     - 41.384
     - 45.832
     - 20/20
     - 0
     - 5453.105/7651.000
   * - planning/simple_search
     - 2.798
     - 2.943
     - 20/20
     - 0
     - 4332.129/7630.000
   * - planning/simple_answer
     - 17.833
     - 18.749
     - 20/20
     - 0
     - 5399.961/7642.000

planning은 평가기에만 있는 실험이다. 추가 검색 판단의 중복 query_plan·순위 점수·화면 설명을 줄이고 질문·전체 원문·인용·시간·사실 검토 경고·필터·대화 이력은 유지한다. 추가 검색 판단, 관련성 판정과 독립 근거 검증을 생략하지 않는다. 제품에는 이 입력 축소를 적용하지 않았다.

앞선 5회 교차 실험(최종 20회와 합산하지 않음)

.. list-table::
   :header-rows: 1

   * - 변형/사례
     - 중앙값 초
     - P95 초
     - 품질/표본
   * - baseline/simple_search
     - 2.837
     - 2.852
     - 5/5
   * - baseline/simple_answer
     - 41.965
     - 47.036
     - 5/5
   * - planning/simple_search
     - 2.813
     - 2.856
     - 5/5
   * - planning/simple_answer
     - 17.670
     - 18.337
     - 5/5
   * - planning_plain/simple_search
     - 2.791
     - 2.829
     - 5/5
   * - planning_plain/simple_answer
     - 15.812
     - 16.251
     - 5/5

기준선과 복합 품질
------------------

baseline-gpu-full

.. list-table::
   :header-rows: 1

   * - 변형/사례
     - 중앙값 초
     - P95 초
     - 품질/표본
     - 실행 실패
   * - baseline/simple_search
     - 4.121
     - 4.134
     - 5/5
     - 0
   * - baseline/alias_ko
     - 11.159
     - 11.754
     - 5/5
     - 0
   * - baseline/alias_en
     - 11.034
     - 11.080
     - 5/5
     - 0
   * - baseline/typo
     - 11.235
     - 11.671
     - 5/5
     - 0
   * - baseline/simple_answer
     - 40.969
     - 48.160
     - 5/5
     - 0
   * - baseline/stopped
     - 34.366
     - 34.383
     - 0/5
     - 0
   * - baseline/negation
     - 15.230
     - 15.480
     - 5/5
     - 0
   * - baseline/plan
     - 45.443
     - 50.352
     - 2/5
     - 0
   * - baseline/identity
     - 37.733
     - 39.068
     - 5/5
     - 0
   * - baseline/followup
     - 62.871
     - 66.419
     - 0/5
     - 0
   * - baseline/additional_search
     - 14.281
     - 15.342
     - 5/5
     - 0
   * - baseline/no_evidence
     - 5.153
     - 5.325
     - 5/5
     - 0
   * - baseline/long_evidence
     - 69.425
     - 80.027
     - 5/5
     - 0
   * - baseline/concurrent
     - 21.232
     - 21.716
     - 5/5
     - 0

planning-critical

.. list-table::
   :header-rows: 1

   * - 변형/사례
     - 중앙값 초
     - P95 초
     - 품질/표본
     - 실행 실패
   * - planning/stopped
     - 34.460
     - 36.155
     - 0/5
     - 0
   * - planning/negation
     - 19.543
     - 19.642
     - 5/5
     - 0
   * - planning/plan
     - 45.145
     - 45.616
     - 5/5
     - 0
   * - planning/identity
     - 37.038
     - 37.942
     - 5/5
     - 0
   * - planning/followup
     - 55.670
     - 56.936
     - 0/5
     - 0
   * - planning/additional_search
     - 14.525
     - 15.986
     - 5/5
     - 0
   * - planning/no_evidence
     - 5.066
     - 5.155
     - 5/5
     - 0
   * - planning/long_evidence
     - 58.461
     - 60.186
     - 5/5
     - 0
   * - planning/concurrent
     - 19.696
     - 19.938
     - 5/5
     - 0
   * - planning/multi_hop
     - 14.590
     - 14.671
     - 0/5
     - 0

학습 중단 질문에서는 기준선과 planning 모두 '중단한 기록은 없다'고 말하면서 '공부를 접었다'는 기록을 설명했다. 인용이 정확해도 의미가 모순되어 양쪽 모두 0/5다. 직접 답변 대조에서 발견한 이 오류를 scoring_version=5에 반영해 모든 고정 응답을 같은 기준으로 읽기 전용 재채점했다. 중단 사건을 부정하는 것과 중단 날짜가 불명인 것은 구분한다. 기준선의 plan은 2/5만 계획과 실행 불확실성을 모두 설명했고 나머지는 근거 부족으로 거절했다. followup은 회사 동료를 지정한 앞선 답변 이후 동아리 친구의 수학 교사 직업을 답하거나 두 직업을 한 사람에게 합쳐 0/5였다. 새 정답 검사는 기대 직업 구절과 허용 원문 범위도 확인한다. 이 보조 검사만으로 일반적인 답변 정확성·완전성을 보장하지 않으며, 실패 응답을 원문과 함께 확인했다. concurrent는 실제 배경 추출 진행 중 요청 도착과 배경 저장 성공을 확인한다. 날짜 조건이 있는 simple_answer와 다른 질문이므로 두 전체 시간의 차이를 대기 비용으로 해석하지 않는다.

생성·임베딩 모델 비교
---------------------

.. list-table::
   :header-rows: 1

   * - 실험
     - 양성 P@8
     - 양성 R@8
     - 음성 P/R
     - 회귀 질문 수
     - 제외
   * - baseline-current-comparison
     - 0.925
     - 0.800
     - 1.000/1.000
     - 0
     - False
   * - q4-gpu-full
     - 0.856
     - 0.731
     - 1.000/1.000
     - 14
     - True
   * - q8-gpu-full
     - 0.854
     - 0.729
     - 1.000/1.000
     - 15
     - True
   * - qwen-embedding-gpu-full
     - 0.890
     - 0.765
     - 0.967/0.967
     - 13
     - True

모델별 기본 응답 5회(별도 서버 실행 간 비율을 최종 개선율로 사용하지 않음)

.. list-table::
   :header-rows: 1

   * - 실험/사례
     - 중앙값 초
     - P95 초
     - 품질/표본
     - 실행 실패
     - RAM/VRAM MiB
   * - baseline-current-comparison/simple_search
     - 2.837
     - 2.852
     - 5/5
     - 0
     - 2881.879/7685.000
   * - baseline-current-comparison/simple_answer
     - 41.965
     - 47.036
     - 5/5
     - 0
     - 5373.332/7691.000
   * - q4-gpu-full/simple_search
     - 3.487
     - 3.517
     - 5/5
     - 0
     - 4144.988/6149.000
   * - q4-gpu-full/simple_answer
     - 18.913
     - 19.052
     - 5/5
     - 0
     - 4852.652/6164.000
   * - q8-gpu-full/simple_search
     - 6.240
     - 6.281
     - 5/5
     - 0
     - 2948.156/7658.000
   * - q8-gpu-full/simple_answer
     - 28.451
     - 30.812
     - 5/5
     - 0
     - 3146.914/7674.000
   * - qwen-embedding-gpu-full/simple_search
     - 7.897
     - 8.270
     - 5/5
     - 0
     - 7370.727/7697.000
   * - qwen-embedding-gpu-full/simple_answer
     - 31.147
     - 38.146
     - 5/5
     - 0
     - 8329.805/7703.000

각 모델의 90개 질문 이해를 새로 실행했다. 이 지표는 기존 다국어 평가와 같은 선택적 LLM 관련성 검토 전의 검색·융합·상위 8개 단계다. 전체 관련성 판정과 답변·독립 검증은 별도 11원문 시나리오에서 측정한다. 평균이 아니라 질문별 P@8·R@8 비하락과 Python/API/ML 별칭 동등성을 검사했다. 회귀한 모델은 단순 검색·답변 5회만 추가 측정하고 복합 사례는 생략했다. 실행하지 않은 사례는 통과로 세지 않는다. 설정·코드·모델을 함께 바꾼 조합은 개별 후보가 품질을 통과한 뒤에만 채택 평가 대상이다.

호출 병목과 선택 옵션
---------------------

.. list-table::
   :header-rows: 1

   * - 변형/사례
     - 생성 호출 중앙값
     - 생성 HTTP 초
     - 검색 반복 중앙값
     - 토큰 계산 HTTP 초
   * - baseline/simple_answer
     - 12.0
     - 40.793
     - 2.0
     - 0.150
   * - planning/simple_answer
     - 7.0
     - 17.110
     - 1.0
     - 0.070

기존 경로는 충분한 초기 근거가 있어도 추가 검색과 후보 판정 배치를 수행하는 경우가 있었다. 병목의 우선순위는 생성·관련성 판정·추가 검색 판단이며 토큰 계산 단축만으로 20%를 설명하기 어렵다. 단계 포함 시간은 중복되므로 합산하지 않는다. JSON에는 단계별 exclusive 값, 반복 횟수, HTTP 호출 시간·횟수·서버가 제공한 토큰 수와 표본별 측정값을 남겼다. 단계별 중앙값 역시 서로 다른 표본에서 나올 수 있어 합계가 전체 중앙값과 같지 않다.

기준선의 주요 병목(각 단계의 exclusive 중앙값, 상위 3개)

.. list-table::
   :header-rows: 1

   * - 사례
     - 상위 단계 초
     - 검색/생성/검증 반복 중앙값
   * - simple_search
     - question_understanding 3.997, embedding 0.080, token_budget 0.023
     - 미계측/미계측/미계측
   * - long_evidence
     - relevance_selection 31.587, context_resolution 13.418, question_understanding 5.716
     - 1/1/1
   * - followup
     - relevance_selection 30.984, context_resolution 7.070, search_planning 5.597
     - 2/1/1
   * - plan
     - relevance_selection 17.963, review 10.894, generation 7.537
     - 1/2/2
   * - concurrent
     - model_wait 6.813, generation 3.604, question_understanding 3.369
     - 1/1/1

긴 근거와 후속 질문은 관련성 판정 비용이 컸고 계획 질문은 생성·검증을 두 번 수행했다. 배경 처리 중 요청의 model_wait는 실제 모델 차례 대기다. 독립 검증을 없애거나 다른 질문·정책의 판정 결과를 재사용해 이 시간을 줄이는 방식은 채택하지 않았다.

판정 배치와 캐시

.. list-table::
   :header-rows: 1

   * - 변형/사례
     - 중앙값 초
     - P95 초
     - 품질/표본
     - 실행 실패
     - RAM/VRAM MiB
   * - selection-batches/baseline/selection_batch
     - 29.449
     - 29.559
     - 5/5
     - 0
     - 5991.449/7639.000
   * - selection-batches/cached/selection_batch
     - 29.462
     - 29.506
     - 5/5
     - 0
     - 5990.422/7639.000
   * - selection-batches/batch8/selection_batch
     - 30.243
     - 30.279
     - 5/5
     - 0
     - 6196.762/7634.000

.. list-table::
   :header-rows: 1

   * - 변형/사례
     - 생성 호출 중앙값
     - 토큰 계산 호출 중앙값
     - 캐시 적중 중앙값
   * - baseline/selection_batch
     - 3
     - 3
     - 0
   * - cached/selection_batch
     - 3
     - 3
     - 0
   * - batch8/selection_batch
     - 2
     - 2
     - 0

실행 설정

.. list-table::
   :header-rows: 1

   * - 변형/사례
     - 중앙값 초
     - P95 초
     - 품질/표본
     - 실행 실패
     - RAM/VRAM MiB
   * - gpu-flash-auto-basic/baseline/simple_search
     - 2.736
     - 2.861
     - 5/5
     - 0
     - 4985.352/7733.000
   * - gpu-flash-auto-basic/baseline/simple_answer
     - 17.360
     - 17.738
     - 5/5
     - 0
     - 4889.633/7741.000
   * - gpu-flash-on/baseline/simple_search
     - 2.770
     - 2.914
     - 5/5
     - 0
     - 5926.074/7630.000
   * - gpu-flash-on/baseline/simple_answer
     - 17.400
     - 17.684
     - 5/5
     - 0
     - 5822.543/7638.000
   * - gpu-flash-off/baseline/simple_search
     - 11.239
     - 11.566
     - 5/5
     - 0
     - 6217.582/7859.000
   * - gpu-flash-off/baseline/simple_answer
     - 33.353
     - 34.495
     - 5/5
     - 0
     - 8032.203/7947.000
   * - hybrid-basic/baseline/simple_search
     - 1.819
     - 1.847
     - 5/5
     - 0
     - 6212.055/7714.000
   * - hybrid-basic/baseline/simple_answer
     - 37.499
     - 39.982
     - 5/5
     - 0
     - 6637.250/7733.000
   * - cpu-basic/baseline/simple_search
     - 5.645
     - 5.706
     - 5/5
     - 0
     - 8278.906/1113.000
   * - cpu-basic/baseline/simple_answer
     - 150.194
     - 153.076
     - 5/5
     - 0
     - 7463.445/1174.000
   * - gpu-flash-on-quality-screen/baseline/stopped
     - 34.446
     - 34.783
     - 0/5
     - 0
     - 6854.688/7742.000

.. list-table::
   :header-rows: 1

   * - 실험
     - 검색 반복 중앙값
     - 생성 호출 중앙값
     - 생성 HTTP 초
   * - gpu-flash-auto-basic
     - 1
     - 7
     - 16.830
   * - gpu-flash-on
     - 1
     - 7
     - 16.875
   * - gpu-flash-off
     - 1
     - 7
     - 30.815
   * - hybrid-basic
     - 2
     - 12
     - 36.734
   * - cpu-basic
     - 2
     - 12
     - 148.430

이 설정 비교는 종단 응답 시간이다. 호출 횟수와 추가 검색 판단도 달라졌으므로 차이를 모두 Flash Attention 커널 계산 속도의 효과로 단정하지 않는다. 빠른 설정은 학습 중단 사례부터 추가 품질 검사를 했고, 실패하면 나머지 복합 사례를 통과했다고 간주하지 않는다.

selection_batch는 11개 모든 후보를 기존 인용 문맥 범위로 판정하는 구성 요소 실험이며 최종 답변 지연이 아니다. 관련성 판정은 기존 compact_evidence의 인용 시작 200자 전부터 600자 뒤까지인 범위를 유지한다. 추가 검색 판단의 전체 source_text와 최종 원문 인용 검증 범위는 줄이지 않았다. cached는 정확히 같은 토큰 계산 입력에만 요청 내부 128개 LRU를 적용한다. 질문·원문 버전·정책이 달라진 판정 결과를 재사용하는 캐시는 추가하지 않았다. plain은 별도의 5회 교차 실험에서 planning 17.670초 대비 15.812초였지만 단순 답변의 제한된 결과이므로 표시 형식의 기본값을 바꾸지 않았다.

준비 시간·재색인 비용
---------------------

.. list-table::
   :header-rows: 1

   * - 실험
     - 해시 확인 초
     - 서버 시작 초
     - 11개 색인 준비 초
     - 216개 문서 임베딩 초
   * - baseline-gpu-full
     - 미측정
     - 6.204
     - 2.264
     - 미측정
   * - baseline-current-comparison
     - 2.890
     - 7.594
     - 0.118
     - 1.167
   * - q4-gpu-full
     - 11.834
     - 8.153
     - 0.119
     - 1.146
   * - q8-gpu-full
     - 19.319
     - 5.139
     - 0.199
     - 1.190
   * - qwen-embedding-gpu-full
     - 5.373
     - 15.249
     - 1.010
     - 1.657
   * - planning-critical
     - 3.202
     - 5.107
     - 0.138
     - 미측정
   * - planning-final20
     - 2.837
     - 7.152
     - 0.148
     - 미측정
   * - selection-batches
     - 2.866
     - 6.162
     - 0.151
     - 미측정
   * - gpu-flash-on
     - 2.968
     - 7.130
     - 0.212
     - 미측정
   * - gpu-flash-off
     - 3.040
     - 9.121
     - 0.166
     - 미측정
   * - hybrid-basic
     - 2.941
     - 5.091
     - 0.145
     - 미측정
   * - cpu-basic
     - 3.057
     - 6.625
     - 0.147
     - 미측정
   * - gpu-flash-auto-basic
     - 2.845
     - 6.619
     - 0.129
     - 미측정
   * - gpu-flash-on-quality-screen
     - 2.957
     - 6.144
     - 0.161
     - 미측정

같은 임베딩 프로필은 기존 합성 색인을 복사하므로 11개 준비 시간이 재임베딩 속도는 아니다. Qwen 임베딩은 별도 실험 DB에서만 새 벡터를 만들었다. 양쪽 벡터는 1024차원 float32로 원시 벡터 저장량은 기억당 4096바이트이며 DB·색인 부가 비용은 별도다. 실제 재색인은 원문 길이·분할 수·추출 및 검증·동시 작업에 따라 달라지므로 216개 문서 임베딩만으로 개인 DB 총 소요 시간을 확정할 수 없다. 이번 작업은 개인 DB 재색인을 실행하지 않았다.

해시 확인이 OS 파일 캐시를 데우므로 시작 시간은 콜드 부팅 측정이 아니다. RAM은 평가 Python과 소유한 서버의 작업 집합 합계로 공유 페이지가 중복될 수 있다. VRAM은 바탕화면 등을 포함한 GPU 전체 사용량을 1초마다 관측한 최댓값이며 순간 절대 최대는 아니다.

재현성과 한계
-------------

response_latency_results.json에는 파일 SHA-256·서버 인자·코드 해시·표본과 질문별 지표가 있다. response_latency_seed.json은 측정 당시의 합성 원문·ID·시각·벡터를 논리 행으로 저장한다. 처음 14사례 기준선은 종료 시 코드 검사가 추가되기 전 실행이므로 종료 해시 검증 값은 null이다. 표본 84개 완주와 후속 기준선의 동일 제품 소스 목록을 확인하고 최신 scoring_version=5로 읽기 전용 재채점했다. 후속 실험은 제품·평가 코드 종료 해시 검사를 통과해야 집계했다.

최종 20회 전에 독립 검색의 요청 범위 계측 연결과 반환 시점 타이머를 보완하고 테스트한 뒤 소스를 다시 고정했다. 이 계측 연결의 시간을 별도의 속도 개선으로 주장하지 않는다. 각 실행의 Git 참조와 실제 파일 해시를 JSON에 남겼다.

초기 C 드라이브 CPU 실행은 다운로드 중 공간 부족으로 중단되어 통계에서 제외했다. 두 초기 시험의 합성 스키마 오류와 이전 채점기 파일도 제외했다. D 드라이브로 옮긴 것은 이번 작업에서 만든 다운로드 파일이며 이후 여유 공간 검사와 원자적 결과 저장을 추가했다.

생성 후보는 공식 Qwen 원본 참조 리비전과 Unsloth GGUF 배포 리비전·파일 해시를 고정했다. 배포자가 정확한 변환 도구 리비전을 공개하지 않아 변환 재빌드까지 재현 가능하다고 주장하지 않는다. 런타임 버전은 변환 도구 버전의 증거가 아니다. 이 제한은 모델 채택 검토에 남긴다. 임베딩 후보는 Qwen 공식 GGUF 배포 파일이다. 고정 주소·크기·해시는 latency_models.py와 JSON에 있다.

적용·복구 절차
--------------

현재 권장 조합은 기존 Qwen3-8B-Q4_K_M + BGE-M3-Q8_0, 4개 판정 배치, 검토된 표시다. 측정 계측과 명시적 실험 옵션만 추가했고 자동 기본 모델 전환은 하지 않았다. planning은 핵심 품질 보강 후 다시 검증할 우선 후보다.

별도 적용을 검토할 때는 앱을 정상 종료하고 SQLite backup API 등 일관된 방법으로 DB를 백업한다. 개인 DB 사본에서 새 프로필 색인을 따로 만들고 질문별 정확도·원문 인용·취소·시간 초과·재처리를 검증한 뒤 명시적으로 전환한다. Qwen은 qwen3-retrieval-v1, 질문 지시문, last pooling, L2 정규화가 필요하며 raw-v1 BGE 벡터와 섞지 않는다. 질문 지시문 변경도 프로필 버전을 변경해야 한다.

복구는 PMA_REQUEST_TOKEN_CACHE·PMA_SELECTION_BATCH_SIZE·PMA_CHAT_PRESENTATION의 실험 설정을 해제하고 원래 생성·임베딩 파일과 raw-v1으로 실행한다. 실제 재색인까지 했다면 모델 식별 키를 확인하고 보관한 일관된 DB 백업으로 복원한 후 원문·검색·근거를 확인한다. 이번 측정 종료 후에는 기존 앱을 원래 설정(-Evaluation -Test, 8765/8081/8082)으로 복구하고 화면·두 모델의 응답을 확인한다.

재현 명령과 선택 메타데이터 계약은 docs/response_latency.md를 참고한다. JSON 집계는 python -m evaluation.latency_publication <실험 루트> --verification evaluation/response_latency_verification.json --output evaluation/response_latency_results.json으로 재생성한다. 미완료 실행은 기본적으로 공개 집계에서 거부한다. 회귀 검사 기록이 없으면 전체 채택 조건을 통과로 표시하지 않는다.

회귀 검사
---------

전체 Python 358개 통과, 실패 0개(26.76초). 화면 검사 4종 통과: multilingual_ui.mjs, query_correction_ui.mjs, search_highlight.mjs, search_audit_browser.cjs. 혼합 사건 평가는 10/10개 정답 집합 일치, 평균 Recall@8 1.000, 잘못된 필터 질문 0개다. 혼합 사건 평가는 결정적 대체 모델을 사용하는 회귀 검사로, 실제 모델 정확도와 구분한다.

앱 복구 확인: 화면 8765 및 모델 8081·8082에서 모두 HTTP 200. 원래 모델 해시·문맥 한도·GPU 오프로딩을 확인했고 실험 포트 18181·18182는 종료했다.
