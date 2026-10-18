# Personal Memory Agent · 기억의 서랍

Windows PC에서 개인 기록을 저장하고, 로컬 AI가 추출한 기억을 검색해 근거와 함께 답하는 단일 사용자 앱입니다. 기존 추출 스키마 v4와 CLI를 함께 유지합니다.

## 평가 관제실

`pwsh -File ./run_app.ps1 -Evaluation`으로 실행하면 모델 서버와 웹 앱이 함께 시작되고
기존 화면에 **평가 관제실** 메뉴가 나타납니다. `python -m pma`는 모델 서버를 시작하지 않습니다.
평가 진행률·현재 처리 단계, 정확도·근거 지표, 질문별 실패 분석, 시나리오별 결과,
동일 조건 버전 비교를 확인할 수 있습니다. 기본값은 비활성화이며 평가 DB는 개인 기억 DB와 분리됩니다.
질문·답변 원문과 상세 진단은 `PMA_EVALUATION_DETAILS=1`을 별도로 설정해야 조회됩니다.
실행·결과 가져오기·데이터셋 형식과 지원 범위는 [평가 관제실 사용법](evaluation/dashboard_README.rst)을 참고하세요.

## 빠른 시작

PowerShell 7, Python 3.14, uv가 필요합니다. 최초 의존성/모델 준비에만 인터넷을 사용합니다.

```powershell
uv sync --frozen --python 3.14
./run_app.ps1
```

실행 직후 시작 메시지와 모델 파일 검사 단계가 표시됩니다. 모델을 로딩하는 동안 10초마다 대기 시간이 표시되며, 각 모델의 준비 제한 시간은 5분입니다. 웹 앱이 준비되면 터미널에 일회용 접속 주소가 표시됩니다. 브라우저가 자동으로 열리지 않으면 이 주소를 직접 여세요. Windows PowerShell 5에서 실행했다면 PowerShell 7에서 `pwsh -File ./run_app.ps1`로 실행하세요.

기본 모델 경로:

- 생성 서버: `C:\llama.cpp\llama-server.exe`
- 생성 모델: `C:\models\Qwen3-8B-Q4_K_M.gguf`
- 검색 모델: `C:\models\bge-m3-Q8_0.gguf`

실행기는 127.0.0.1:8081(Qwen), :8082(BGE-M3), :8765(웹 앱)를 사용합니다. 준비되면 브라우저가 열립니다. 실행한 PowerShell에서 Ctrl+C로 종료하면 실행기가 시작한 모델 프로세스도 정리합니다. 모델 경로는 `-Server`, `-GenerationModel`, `-EmbeddingModel`로 지정할 수 있습니다. 이미 호환 모델 서버가 실행 중이면 `-ExternalServers`를 사용하세요. `-NoBrowser`는 일회용 접속 주소를 터미널에 표시합니다. 이 주소는 공유하지 마세요.

