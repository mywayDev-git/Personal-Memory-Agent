질문·문맥 해석 재사용
====================

선택 옵션 ``PMA_INTERPRETATION_REUSE=1``은 동일 해석 입력의 결과만 프로세스
메모리에서 재사용합니다. 기본값은 비활성입니다. 질문 해석과 문맥 해석만 대상이며,
검색 계획·근거 선택·답변 생성·독립 답변 검증은 대상이 아닙니다.

첫 질문이나 다른 질문은 모델을 그대로 호출합니다. 반복 요청도 입력이 달라지면
호출합니다. 질문 해석 키는 질문·기준 날짜·확장 여부·데이터 디렉터리·전체 설정·
모델 SHA-256을 포함합니다. 문맥 키는 여기에 대화·전체 근거 원문·기록 버전·
원래 질문·해석 정책·소유자 구분을 포함합니다. 수정·삭제 이후 검색은 항상 다시
수행하며 새로운 근거 목록으로 문맥 키를 계산합니다. 최종 저장 시 출처 확인도 유지합니다.

등록된 생성 모델 SHA-256(``PMA_GENERATION_REVISION``)이 없거나 temperature가
0이 아니면 재사용하지 않습니다. 모델을 교체하면 반드시 실제 해시를 갱신해야 합니다.
실패·취소·만료 요청 및 모호함 확인이 필요한 문맥 결과는 저장하지 않습니다.
캐시 적중도 취소와 시간 제한 검사를 통과해야 합니다.

최대 64개, JSON 결과 내용 총 512 KiB, 항목당 128 KiB, 유효 시간 30분입니다.
파이썬 관리 구조의 작은 추가 비용은 이 내용 용량에 포함하지 않습니다.
원문 입력은 해시 계산에만 사용하고 키에는 해시만 보관합니다. 해석 결과에는
질문 등 개인 내용이 들어갈 수 있으므로 디스크 저장이나 로그 출력을 하지 않습니다.
프로세스 종료 시 없어지며 만료 항목은 다음 캐시 접근 시 제거합니다.

사용자 재현
-----------

기존 실행기에서 ``-InterpretationReuse``를 추가하면 기존 ID 단축·원문 답변안을
양쪽에 동일 적용하고 해석 캐시만 후보에 추가합니다. 기본 실행은 계획만 출력합니다::

    Set-Location C:\development\Personal-Memory-Agent\.local\latency-validated-drafts
    pwsh -File scripts/run_latency_goal.ps1 -Placement gpu -Samples 5 -InterpretationReuse -PythonExe C:\development\Personal-Memory-Agent\.venv\Scripts\python.exe

실제 합성 측정은 ``-Execute``를 추가합니다. 이전에 승인한 일반 서버 일시 종료·
복구 방식은 ``-PauseOrdinaryModels``입니다. CPU는 ``-Threads 8``과
``-GenerationBatchThreads 24``를 지정합니다. 이 작업 트리에는 기존 프로젝트의
Python 환경을 지정합니다. CPU 실측 명령은 다음과 같습니다::

    pwsh -File scripts/run_latency_goal.ps1 -Placement cpu -Samples 5 -Threads 8 -GenerationBatchThreads 24 -InterpretationReuse -PythonExe C:\development\Personal-Memory-Agent\.venv\Scripts\python.exe -PauseOrdinaryModels -Execute

실행 결과는 ``.local/latency-goal/<실행 이름>/comparison.rst``와 같은 이름의
JSON 파일에서 확인합니다. 합성 답변과 원문 근거는 각 CPU/GPU 폴더의 ``quality/``에
분리해서 보관합니다. 보고서 열기나 기본 계획 출력은 실제 측정을 시작하지 않습니다.

한 번의 준비 실행 다음 동일 질문을 5회 반복합니다. 후보 준비 실행은 캐시 미적중,
본 반복은 재사용 가능 조건입니다. 이것은 첫 질문의 속도 향상을 의미하지 않습니다.
``-ColdInterpretations``를 추가하면 매 요청 전 캐시를 비워 첫 요청 조건을 비교합니다.
서버의 프롬프트 슬롯은 각 요청 전 비우지만 해석 캐시는 이 옵션이 없으면 유지합니다.
각 행의 프로필에는 question/context_interpretation_cache_hits 또는 misses가 기록됩니다.

DB 색인·모델 준비·브라우저 화면 표시 시간은 기존 응답 실험과 같이 제외합니다.
새 질문·새 날짜·바뀐 대화·다른 근거에서는 속도 이득을 보장하지 않습니다.
실험은 같은 DB와 초기 대화를 복제하므로 문맥이 같습니다. 실제 대화에 새 답변이
추가되면 대화 입력이 달라져 문맥 캐시는 미적중할 수 있습니다. 질문 해석은 동일한
질문·날짜·모델이면 계속 재사용 가능하지만 검색과 최종 검증은 다시 수행합니다.
