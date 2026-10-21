첫 질문 GPU 10초·CPU 60초 실험
================================

작업 브랜치는 ``codex/first-response-cpu-gpu``, 시작점은 ``31a2493``입니다.
기본 프로젝트 폴더의 브랜치·앱 기본 모델·DB 스키마는 변경하지 않습니다.
통합 중간 판단은 ``PMA_INTERMEDIATE_PLANNING=1``일 때만 동작하는 시제품입니다.
``PMA_BOUNDED_EXPANSIONS=1``은 기존 검증 사전에 대응 가능한 단어가 전혀 없는
질문에서만 확장어 목록을 빈 배열로 제한합니다. 모든 검증 사전 항목이 계속 후보로
남도록 보수적으로 검사하며, 가능한 확장에는 기존 모델 판단·검증을 그대로 사용합니다.
최종 답변의 독립 검증과 원문·인용·주체·날짜·부정 검사는 그대로 실행됩니다.
현재 후보는 최종 품질 선별에서 탈락해 채택되지 않았습니다. 이 도구는 재현 실험용이며
목표 달성·적용 완료를 뜻하지 않습니다. 상세 결과는 ``docs/first_response_results.rst``에 있습니다.

사용자가 실행하고 확인하기
--------------------------

작업 폴더 PowerShell에서 실행합니다. 아래 첫 명령은 실행 계획만 출력하며
모델 구동·다운로드·평가를 수행하지 않습니다::

    & C:\development\Personal-Memory-Agent\.venv\Scripts\python.exe -m evaluation.first_response

기존 8B 모델에서 첫 질문·후속 질문을 비교하는 실행 계획::

    ./scripts/run_latency_goal.ps1 -Placement gpu -Samples 5 -IntermediatePlanning -BoundedExpansions -SourceDateDrafts -ColdInterpretations -FixtureSplit development -Cases @('dev_fact','dev_date','dev_pronoun','dev_compound') -PythonExe C:\development\Personal-Memory-Agent\.venv\Scripts\python.exe -PauseOrdinaryModels -RunName my-first-response

명시적으로 ``-Execute``를 붙이면 실제 합성 DB와 모델을 사용합니다.
``-PauseOrdinaryModels``는 알려진 8081·8082 서버만 잠시 종료하고,
실패·취소를 포함해 종료 시 원래 명령으로 복구합니다. 다른 앱은 종료하지 않습니다.
``-Placement cpu``는 GPU 계층·연산·KV 오프로딩을 모두 끕니다.
GPU가 물리적으로 없는 컴퓨터에서 검증한 것으로 해석하지 않습니다.

``-ColdInterpretations``는 각 요청 전 해석 캐시를 비웁니다.
이 옵션을 빼고 ``-InterpretationReuse``를 함께 지정하면 동일한 전체 입력의 반복을 비교합니다.
예를 들어 위 실행 계획에 ``-InterpretationReuse -IntermediatePlanning``을 사용하고
``-ColdInterpretations``를 생략합니다. 통합 해석 비교에서는 기준 경로에도 기존 해석 캐시를 켭니다.
질문 글자뿐 아니라 이전 대화·근거·날짜·모델·설정이 같아야 재사용됩니다.
실제 대화가 추가되거나 기록을 수정·삭제한 뒤 같은 질문을 하는 것은 동일 입력 반복과 다릅니다.
검색 확장 출력 제한을 별도로 비교하려면 ``-BoundedExpansions`` 유무를 바꿉니다.
``-SourceDateDrafts``는 명시적 날짜가 검증된 유일한 대상 사건의 원문을 답변 후보로 제안합니다.
같은 대상의 다른 언급·부정·미상 날짜가 있으면 기존 생성 경로를 사용합니다.
다른 배경 원문은 최종 독립 검증 입력에서 제거하지 않습니다.
``-BatchEight``은 모든 후보를 유지하면서 한 번에 판정할 묶음 크기만 8로 바꿉니다.
``-QualityScreen``은 속도 채택용 표본을 모으지 않는 1회 품질 선별입니다.
``-BaselineOnly``는 후보를 실행하지 않고 기존 8B 기준 경로만 측정합니다.
품질 선별에서 후보가 탈락한 경우에도 현재 CPU·GPU의 기준 시간을 확인할 수 있습니다.
이때 ``baseline.json``은 기준 측정값이며 최적화 전후 비교나 후보 채택 결과가 아닙니다.
``-DisableCpuRepacking``은 실패한 메모리 옵션의 재현용입니다. 이번 환경에서 두 번의
시간 초과가 발생했으므로 권장 설정으로 사용하지 않습니다.
``-RetrievalOnly``는 기존 90개 검색 사례만, ``-ReviewBank``는 정상·변조 답변 검사도 실행합니다.
``-ReviewOnly``는 고정 답변 묶음의 검증만 수행하며, 검색·답변 속도 채택 검사를 대신하지 않습니다.
후보 파일 선택은 ``-Generation q4`` 또는 ``-Generation q8``이며 BGE는 유지됩니다.
생성 서버의 이전 프롬프트 슬롯은 첫 질문과 반복 질문 실험 모두 비웁니다.
모델 최초 로딩·합성 자료 색인·준비 실행은 응답 시간에서 분리됩니다.
처리 중인 실험을 중단하려면 결과 폴더의 ``gpu`` 또는 ``cpu`` 아래에
``cancel.request``라는 빈 파일을 만듭니다. 다음 요청 경계에서 중단하고 서버를 복구합니다.
실행별 새 RunName을 사용해야 이전 측정이 보존됩니다.

