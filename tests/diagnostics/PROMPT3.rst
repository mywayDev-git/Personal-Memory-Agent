진단 설정 추가 보고서 — Prompt 3
==============================

2026-10-17 (Asia/Seoul)

브랜치와 변경 범위
-----------------

대화 시작 당시 버전을 보관한 codex/pre-search-diagnostics-20261017 브랜치의
cfc8f52 커밋에서 codex/search-diagnostics-v1 개발 브랜치를 만들었다.
앞서 작성한 진단 모듈과 테스트는 작업 폴더에 유지했다.
이번 단계에서는 pma/settings.py와 테스트·보고서만 수정했다.
개발 변경은 아직 커밋하지 않았으며 보관 브랜치의 커밋도 변경하지 않았다.

설정 동작
---------

* PMA_DIAGNOSTICS 기본값은 0이다. 문자열이 정확히 1일 때만 True이다.
* PMA_DIAGNOSTICS_PATH 기본값은 비어 있다. 미지정/빈 문자열은 None이다.
* 경로만 지정해서 진단이 켜지지 않는다.
* 경로는 문자열 그대로 보관한다. 설정 로딩 시 파일 접근·디렉터리 생성·경로
  정규화를 하지 않으며, 사용할 수 없는 경로 때문에 앱 시작을 거부하지 않는다.
  실제 저장 오류는 기존 SearchTrace에서 격리한다.
* 환경변수는 AppSettings.from_env 호출 시 읽는다. 이미 만든 설정은 불변이다.
* AppSettings() 직접 호출은 환경변수와 무관하게 기본 OFF이다.
* 새 필드는 keyword-only로 추가해 기존 위치 인자 생성자 순서를 보존한다.
* 모델·임베딩·프롬프트·검색·Top-K·답변 검증 설정은 그대로다.

Test-First 결과
---------------

추가 테스트 13개를 운영 코드보다 먼저 작성했다. 기존 설정 계약과 함께 실행했을 때
18 failed, 2 passed, 24 deselected였다. 실패는 설정 필드 미구현 때문이었다.
설정 구현 뒤 같은 선택 범위는 20 passed, 24 deselected로 바뀌었다.

검증 범위는 기본 OFF, 엄격한 0/1 파싱, 비정상 문자열, 경로 미지정,
디렉터리/부모 경로 없음/유효하지 않은 경로, 환경변수 로딩 시점,
불변 설정, 기존 생성자 및 모델 설정 보존이다.

전체 회귀: **369 passed, 31 failed, 1 warning, 18.45초**.
기존 288개 및 신규 동작 기준선 30개는 모두 통과했다.
남은 실패는 필터 12개, Store/HTTP 4개, 모델 6개, 서비스 통합 9개다.
실패를 skip/xfail로 처리하지 않았으며 전체 명령의 종료 코드는 1이다.
결과 XML은 .local/diagnostics-prompt3.xml 에 저장했다.
Ruff 검사 통과. 경고는 기존 Starlette/httpx 사용 중단 예정 안내다.

설정 필드가 생기면서 서비스 저장 실패 동일성 테스트 하나도 통과했지만,
서비스가 아직 새 진단 수집기를 사용하지 않으므로 실제 서비스 저장 실패를
주입해 검증한 결과로 해석하면 안 된다. 해당 통합 검증은 서비스 연결 후 다시 필요하다.

현재 가능한 것과 후속 작업
-------------------------

설정 로딩 및 공통 수집기에 직접 전달하는 경로는 검증했다.
애플리케이션의 질문 요청에 자동 trace를 붙이는 기능은 아직 연결하지 않았다.
환경변수를 켜는 것만으로 지금 바로 검색 JSONL이 생성되는 것은 아니다.
실제 서비스 ON/OFF 성능 차이는 계측 연결 후 측정한다.

다음 단계는 Prompt 4의 Store snapshot·관계 조회 계측이다.
추가 DB 조회 없이 이미 읽은 데이터만 관찰하고 기존 SQL과 반환값을 보존해야 한다.

재실행
------

저장소 루트에서 테스트 전용 basetemp 경로를 지정한다::

    .\.venv\Scripts\python.exe -B -m pytest -q tests/diagnostics/test_settings.py tests/diagnostics/test_trace_contract.py -k "settings or path or constructor or environment or literal" --basetemp=.local/pytest-prompt3-settings
    .\.venv\Scripts\python.exe -B -m pytest -q --basetemp=.local/pytest-prompt3-full --tb=line --junitxml=.local/diagnostics-prompt3.xml
