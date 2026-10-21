10초 목표의 직접 비교 방법
=========================

이 실험은 개인 기록 대신 합성 DB와 현재 설치된 Qwen/BGE를 사용합니다.
공식 메인 평가와 별개이며 모델 다운로드나 기본 모델 변경을 하지 않습니다.
모든 답변은 기존 독립 모델 검토와 원문·인용 검사를 거칩니다.

새 브랜치가 열린 프로젝트 폴더에서 PowerShell로 다음 명령을 실행하면 계획만 표시됩니다::

    pwsh -File scripts/run_latency_goal.ps1 -Placement both

실제로 실행하려면 ``-Execute``를 붙입니다. 현재 16GB 환경에서 일반 모델
서버와 함께 실행하면 메모리 경쟁이 생깁니다. 일반 서버 두 개를 잠시 종료하고
같은 설정으로 복구하는 실행은 다음과 같습니다. 다른 앱은 종료하지 않습니다::

    pwsh -File scripts/run_latency_goal.ps1 -Placement both -Samples 5 -PauseOrdinaryModels -Execute

작업 트리에서 별도의 Python 환경을 사용한다면 ``-PythonExe``에 기존 프로젝트의
``.venv/Scripts/python.exe`` 절대 경로를 지정합니다. CPU 실험은 이 PC에서 수십 분
걸릴 수 있습니다. ``-Samples 20``은 더 긴 반복 측정입니다. CPU와 GPU는 순차 실행합니다.
``-GenerationBatchThreads``는 입력 처리 스레드만, ``-Threads``는 모델 스레드 수를 지정합니다.
0인 입력 처리 스레드 옵션은 서버 기본값을 유지합니다.

이번 검토용 작업 트리에서 CPU 비교를 재현하는 명령은 다음과 같습니다::

    Set-Location C:\development\Personal-Memory-Agent\.local\latency-validated-drafts
    pwsh -File scripts/run_latency_goal.ps1 -Placement cpu -Samples 5 -Threads 8 -GenerationBatchThreads 24 -PythonExe C:\development\Personal-Memory-Agent\.venv\Scripts\python.exe -PauseOrdinaryModels -Execute

GPU 비교는 ``-Placement gpu -Samples 20 -GenerationBatchThreads 0``으로 바꿉니다.
이 명령의 기준 경로와 후보는 동일한 지정 스레드를 사용합니다. 앱에서 스레드를
지정하지 않았을 때의 기본값과는 구분합니다. 일반 모델 서버가 아예 실행 중이지
않다면 ``-PauseOrdinaryModels``를 제외합니다.

결과는 ``.local/latency-goal/<실행 이름>/comparison.rst``에서 볼 수 있습니다.
각 CPU/GPU 폴더의 ``results.json``에는 단계별 시간, 호출 수, RAM 작업 집합,
private commit, 시스템 여유 RAM, 장치 전체 VRAM이 기록됩니다. 합성 답변·근거·인용은
``quality/``에 분리되므로 성능 로그에 원문을 넣지 않습니다.

중단하려면 실행 중인 CPU/GPU 결과 폴더에 ``cancel.request``라는 빈 파일을 만듭니다.
현재 요청이 끝나면 다음 요청 전에 멈추고 실험 서버를 정리합니다. 일반 서버를 잠시
종료한 경우 저장한 명령으로 다시 시작합니다. 실행 창을 강제 종료하면 이 정리 절차가
완료되지 않을 수 있으므로 저장된 서버 명령과 복구 기록을 확인해야 합니다.

시간은 준비 실행 후 검증된 응답이 반환될 때까지입니다. 서버 로딩·색인·준비 실행은
제외하고, 각 요청 전에 실험 슬롯을 비웁니다. 운영 중 여러 요청에 걸친 캐시 적중 효과는
이 수치에 포함하지 않습니다. 실패나 검토 대기는 10초 목표 달성으로 세지 않습니다.
CPU는 GPU 장치·연산·KV 오프로딩을 모두 끕니다. GPU가 물리적으로 없는 PC에서의
검증은 별도입니다. 5회 표본의 최댓값은 앱 전체의 지연 보장이 아닙니다.

현재 후보는 호출 안에서 긴 근거 ID를 짧게 표현한 뒤 원래 ID와 스키마로 복구합니다.
추출형 답변안은 하나의 짧은 확정 선물 기록에만 적용하고 같은 독립 검토를 통과해야
합니다. 해당하지 않거나 검토가 거절되면 기존 답변 생성 경로를 유지합니다.
모든 질문에서의 품질 동등성을 이 좁은 속도 실험만으로 판단하지 않습니다.
제품 기본값은 비활성이고, 비교 도구의 후보 경로에서만 두 옵션을 명시적으로 켭니다.
이번 작업 트리에는 기존 C++ 검색어 확장을 배치했습니다. 호환 확장이 없는 환경은
동일한 Python 매칭 경로를 사용하며, 비교 결과 JSON에서 확장 파일 해시를 확인합니다.

제외한 메모리 후보의 재현
-------------------------

진단 도구의 ``-DisableCpuRepacking``은 CPU 실험 자식 서버에서만 가중치 재배치를
끕니다. 사용한 값은 ``model-server-environment.json``에 기록하고, 종료 시 원래
환경을 복구한 뒤 일반 서버를 다시 시작합니다. GPU와 외부 서버 설정은 바꾸지 않습니다.

이번 16GB 조건에서 이 옵션의 검색 5회는 약 16초였으나, 답변 준비 실행과 본 측정
첫 회는 재검색과 근거 선택이 늘어 모두 300초 제한으로 실패했습니다. 남은 반복은 중단했고 제품 실행기에는
적용하지 않았습니다. private commit 감소는 실제 RAM 상주량 절감과 다릅니다.
진단 옵션을 검색과 대화 전체의 권장 설정으로 해석하지 않습니다.