BGE-M3 파일은 [GPUStack GGUF 저장소](https://huggingface.co/gpustack/bge-m3-GGUF/tree/2d48f1737679ad900d5c26c5aad5410e9c70fdca)에서 받습니다. 원본 모델은 [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)입니다.

- 파일: `bge-m3-Q8_0.gguf` (634,553,760 bytes)
- 저장소 revision: `2d48f1737679ad900d5c26c5aad5410e9c70fdca`
- SHA-256: `950f4a8e5e19477a6d3c26d2f162233c20002c601f75e4b002e3239997821167`

실행기는 임베딩 파일 SHA-256을 계산해 색인 버전을 구분합니다. 임베딩 모델 변경 시 기존 검색 데이터를 무효화하고 원문에서 다시 추출합니다. `-ExternalServers` 사용 시 실제 서버에 로드된 모델과 지정 파일이 같은지 직접 확인해야 합니다.

## 포트 한 번에 종료

```powershell
./stop_app.ps1
```

앱 포트 8765·8766과 모델 서버 포트 8081·8082를 사용하는 프로세스를 강제 종료합니다.
처리 중인 작업도 중단되므로 평소에는 실행 창의 Ctrl+C를 사용하고, 남아 있는 서버 정리에 사용하세요.
해당 포트를 다른 프로그램이 사용 중이어도 종료 대상입니다.
`./stop_app.ps1 -WhatIf`로 대상을 미리 확인하거나,
`./stop_app.ps1 -Ports 8765,8766`으로 지정한 포트만 종료할 수 있습니다.

## 메인 실행 창에서 처리 과정 보기

```powershell
./run_app.ps1 -Test
# 가상 기록 전용 DB에서 연습할 때
./run_app.ps1 -LifeTest -Test
# 이미 모델 서버를 실행한 경우
./.venv/Scripts/python.exe -m pma --test
```

브라우저에서 평소처럼 기록을 저장하거나 검색하면 실행한 PowerShell 창에 한국어로
원문 저장, 기억 추출·검증, 검색 벡터 저장, 날짜 조건, 후보 수, 실제 검색 키워드,
선택된 기억과 원문, 최종 답변을 표시합니다. JSON을 열 필요가 없습니다.
`-Test`는 자동 평가가 아니라 실제 작업 과정을 보는 옵션이며 일반 실행과 같은 DB를 사용합니다.
기록·질문·답변이 콘솔에 노출되므로 화면 공유에 유의하세요. 별도 로그 파일이나 질문 이력을
저장하지 않습니다. 긴 원문은 일부만 표시하며 전체 내용은 앱에서 확인합니다.
옵션 없이 실행하면 기존처럼 상세 내용을 표시하지 않습니다.
AI가 검색·답변에 사용 중일 때 백그라운드 작업은 오류 없이 다음 주기에 재시도합니다.
실제 실패는 `-Test` 창에 실패 단계, 원인, 해결 방법, 오류 코드·종류를 표시합니다.
예외 메시지나 모델 오류 응답 원문은 출력하지 않으며, 알 수 없는 오류는 원인 미확정으로 안내합니다.

## 사용 흐름

### 검색 연습용 데이터

`data/demo_records.json`에는 `[테스트 데이터 DEMO-01]`부터 `DEMO-08`까지 표시된 가상 기록 8개가 있습니다. 모두 2026년 10월 기록이며 실제 사용자 경험이 아닙니다. 등록된 예시로 다음 질문을 검색해 볼 수 있습니다.

- 캡스톤 프로젝트에서 내가 맡기로 한 역할은?
- 작업하기 좋았던 성수동 카페는 어디였지?
- 지연이 생일 선물로 받고 싶다고 한 것은?
- 부산 여행 숙소와 체크인 날짜는?
- 무선 키보드를 얼마에 샀고 왜 선택했지?
- 파스타를 다음에 만들 때 무엇을 바꾸기로 했지?

다시 등록하려면 앱을 종료하고 호환 모델 서버를 실행한 뒤, `PMA_EMBEDDING_REVISION`을 실제 모델 파일 SHA-256으로 설정하고 `./.venv/Scripts/python.exe -B -m scripts.seed_demo`를 실행합니다. 동일한 활성 기록은 중복 등록하지 않습니다. 등록 후 일반 추출·임베딩 파이프라인으로 색인을 생성하고 예시 질문을 검증합니다. 테스트 기록은 앱에서 각각 삭제할 수 있습니다.

### 기록 저장과 검색

1. 기록과 기준 시각을 입력하면 원문을 먼저 저장합니다.
2. 백그라운드 작업이 Qwen으로 기억을 추출하고 스키마·원문 인용을 검증합니다. BGE-M3 임베딩까지 성공한 기록만 검색 가능합니다.
3. 질문의 시간 조건을 해석하고 벡터·키워드 검색 결과를 결합합니다. Qwen이 찾은 기억으로 답하며 각 답변에서 원문을 열 수 있습니다.
4. 수정·이전 버전 복귀 시 새 버전을 만들고 다시 처리합니다. 처리 실패 시 원문은 남으며 재시도할 수 있습니다.
5. 삭제한 기록은 즉시 검색에서 제외합니다. 휴지통에서 30일간 복원할 수 있고, 만료 시 앱 시작 또는 실행 중 정리 작업에서 영구 삭제합니다.

기존 단일 질문·답변 이력은 저장하지 않습니다. 별도 AI 대화 탭은 이력과 답변별 근거를 로컬 DB에 저장합니다. 전체 횟수·최초/최후·순위 집계는 지원하지 않습니다. 기간 필터가 있으면 시점이 불명확한 기억을 제외합니다. 기록당 4,000자, 질문당 1,000자로 제한하며 모델 문맥 길이도 검사합니다. 계획을 실행 결과로 오해하는 등 의미 오류는 여전히 가능하므로 근거를 확인하세요.

## 구성과 데이터

| 경로 | 역할 |
|---|---|
| `pma/web.py`, `pma/static/` | 로컬 API, 세션/CSRF, 한국어 웹 UI |
| `pma/service.py` | 작업 실행, 검색·답변, 동시 모델 사용 제한 |
| `pma/store.py`, `pma/lock.py` | SQLite 트랜잭션·버전·휴지통·단일 실행 잠금 |
| `pma/models.py` | 로컬 생성·임베딩·질문 분석 |
| `scripts/memory_agent/` | CLI·앱·평가가 공유하는 추출/검증 파이프라인 |
| `schema/`, `prompts/` | 기존 v4 스키마와 추출 지침 |
| `evaluation/`, `tests/` | 평가, 기존 결과 감사, 회귀·통합 검증 |

DB 기본 위치는 `%LOCALAPPDATA%\PersonalMemoryAgent\memory.db`입니다. records, revisions, jobs, memories, evidence, embeddings와 파생 facts, memory_links, dismissed_links 테이블을 사용합니다. SQLite user_version은 2이며 기존 DB는 다음 앱 시작 시 원문과 이력을 유지하면서 확장합니다. 저장된 기억의 파생 사실은 50개씩 재구축하며, 완료 전에는 구축 중 상태와 불완전한 검색 범위를 표시합니다. 수정 이력은 기록 영구 삭제 때 함께 삭제됩니다. DB는 암호화되지 않으며 Windows 사용자 계정/디스크 보호가 필요합니다. 백업은 앱을 정상 종료한 후 데이터 디렉터리를 복사하세요. 영구 삭제는 앱 DB에서 제거하지만 OS 백업·SSD 잔존 데이터까지 지우는 기능은 아닙니다.

모델 통신은 loopback HTTP만 허용하고 프록시·리다이렉트를 사용하지 않습니다. 앱은 Host/Origin, 일회용 로그인, HttpOnly SameSite 쿠키, CSRF, CSP를 검사합니다. 원문·질문·답변·모델 오류 본문을 서버 로그에 출력하지 않습니다. 같은 Windows 계정의 악성 프로그램으로부터 보호하는 보안 경계는 아닙니다.

## API

인증 후 `/api/v1` 아래 API를 호출합니다. 변경 요청은 동일 Origin과 X-CSRF-Token이 필요합니다.

- `POST /session`: 일회용 로그인 / `GET /session`: 세션 확인
- `GET, POST /records`: 목록·등록
- `GET, PATCH, DELETE /records/{id}`: 조회·버전 지정 수정·휴지통 이동
- `GET /records/{id}/revisions`, `POST /records/{id}/revert`
- `POST /records/{id}/retry`, `POST /records/{id}/restore`
- `DELETE /records/{id}/purge`: 영구 삭제
- `GET /jobs/{id}`, `GET /health`
- `POST /search`, `POST /answers`: question, 선택적 filters(date_from/date_to), today

등록은 202와 record_id/job_id를 반환합니다. 수정·되돌리기는 expected_version으로 충돌을 검사합니다. 오류는 error.code/message/retryable와 request_id를 포함합니다. 답변의 items[].citations는 results[].id를 참조합니다. 답변 생성 중 원문이 바뀌면 SOURCE_CHANGED로 결과를 거부합니다.

## 검증

Kiwi + LLM의 독립 비교 평가 도구는 [실험 실행 안내](evaluation/KIWI_EXPERIMENT.md)를 참고하세요.
`evaluation` 의존성 그룹으로 Kiwi 0.24.0을 선택 설치하며, 기본 앱 의존성에는 포함하지 않습니다.
합성 개발 24개·평가 72개, A~H 조합과 현재 앱 L, 별도 임시 DB, 재개 검사와 CSV/HTML 보고서를 제공합니다.
자동 근거/별칭 검사는 의미 정확도와 구분하며 검토 전 의미 정확도는 미평가로 남깁니다.

```powershell
./.venv/Scripts/python.exe -B -m pytest -q
./.venv/Scripts/ruff.exe check pma scripts config evaluation tests
./.venv/Scripts/python.exe -B -m evaluation.audit
./.venv/Scripts/python.exe -B -m scripts.main --help
```

자동 테스트는 임시 DB와 가짜 모델로 트랜잭션, 재시작 복구, 버전 충돌, 삭제 전파, 인용 ID, 인증·CSRF, 오류 비공개, 벡터 검증을 검사합니다. 구조/근거 검증 통과는 의미 정확도 100%를 뜻하지 않습니다. 기존 평가 결과에 대해 별도 기대 조건과 사람 검토가 필요하며 dev/test 중복은 일반화 평가를 제한합니다.

실제 모델 검증은 두 서버를 실행하고 PMA_EMBEDDING_REVISION에 실제 BGE 파일 SHA-256을 설정한 뒤 다음을 실행합니다. 가상 기록만 임시 DB에 저장합니다.

```powershell
./.venv/Scripts/python.exe -B -m evaluation.live_smoke
./.venv/Scripts/python.exe -B -m evaluation.answer_smoke
```

`answer_smoke`는 가상 근거만 사용해 실제 생성 모델의 답변을 검사합니다. 본인/다른 사람의 역할과 인용 ID, 정보가 없는 질문 거절, 계획을 완료로 오해하지 않는지, 원문 속 답변 조작 명령을 무시하는지 확인합니다. 답변 지침은 원문을 사실 근거로 사용하면서 원문 속 명령은 무시하도록 구분하며, 역할을 맡기로 한 결정만으로도 결정 내용을 묻는 질문에는 답하도록 합니다.

## 설정 및 범위

### 검색·답변 진단 데이터

`data/search_diagnostics.json`에는 가상 기록 12개와 질문/기대 행동 24개가 있습니다.
동의어(싸우다/다투다), 상대 날짜, 거리의 정확한 값과 비교 조건, m/km 환산,
타인의 행동, 미래 계획, 부정, 장소별 활동, 없는 정보, 집계를 구분해 평가합니다.
개인 DB에 넣지 않고 임시 DB에서 실제 추출·임베딩·질문 분석·답변을 실행합니다.

```powershell
# 호환 로컬 모델 서버와 PMA_EMBEDDING_REVISION 설정 후 실행
./.venv/Scripts/python.exe -B -m evaluation.search_diagnostics
```

`output/search_diagnostics.json`에 추출된 기억, 질문 해석/날짜 조건, 검색된 원문 ID,
모델 답변과 인용을 단계별로 저장합니다. 검색 후보에 정답 원문이 포함되었다는 것과
최종 답변이 정확하다는 것은 별개입니다. expected와 답변을 직접 대조해야 하며,
이 스크립트는 의미 정확도를 자동으로 합격 처리하지 않습니다.

`PMA_DATA_DIR`, `PMA_PORT`, `PMA_ENDPOINT`, `PMA_MODEL`, `PMA_TIMEOUT`, `PMA_MAX_TOKENS`, `PMA_CONTEXT_TOKENS`, `PMA_EMBEDDING_ENDPOINT`, `PMA_EMBEDDING_MODEL`, `PMA_EMBEDDING_REVISION`, `PMA_EMBEDDING_DIMENSIONS`를 지원합니다. 생성 서버 문맥은 16,384 토큰, 임베딩은 8,192 토큰·CLS pooling·1,024차원으로 실행합니다. 서버 직접 실행 시 앱 설정과 맞추세요.

앱은 단일 프로세스·단일 사용자입니다. 명시적 사실과 추론 관계를 구분합니다. 대규모 범용 지식 그래프, 통계 집계, 계정/동기화, 자동 백업은 포함하지 않습니다. 1,000개 기록/20,000개 기억은 설계 목표이며 실제 PC의 모델 지연과 메모리 사용을 별도로 측정해야 합니다. 사용자 원문 처리에는 인터넷 서비스가 필요하지 않습니다.


## 관계·시간 검색

- 반복되는 동일 문장도 저장된 인용 위치로 구분하여 각 날짜 제목에 연결합니다. 파생 사실 버전 5는 기존 원문을 보존하고 근거 위치와 관계 규칙을 다시 적용합니다.
- `작년 10월 3일`, `2024년 2월`, `어제부터 오늘까지`처럼 구체적인 날짜와 기간을 우선 해석합니다. 희망과 실제 선물의 연결·비교에는 완료 행동만 사용하며 계획·부정·불확실한 행동은 제외합니다.

- 기존 추출 v4 결과와 별도로 주체·수신자·발화자·관계·대상 속성·상태·사건 시각을 파생 색인에 저장합니다. 추출기가 기준 시각을 사건 시각으로 잘못 복사하면, 원문에 시간 표현이 없는 경우 파생 색인에서 제거합니다.
- 알려진 한국어 관계 표현은 코드로 정규화합니다. 희망/선물/수신/선호/달리기/방문/식사/다툼/취소를 구분하며, 미인식 표현은 로컬 모델의 후보 선별과 답변 검증 경로를 사용합니다. 모든 자연어 표현을 해석하는 완전한 의미 체계는 아닙니다.
- 거리의 m/km 환산과 정확한 값·이상·초과·이하·미만은 코드로 검사합니다. 날짜 조건은 질문의 명시적인 날짜 표현에서만 적용합니다. 지원하는 날짜 표현은 직접 입력한 날짜 범위, ISO 날짜, 월/일, 오늘·어제·그제·내일, 이번달·지난달·올해·작년입니다. 복잡한 기간은 화면에서 직접 지정하세요.
- 구조화 조건이 명확한 질문은 검증된 기억을 인용하는 답변을 구성합니다. 일반 질문은 모델이 후보를 선별하고 답변을 만든 후 별도 근거 검증을 통과해야 합니다. 숫자·색상 생성 오류는 추가로 코드에서 검사합니다. 모델 검증도 오류 가능성이 있으므로 일반 질문의 의미 정확도를 보장하지 않습니다.
- 희망↔실제 행동, 계획↔실행, 선호 변화, 같은 시점의 긍정↔부정 진술을 관계 후보로 연결합니다. 각 사실의 주체·대상·속성·시각을 대조하며 새 기록이 과거 사실을 덮어쓰지 않습니다. 관계 탐색은 같은 대상/인물 후보 중 사건 시각 기준 최대 100개로 제한합니다. 모든 기억 간 관계를 완전 탐색하지 않습니다.
- 기억 간 연결은 보수적으로 `inferred`로 표시합니다. 같은 이름은 실제 동일 인물이라는 보장이 없어 동명이인 가능성을 표시합니다. 현재 선호 질문은 최신 사건 기록과 과거 기록을 구분해서 보여주고 현재 상태를 무조건 확정하지 않습니다.
- 원문 상세와 답변 아래에서 추정 연결의 양쪽 원문을 확인하고 **이 연결 해제**를 누를 수 있습니다. 해제한 연결은 같은 원문 버전·근거로 재구축되지 않습니다. 수정/삭제는 파생 사실과 연결을 즉시 무효화합니다. 영구 삭제는 해당 연결 해제 이력도 제거합니다.
- `GET /api/v1/relations?record_id=...`, `DELETE /api/v1/relations/{id}`를 추가했습니다. 답변에는 `query_plan`, `facts_pending`, `connections`, 항목별 `claim_kind`와 `relation_ids`가 추가됩니다. 기존 `status/items/results/filters`는 유지합니다.

회귀 데이터 `data/relationship_diagnostics.json`은 18개 가상 기록과 60개 질문, 기록 추가 전후/순서 변경 시나리오를 포함합니다. 평가기는 개인 DB를 열지 않습니다.

```powershell
./.venv/Scripts/python.exe -B -m evaluation.search_diagnostics --dataset data/relationship_diagnostics.json --output output/relationship_diagnostics.json
./.venv/Scripts/python.exe -B -m evaluation.relationship_checks --report output/relationship_diagnostics.json --output output/relationship_review.json
```

`--cached-extractions`는 동일 원문임을 확인한 가상 추출 결과만 재사용합니다. 실제 추출을 새로 평가할 때는 이 옵션을 생략하세요. 지정된 기대 조건 통과와 일반적인 의미 정확도는 다릅니다. 실행 결과의 질문 해석, 검색 원문, 답변, 인용, 추론 연결을 함께 검토해야 합니다.

## 누적 생활 기록 평가

`data/life_diagnostics.json`은 2026년 4~9월의 **가상 기록 300개 / 신규 질문 600개**입니다.
기존 관계 평가 60문항을 대체하지 않습니다. 12명, 8개 생활 영역, 40개 사건에 연결된
200개 기록과 일상·혼동 기록 100개를 포함합니다. 질문은 직접 회상, 구어체, 간접 단서,
기록 연결, 조건, 모호함의 6개 유형별 100개입니다. 영역별 틀에서 생성한 합성 데이터로,
실제 사용자 분포나 완전히 독립적인 600개 사건을 뜻하지 않습니다.

사건 30개는 개발용, 10개는 별도 평가용입니다. 같은 사건의 표현 변형은 같은 그룹에
남습니다. 두 그룹이 생활 영역·표현 틀까지 완전히 분리된 것은 아닙니다.
평가 결과를 보고 제품을 고칠 때 별도 평가군은 조정에 사용하지 마세요.

```powershell
# 가상 데이터 재생성(모델 호출 없음). 기대 근거는 모델 답변을 보기 전에 정의합니다.
./.venv/Scripts/python.exe -B -m evaluation.build_life_dataset
# 모델 서버만 시작하고 앱/개인 DB를 열지 않습니다. 끝나면 시작한 서버만 종료합니다.
pwsh -File scripts/run_life_evaluation.ps1 -RunDirectory output/life-baseline
# 동일 코드·데이터·설정에서는 같은 명령으로 중간 결과부터 재개합니다.
# 코드나 데이터가 바뀌면 새 RunDirectory를 사용하세요.
# 호환 모델 서버가 이미 실행 중이면 -ExternalServers를 추가하세요.
```

기록 30/100개에서는 지정된 60질문씩, 300개에서는 전체 600질문, 역순 입력에서는
동일한 60질문을 실행하여 총 **780회**를 기록합니다. 사건별 수정·휴지통·영구 삭제와
관계 해제도 별도 실행합니다. 과거 스냅샷에서는 아직 들어오지 않은 기록을 정답 근거로
요구하지 않습니다. 추출 실패는 숨기거나 정답으로 대체하지 않고 이후 질문에 표시합니다.
추출과 임베딩을 한 번 실행한 뒤 같은 결과를 재생하여 검색 결과를 비교합니다.
재생 DB의 UUID도 새로 생성되므로 차이를 입력 순서만의 인과 효과로 단정하지 않습니다.
역순에서 추출 모델 자체의 변동까지 다시 측정하는 검사는 아닙니다.

실행 폴더에는 입력·질문 데이터의 고정 사본(`dataset.json`), 원문/코드 해시(`manifest.json`), 추출 결과·벡터(`extractions.json`),
질문·기대 사실·답변·인용·선택 후보·지연(`questions.json`), 미실행을 포함한 집계
(`summary.json`), 수정/삭제 검사(`lifecycle.json`)가 저장됩니다. 후보 선별을 호출하지
않는 구조화 검색 경로는 최종 검색 결과를 남기며 선별 이전 후보 목록은 null입니다.
앱의 사용자 질문을 자동 저장하는 기능은 추가하지 않습니다.

```powershell
# 실행 도중에도 읽기 가능한 HTML 보고서를 만들 수 있습니다.
./.venv/Scripts/python.exe -B -m evaluation.life_report --run-dir output/life-baseline
```

`report.html`에서 질문을 검색해 기대 근거와 실제 답변을 비교합니다. 자동 판정은
근거 포함 여부·인용 유효성 등의 **진단 신호**이며 의미 정확도가 아닙니다. 답변이
정답 원문을 인용해도 주체·관계·상태·수량을 틀릴 수 있습니다. 지원 사실의 전체 문장을
정답 문구로 강요하지 않고 질문에 해당하는 속성만 대조합니다. `needs_conversation_context`
질문은 단서 부족을 인정하거나 확인하는 것이 기대 동작이며 대화 이력을 생성해 넣지 않습니다.

의미 검토는 실행 폴더의 `semantic_reviews.json` 배열에 `run_id`,
`verdict`(correct/incorrect/unclear), `reviewer`, `rationale`,
`failure_stage`(extraction/query_interpretation/retrieval/relationship/answer/unconfirmed)를
작성한 뒤 보고서를 재생성합니다. 실패 원인이 불명확하면 unconfirmed로 둡니다.
자동 검사와 검토자의 판단을 분리하며 미실행·검토 대기를 통과로 계산하지 않습니다.

예비 실행에서 발견한 오류와 다음 개선 지점은 `data/life_evaluation_notes.json`에 남깁니다.
이 파일의 관찰은 전체 780회 평가의 최종 정확도가 아닙니다. 실제 실행별 판정과 시점은
해당 실행 폴더를 확인하세요. 평가 폴더는 개인 DB와 분리되어 있으며 재실행을 위한
벡터·중간 결과가 포함되므로 크기가 커질 수 있습니다.

### 가상 생활 기록 웹 테스트

기존 로컬 모델 서버(8081·8082)가 실행 중일 때:

```powershell
./.venv/Scripts/python.exe -X utf8 -B -m scripts.run_life_web
```

브라우저가 일회용 인증으로 열리며 주소는 `http://127.0.0.1:8766`입니다.
개인 DB 대신 `.local/life-web/memory.db`에 기록 300개를 저장합니다.
`생활 기록 테스트`에서 기록과 질문 600개를 검색·분류하고, 질문을 답변 화면에 불러올 수 있습니다.
기대 결과는 펼쳐서 확인하며 AI 입력에는 전달하지 않습니다. 질문 기준일은 데이터셋의 2026-10-13입니다.
`output/life-evaluation-20261013`의 동일 데이터셋 추출 캐시를 재사용하고 나머지는 백그라운드에서 처리합니다.
처리 실패 기록은 원문을 열어 확인하고 `나의 기록`에서 재시도할 수 있습니다.
수정·삭제한 테스트 기록은 서버 재시작 시 덮어쓰거나 재생성하지 않습니다.
평가와 웹이 같은 모델을 사용하면 대기 시간이 늘어날 수 있고, 모델 서버가 종료되면 AI 기능은 연결 복구가 필요합니다.
이 화면의 수동 질문·답변은 저장되지 않습니다. 재현 가능한 평가 로그는 기존 평가 도구로 생성합니다.

가상 테스트를 AI 서버와 함께 시작하려면 `pwsh -File ./run_app.ps1 -LifeTest`를 실행하세요. 실행기가 자동으로 여는 인증된 브라우저 탭을 사용하세요. 다른 브라우저에서 일반 주소만 열면 인증되지 않습니다.

### 실패 목록과 재처리

웹의 `처리 실패 목록` 또는 연결 상태 아래 `실패 목록·재처리`에서 현재 실패한 기록을 모아 볼 수 있습니다.
원인별 건수·설명·오류 코드·원문을 표시하고, 원인 필터를 적용한 항목 전체 또는 개별 기록을 재처리 대기열에 추가합니다.
재처리는 성공을 보장하지 않으며, 이미 수정·삭제되었거나 다른 작업으로 전환된 항목은 건너뜁니다.
기존 `EXTRACTION_INVALID`는 여러 예외를 묶은 코드이므로 상세 원인을 단정하지 않습니다.

### 처리 신뢰성 개선

새 작업은 원문 문장 ID로 근거를 선택하고 Python이 인용문을 복원합니다. 모델이 인용문을 다시 쓰지 않습니다.
날짜는 인용된 문장·명시적 날짜 제목 범위에서 정규화합니다. 상대 날짜는 한국 시간 기준으로 계산하고 시각은 만들어 넣지 않습니다.
요일만으로 특정 주를 결정하거나 다음 문장에 날짜를 무조건 상속하지 않습니다. 미확정 시간은 일반 검색에는 남지만 날짜 조건의 확정 근거로 쓰지 않습니다.
긴 원문은 최대 6문장·본문 약 600토큰 단위로 처리하고, 출력 잘림은 해당 구간만 최대 4단계 재분할합니다.
성공 구간은 SQLite `extraction_chunks`에 임시 저장하며 전체 완료 후에만 기억·벡터·관계를 게시합니다. 수정·삭제 시 임시 결과는 무효화됩니다.
실패 목록의 `진단 정보·재처리 이력`에서 실패 단계, 오류 코드, 필드 검증 규칙과 출력 잘림 토큰 정보를 확인할 수 있습니다.
`지연에게`와 `지연이`의 역할 조건을 구분하고, 기준 시점 없는 `당시/그때` 질문은 날짜·사건을 요청합니다.
`evaluation.reliability_audit`는 기존 실패와 긴 일기를 별도 DB에서 실제 모델로 검증합니다. 처리 성공과 의미 검토는 별개입니다.
필드 타입 등 스키마 오류는 원문과 검증 경로를 전달해 1회만 재추출합니다. 재실패하면 실패로 남기며, 성공해도 최초 진단을 보존합니다.
날짜 정규화는 현재 문장·날짜 제목·일부 앞 문장 지시어를 지원하는 보수적인 규칙입니다. 모든 한국어 절의 시간 범위나 명시된 시각을 완전히 해석하는 기능은 아니며, 확정할 수 없는 시간은 비워 둡니다.
평가 재개 시 고정된 `sources.json`과 성공 구간을 재사용합니다. 실행별 코드 해시와 모델 설정은 `manifest-*.json`에 남기며, 의미 검토가 끝나지 않은 결과는 `pending`으로 구분합니다.

### 질문·후처리 회귀 평가

`evaluation.downstream_regression`은 개인 DB를 열지 않고 합성 임시 DB에서 실행한다. Kiwi 설치는 필요 없다.
기존 `output/kiwi-focused-v1`의 36개 사례·추출 결과가 필요하며, 로컬 생성·임베딩 서버를 사용한다.

```powershell
./.venv/Scripts/python.exe -X utf8 -m evaluation.downstream_regression --output output/downstream-new-frozen
./.venv/Scripts/python.exe -X utf8 -m evaluation.downstream_regression --mode live --output output/downstream-new-live
./.venv/Scripts/python.exe -X utf8 -m evaluation.downstream_regression --mode diagnostic --output output/downstream-new-diagnostic
./.venv/Scripts/python.exe -X utf8 -m evaluation.downstream_regression --mode live --case-file data/downstream_distractors.json --output output/downstream-new-distractors
```

기본 모드는 추출 기억과 근거 위치를 고정하고 질문 이해·검색·답변을 다시 실행한다. `live`는 추출도 새로 실행한다.
`diagnostic`은 대표 12개에서 선택된 기억, 전체 기억과 근거, 전체 원문을 동일한 답변 프롬프트로 비교한다.
질문 기준 날짜는 실험 정의의 2026-10-13으로 고정한다. 정답은 모델 입력에 포함하지 않는다.
입력·모델·코드·설정 해시가 일치하는 완료 결과만 재사용하며, 변경 후에는 새로운 출력 경로를 사용한다.
출력의 `executed_source`에는 실행 소스, 사례별 JSON에는 단계별 진단과 서버 호출·토큰이 저장된다.
`evaluation.downstream_report`는 명시적인 `review.json` 판정으로 CSV·HTML을 생성한다. 판정이 없으면 검토 대기로 남긴다.
답변 생성 수를 정확도로 계산하지 않으며 `correction-2`는 모순 판정에서 제외한다.

검색용 사실 버전은 6이다. 작업자의 기존 `rebuild_facts()` 경로에서 구버전 파생 사실만 배치 갱신한다.
최초 갱신 전에 DB 옆에 `<DB파일명>.before-facts-v6.bak`를 SQLite 백업 API로 생성한다.
원문·추출 payload·근거 위치·임베딩은 재작성하지 않고, 추출·임베딩 모델 호출도 하지 않는다.
백업 실패 시 갱신을 진행하지 않는다. 백업은 원문을 포함하므로 기존 DB와 같은 접근 권한 및 보존 정책으로 관리해야 한다.
이 변경을 검증하는 실험은 개인 DB를 갱신하지 않는다. 기본 UI에는 새 진단을 표시하지 않는다.
개발용 진단은 `Service(..., diagnostic_sink=events.append)`로 켜며, 원문·질문을 포함할 수 있으므로 명시적으로 켠 경우에만 수집한다.

## 답변·검증 비교 실험

**실험 결과 채택 보류이며, 기본 앱은 기존 답변 경로를 유지합니다.** `PMA_ANSWER_VALIDATION=1`을 설정하면 실험 후보를 켤 수 있습니다. 후보에서는 현재 상태 질문을 원문 기반 답변·검증 경로로 전달합니다. 답변 검증은 항목별 근거 일치와 질문 충족 여부를 구분하며, 의미상의 실패에는 동일 근거로 수정 생성 1회와 재검증 1회만 허용합니다. 검증 형식 오류·시간 초과에는 수정 루프를 실행하지 않습니다. 추출·저장·검색 후보 선택과 외부 응답 형식은 유지합니다.

평가 실행기는 후보 옵션을 명시적으로 켭니다. 로컬 Qwen/BGE 서버가 준비된 상태에서 아래 명령을 실행합니다. `output/answer-validation-v1/baseline-code/`는 변경 전 코드 보존본입니다. 원본 개인 DB 대신 임시 합성 DB만 사용합니다.

```powershell
.venv/Scripts/python.exe -m evaluation.answer_validation --phase prepare --split all --tag candidate-rerun
.venv/Scripts/python.exe -m evaluation.answer_validation --phase fixed --split all --tag candidate-rerun
.venv/Scripts/python.exe -m evaluation.answer_validation --phase application --split all --tag candidate-rerun
.venv/Scripts/python.exe -m evaluation.answer_validation --phase live --split all --tag candidate-rerun
.venv/Scripts/python.exe -m evaluation.answer_validation --phase repeat --split all --tag candidate-rerun
.venv/Scripts/python.exe -m evaluation.answer_validation_report --tag candidate-rerun
```

`fixed`는 동일한 검색 결과·근거 ID로 기준선/답변 개선/검증 개선/1회 수정 조건을 비교합니다. `application`은 보존된 추출로 검색부터 다시 실행하고, `live`는 새 추출까지 포함합니다. `repeat`는 핵심 8개를 두 번 더 실행합니다. 결과·설정·실행 코드·근거 해시를 보존하며 코드·설정·데이터가 달라지면 동일 경로 재개를 거절합니다. 데이터는 `data/answer_validation_cases.json`에 고정되어 있습니다.

보고서 정확도는 모델 검증 통과율이 아닙니다. `review.json`에 결과 파일 SHA-256, `label`, 원문 대조 `reason`을 기록해야 판정에 반영됩니다. 미검토 결과는 성공으로 계산하지 않습니다. 기존 실험 결과와 개인 DB는 변경하지 않습니다.


최초 평가 결과는 `output/answer-validation-v1/report.html`에 보존했습니다. `final-1` 실행은 당시 코드와 함께 동결되어 있으며, 기본 경로 보호 설정을 추가한 현재 코드로 다시 실행할 때는 새 태그를 사용합니다. 평가기 예외가 발생했던 한 사례의 네 조건은 `harness-retry`로 재실행하고 `replacements.json`에 대체 경로를 기록했습니다. 원래 결과는 삭제하지 않았습니다. 원문 대조 판정은 Codex의 검토이며 독립적인 사람 평가가 아닙니다.


## 기억과 함께하는 AI 대화

**AI 대화 → 새 대화**에서 바로 이야기할 수 있습니다. 일상 대화는 검색 없이 답하고,
개인 경험·인물·일정이 필요하면 현재 질문에 맞춰 전체 검색 가능한 기록을 자동으로 찾습니다.
후속 질문마다 장소·날짜·대상을 다시 해석하며, 첫 검색과 최대 두 번의 보완 검색을 사용합니다.
검색 알고리즘과 기존 단일 질문 API는 유지합니다. 아직 정리 중인 기록은 검색되지 않습니다.

- DM 말풍선으로 대화하며, 필요한 경우 목록·일정 흐름·인물 카드·표로 표시합니다.
- 인용을 누르면 답변 당시 원문 버전과 강조된 구간을 확인할 수 있습니다.
- 답변마다 최대 8개 근거를 보관하며, 대화 이력은 이 PC에서 재시작 후에도 이어집니다.
- 원본 수정·버전 복귀 시 관련 답변에 ‘이전 기록 기준’을 표시하고 이후 문맥에서 제외합니다.
- 원본 삭제 시 해당 기록에 의존하는 AI 답변과 전용 근거·인용만 영구 삭제합니다.
  나머지 대화는 남고, 기록을 복원해도 삭제된 답변은 복구되지 않습니다.
- 대화 내용을 개인 기억으로 자동 저장하지 않습니다. 최근 유효한 최대 6개 턴은 참조 해석에만 사용합니다.
- 검증되지 않은 초안을 출력하지 않습니다. 실패 요청은 같은 요청 ID로 재시도할 수 있습니다.
- 전체 횟수·최초·최후를 확정하는 집계는 지원하지 않습니다. 원인·실행 여부가 없으면 추측하지 않습니다.

DB는 v0~v4를 v5로 자동 업그레이드하며 기존 대화와 인용을 보존합니다.
v5는 재시도 요청의 질문과 선택적 기준 날짜를 함께 저장합니다. 같은 요청 ID의 입력이
달라지면 충돌로 처리하며, 화면의 재시도는 최초 날짜 조건을 유지합니다.
원래 날짜 입력을 보관하지 않았던 기존 메시지는 종전의 질문 비교 방식으로 재전송을 처리합니다.
`POST /api/v1/chat/sessions`에 `{}`를 보내면 새 대화를 만듭니다.
기존 검색 ID·선택 ID 방식은 API 호환성을 위해 남아 있지만 후속 메시지는 자동 검색합니다.
메시지 응답에는 `conversation_type`과 안전한 표시 블록 `blocks`를 추가합니다.
세션 조회의 각 메시지에 `evidence`, `snapshot`, 원본 변경 상태 `error_code`가 포함됩니다.
기존 `/api/v1/search`, `/api/v1/answers` 계약과 인증·CSRF 정책은 바꾸지 않습니다.

### 대화 품질 평가

로컬 생성 서버를 실행한 상태에서 다음 명령으로 가상 고정 근거를 평가합니다.
개인 DB와 검색·추출을 사용하지 않고 임시 DB에서만 실행합니다.

```powershell
./.venv/Scripts/python.exe -m evaluation.chat_eval --output output/chat-evaluation.json
# 한 시나리오만 확인
./.venv/Scripts/python.exe -m evaluation.chat_eval --case schedule
# 기존 평가 관제실 DB에 결과를 추가할 때
./.venv/Scripts/python.exe -m evaluation.chat_eval --db C:/path/to/evaluation.db
```

일정 변경, 후속 대명사, 동명이인, 실제 모호성, 계획과 부정, 상충 기록, 원문 속 지시문,
사용자 가정의 사실 오인 여부를 평가합니다. 결과에는 응답·인용 유효성·행동 일치·지연 시간을
기록합니다. `groundedness`와 `followup_understanding`은 의미 검토 전에는 미확정입니다.
모델의 자체 검토나 인용 ID 존재만으로 정확도 합격을 부여하지 않습니다.
평가 관제실의 검색 Recall/MRR과 혼합하지 않으며, 이 실행은 고정 근거 대화 유형으로 구분됩니다.

전체 자동 대화는 생성·임베딩 서버와 `PMA_EMBEDDING_REVISION`을 설정한 뒤 평가합니다.
다음 평가는 임시 DB에서 기록 추출부터 검색·후속 대화까지 실행합니다.

```powershell
./.venv/Scripts/python.exe -m evaluation.automatic_chat_eval --output output/automatic-chat-live.json
```

결과에는 검색 질문·조건, 답변별 원문·리비전·인용, 의미 검토 내역과 응답 시간을 기록합니다.
기대 답변은 모델에 전달하지 않습니다. 보고서는 별도 의미 검토 전까지 `pending_review`입니다.

대화 요청 전체의 시간 예산은 `PMA_CHAT_TIMEOUT`(기본 300초, 최대 3,600초)입니다.
모델 잠금 대기·검색·생성·검토·원본 변경 재시도가 같은 예산을 사용합니다.
각 모델 HTTP 호출에는 남은 예산과 기존 `PMA_TIMEOUT` 중 작은 값을 적용하고,
시간을 넘겨 도착한 결과는 폐기합니다. 저장 직전에도 확인하여 답변·근거·인용을 함께
롤백하며 `CHAT_TIMEOUT`(504, 재시도 가능)을 반환합니다. 서버 측 계산을 강제로 종료하는 기능은 아닙니다.

표시 형식은 검증된 답변을 코드로 구성하므로 별도의 모델 호출이 필요하지 않습니다.
타임라인은 항목마다 명시된 유효한 날짜가 있을 때만 사용하고, 날짜가 불분명하면 목록으로 표시합니다.
동명이인 확인 질문의 후보에서도 원문 인용을 열람할 수 있습니다.
대화 응답을 캐시해 새 검색을 생략하지 않으므로 신규 상충 기록도 다음 검색 대상에 포함됩니다.

자동 대화 평가에는 표현을 바꾼 지시어·이유·관계 질문과 주제 전환 사례가 포함됩니다.
`snapshot.performance`에는 원문 없는 모델 호출 경로·소요 시간·잠금 대기 시간이 저장되며,
평가 결과에 모델 호출 수와 단계별 HTTP 소요 시간을 집계합니다. 이는 전체 단계 CPU 시간과 다릅니다.
UI 인용의 Unicode 위치와 안전한 표시 대체 동작은 `node --test tests/chat_ui.test.mjs`로 검증합니다.

관계 질문은 ‘어떤 사이’와 같은 표현도 처리합니다. 검색하지 않은 일반 대화 응답이
기록의 유무를 주장하는 경우 해당 초안을 버리고 검색으로 전환합니다.
질문 해석의 `requested_slots`는 기존의 ‘5종류 중복 금지’와 동등한 배열 상한을 명시하여
제약 디코더에서 반복 출력이 길어지는 것을 제한합니다. 검색 순위·필터 알고리즘은 유지합니다.

### 대화 UI/UX 통합

대화 목록은 접을 수 있으며 제목과 메시지 내용을 검색할 수 있습니다. AI 답변의 `근거 N건`은
같은 원본·버전을 합쳐 세고, 클릭하면 기본적으로 닫힌 상세 패널에서 당시 원문과 인용 구간을
보여 줍니다. 기록 작성 시각·기준 시각·사건 시각을 구분하고, 없는 날짜를 추정하지 않습니다.
모바일에서는 목록을 드로어로, 근거를 하단 상세 화면으로 제공합니다.

이전 주제 목록은 유효한 완료 메시지로 구성합니다. 선택하면 `context_message_id`를 요청에
포함하며, 서버는 같은 세션의 유효한 메시지인지 확인합니다. 선택한 대화는 마지막 해석 문맥으로
사용하고 개인 사실의 증거로 사용하지 않습니다. 요청의 선택 조건도 중복 제출 검사에 포함합니다.
정정 버튼은 자유 입력을 돕고, 원본 기록을 수정하지 않습니다. 구조화된 인물·시간 필드를 별도
모델로 추측하지 않고 선택한 질문을 현재 주제로 표시합니다.

실제 모호성이 있을 때만 인용이 유효한 후보를 선택 버튼으로 제공합니다. 후보를 직접 설명하거나
선택을 취소하고 다른 이야기를 할 수 있습니다. 원본 변경 또는 후속 턴 완료 시 이전 후보 선택은
만료됩니다. 짧은 역할 표현(예: `동아리 민수`)도 유일한 후보를 구분하면 처리하며, 새 검색과
답변 검증은 그대로 수행합니다.

추가 API:

- `GET /api/v1/chat/sessions?q=...`: 제목·사용자 질문·유효한 답변 검색. 삭제·무효화된 AI 답변은 제외합니다.
- `GET /api/v1/chat/sessions/{id}/requests/{request_id}`: 실제 처리 단계와 실행 여부 조회.
- `POST /api/v1/chat/sessions/{id}/requests/{request_id}/cancel`: 진행 중 요청의 후속 처리·저장 중단.
- 메시지 요청의 선택적 `context_message_id`: 이전 주제 또는 확인 질문의 대상 메시지.

중단은 실행 중인 모델 HTTP 호출을 강제 종료하지 않습니다. 해당 호출이 돌아온 뒤 다음 단계 또는
저장 전에 중단을 확인하며, 실행이 정리되기 전 같은 세션의 재시도는 거절합니다. 접수되지 않은
요청의 중단을 성공으로 보고하지 않습니다. 기존 인증·CSRF·로컬 접근 제한을 그대로 적용합니다.

`presentation`은 검증된 텍스트의 표시 지시만 담습니다. 알 수 없는 형식은 텍스트로 대체하고,
일부 항목이 누락된 표시 지시도 나머지 검증된 답변을 숨기지 않습니다. HTML은 실행하지 않으며
작은 제목·강조의 제한된 Markdown만 표시합니다. 비교와 확인 한계 표시는 검증된 답변의 명시적
내용을 바탕으로 하며 독립적인 의미 판정을 추가하지 않습니다. `PMA_DIAGNOSTICS=1`일 때만
검색·검증·소요 시간과 현재 세션의 상태 집계를 개발자 진단에 표시합니다. 의미 정확도 점수는
이 집계로 자동 합격 처리하지 않습니다.

UI 계약과 실제 모델의 주제 복귀·선택 입력은 다음으로 확인합니다. 모델 평가는 먼저
`evaluation.automatic_chat_eval`로 만든 합성 기록 디렉터리를 사용하며 사용자 DB와 분리합니다.

```powershell
node --test tests/chat_ui.test.mjs
./.venv/Scripts/python.exe -m pytest tests/test_chat_ux.py
./.venv/Scripts/python.exe -m evaluation.chat_ux_eval --data-dir output/automatic-eval-data --output output/chat-ux-eval.json
```

## 일반 대화와 개인 기억 통합 (v1.1)

AI 대화 입력창에서 자동 / 일반 대화 / 내 기억 사용을 선택할 수 있습니다.
기본값은 자동이며, 질문과 최근 대화에 따라 일반 답변·기억 검색·혼합 답변을 선택합니다.
일반 대화는 개인 기록을 검색하지 않습니다. 답변 검증이 실패해도 검색으로 전환하지 않으며,
최근 대화 내용은 후속 질문과 코드 예제를 위해 유지합니다.
내 기억 사용은 기존 검색과 원문 검증을 사용하고 필요하면 일반적인 제안을 덧붙입니다.

메시지 API의 선택 필드 `mode`는 `auto`, `general`, `memory`, `hybrid`를 지원합니다.
생략하면 기존 요청처럼 `auto`로 처리합니다. 기존 `conversation_type=mixed`는 유지하고,
새 `conversation_mode=hybrid`를 함께 반환합니다. 각 답변 항목의 `source_type`은
`personal_memory`, `general`, `inference`로 출처 성격을 구분합니다.
혼합 답변은 검증된 개인 사실을 먼저 생성한 뒤 그 사실에 기반한 제안·추론을 별도 생성하고 검토합니다.
기록이 없으면 개인 사실을 만들지 않고 근거 부족 안내와 일반적인 도움만 제공합니다.

선택 모드는 기존 요청 JSON에 저장하므로 DB 테이블 변경 없이 세션 재개와 재시도에 복원됩니다.
동일 요청 ID에서 모드가 달라지면 409 충돌로 처리합니다. 사용자 지정 모드는 검색 여부에 대한
제약이며, 검색·참조 해석·정정 등 실행 동작과 별개입니다. 기존 구조에는 별도 ChatAction 열거형이 없습니다.
기존 Qwen 서버와 모델 사용 잠금을 공유하며 새 모델을 로딩하지 않습니다.

검증: `tests/test_conversation_modes.py`는 검색 차단, 호출 횟수, 후속 맥락, 모드 전환,
재시도 충돌, 세션 복원, 근거 없는 혼합 답변을 검사합니다. `tests/chat_ui.test.mjs`는
모드 복원·재시도 및 코드 블록의 안전한 텍스트 표시를 검사합니다.
