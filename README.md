# Personal Memory Agent · 기억의 서랍

Windows PC에서 개인 기록을 저장하고, 로컬 AI가 추출한 기억을 검색해 근거와 함께 답하는 단일 사용자 앱입니다. 기존 추출 스키마 v4와 CLI를 함께 유지합니다.

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

질문·답변 이력은 저장하지 않습니다. 전체 횟수·최초/최후·순위 집계는 지원하지 않습니다. 기간 필터가 있으면 시점이 불명확한 기억을 제외합니다. 기록당 4,000자, 질문당 1,000자로 제한하며 모델 문맥 길이도 검사합니다. 계획을 실행 결과로 오해하는 등 의미 오류는 여전히 가능하므로 근거를 확인하세요.

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