결과는 ``.local/latency-goal/<RunName>`` 아래에 남습니다.
``launch-plan.json``에는 실제 실행 인자·실행기 해시·가중치 재배치 환경값을 기록합니다.
``results.json``에는 원문 없는 시간·호출·메모리 측정값이,
``quality`` 폴더에는 합성 답변과 인용 근거가 남습니다. 개인 DB는 사용하지 않습니다.
별도 보고서 생성은 모델을 구동하지 않습니다::

    & C:\development\Personal-Memory-Agent\.venv\Scripts\python.exe -m evaluation.first_response_report .local/latency-goal/my-first-response/gpu/results.json --output .local/latency-goal/my-first-response/review.json

``review.json``과 읽기 쉬운 ``review.rst``가 생성됩니다.
SCREEN_PASS는 해당 사례의 자동 선별 통과이며 전체 품질 통과·최종 채택이 아닙니다.
16개 품질 사례의 비교는 모델을 구동하지 않는 별도 도구로 확인합니다::

    & C:\development\Personal-Memory-Agent\.venv\Scripts\python.exe -m evaluation.first_response_quality .local/latency-goal/my-first-response/gpu/results.json --output .local/latency-goal/my-first-response/quality-review.json

자동 채점과 원문을 대조한 의미 검토를 구분합니다. 기준과 후보가 똑같이 실패했어도
정답으로 집계하지 않습니다. 명령문을 사실로 승인하는 오류는 채택을 막습니다.
실제 답변과 전체 원문을 함께 볼 수 있는 검토표도 모델 재실행 없이 만듭니다::

    & C:\development\Personal-Memory-Agent\.venv\Scripts\python.exe -m evaluation.first_response_review .local/latency-goal/my-first-response/gpu/results.json --output .local/latency-goal/my-first-response/answers.html

생성된 ``answers.html``을 브라우저에서 열면 사례별 답변과 자동 점수가 보입니다.
인용 구간·전체 원문·채점 조건은 펼쳐서 볼 수 있습니다. 외부 통신과 모델 실행 버튼은 없습니다.
새로운 개발용·최종 확인용 답변 비교 실행은 가속 환경별 폴더에 이 검토표를 자동 생성합니다.

비교 조건과 채택
---------------

* 첫 요청의 단순 사실·날짜 사례별 중앙값: GPU 10초, CPU 60초 이하.
* 복합·후속: 중앙값 20% 이상 개선, 최대 지연 악화 10% 이내.
* 동일 입력 반복: 악화 허용치는 기존 중앙값의 10% 또는 0.05초 중 큰 값.
* RAM·private commit·GPU의 장치 VRAM을 관측하고 메모리 증가 5% 이내인지 확인.
* 개발용 16개·최종 확인용 16개 질문은 ``evaluation/first_response_cases.py``에 고정.
  최종 확인은 다른 인물·날짜·사건의 별도 합성 원문 집합을 사용하고 개발 중 실행하지 않음.
  근거 정답은 사람이 작성한 합성 원문 기준이며 기존 모델의 승인을 정답으로 삼지 않음.
* 별도 ``evaluation/review_bank.py``는 주체·날짜·부정·계획/실행·이유·동명이인·원문 지시
  관련 정상/변조 답변 8쌍을 사용. 중요한 오답의 잘못된 승인 0건 필요.
* GPU 품질을 통과한 후보만 CPU 비교. 최종 GPU 성능 후보가 있을 때 20회 재확인.
* 공식 메인 평가는 이 도구와 별개이며 저장소의 명시 요청·실행 버튼 정책을 따름.

런타임 후보
-----------

제품 Python과 분리된 ``.local/first-response/runtime-env``를 사용합니다.
OpenVINO 후보는 고정된 OpenVINO/Qwen3-8B-int4-ov 커밋이며
``evaluation/runtime_candidates.py``에서 파일 선택·용량·해시를 확인합니다.
추가 사용량 20GiB, 남은 공간 8GiB 제한을 적용하며 대규모 변환·소스 빌드는 하지 않습니다.
기존 GGUF 다운로드와 런타임 환경까지 포함하려면 ``--budget-root .local``을 지정합니다.
양자화도 달라지므로 결과는 모델·런타임 조합의 효과입니다.
실행기는 시작 시와 요청 사이에 8GiB 여유 공간을 확인합니다. 서버 로딩의 RAM·private commit·VRAM과
응답 처리 중 메모리를 분리해 기록합니다. 표본 관측이므로 순간 피크를 전부 포착한다고 보장하지 않습니다.

ONNX 후보의 메타데이터와 작은 그래프부터 확인합니다. 해당 저장소에
``genai_config.json``이 없으면 현재 아티팩트로는 GenAI 파이프라인을 시작할 수 없습니다.
이 단계의 실패는 CPU·GPU 속도 측정이나 ONNX Runtime 자체의 미지원 판정이 아닙니다.

실제 측정 결과·탈락 사유·미완료 항목은 결과 보고서에서 구분합니다.
실험별 최종 정리 문서는 ``docs/first_response_results.rst``입니다.
검증 통과만으로 기본 브랜치 병합·앱 모델 교체를 하지 않습니다.
