# Personal Memory Agent · 기억의 서랍

Windows PC에서 개인 기록을 저장하고, 로컬 AI가 추출한 기억을 검색해 근거와 함께 답하는 단일 사용자 앱입니다. 기존 추출 스키마 v4와 CLI를 함께 유지합니다.

## 평가 관제실

`pwsh -File ./run_app.ps1 -Evaluation`으로 실행하면 모델 서버와 웹 앱이 함께 시작되고
기존 화면에 **평가 관제실** 메뉴가 나타납니다. `python -m pma`는 모델 서버를 시작하지 않습니다.
평가 진행률·현재 처리 단계, 정확도·근거 지표, 질문별 실패 분석, 시나리오별 결과,
동일 조건 버전 비교를 확인할 수 있습니다. 기본값은 비활성화이며 평가 DB는 개인 기억 DB와 분리됩니다.
질문·답변 원문과 상세 진단은 `PMA_EVALUATION_DETAILS=1`을 별도로 설정해야 조회됩니다.
이 실행용 저장소에는 관제실 조회 기능만 포함하며, 평가 실행기와 테스트 데이터는 포함하지 않습니다.

## 빠른 시작

PowerShell 7, Python 3.14, uv가 필요합니다. 최초 의존성/모델 준비에만 인터넷을 사용합니다.

```powershell
uv sync --frozen --python 3.14
./run_app.ps1
```

가속 모드는 `-Acceleration auto`(기본), `cpu`, `gpu`로 선택합니다.
자동 모드는 서버가 보고한 GPU 장치를 사용하며 GPU 모델 준비 실패 시 시작한 서버를
정리하고 CPU로 한 번 재시도합니다. CPU 모드는 GPU 오프로딩을 명시적으로 끕니다.
`-GenerationThreads 8 -EmbeddingThreads 4`처럼 각 서버의 CPU 스레드 수를 지정할 수
있으며 생략하면 서버 기본값을 사용합니다. `-ExternalServers`에서는 이 옵션들을
실행 중인 서버에 적용하지 않습니다. 모델·문맥 길이·답변 검증은 모드에 따라 바뀌지 않습니다.
`-EmbeddingAcceleration cpu`를 함께 지정하면 생성 모델만 GPU에서 실행할 수 있습니다.
임베딩 가속의 기본값 `auto`는 전체 가속 모드를 따릅니다. 전체 모드가 `cpu`이거나
자동 모드가 CPU로 전환되면 두 모델 모두 CPU에서 실행합니다.
추출의 읽기 시간 초과는 같은 청크를 자동으로 다시 생성하지 않습니다. 연결 오류 재시도와
성공한 추출 결과를 재사용하는 임베딩 재시도는 유지합니다. CPU에서 긴 기록을 처리할 때
기본 180초 제한이 부족하면 실행 전에 `$env:PMA_TIMEOUT = '600'`처럼 늘릴 수 있습니다.
이 설정은 처리 속도를 높이는 옵션이 아니며 모델·추출 범위·검증 수준은 바뀌지 않습니다.

기록 처리의 `job_performance` 로그는 원문 없이 모델 대기, 분할, 토큰 계산, 추출,
임베딩, 저장 시간과 호출·재시도 횟수를 기록합니다. 단계 시간은 포함 관계가 있으므로
합산하지 않습니다. 백그라운드 작업은 모델 호출 사이에 대기 중인 검색·대화에 순서를
양보합니다. 진행 중인 모델 호출 자체를 중단하지는 않습니다.
대화는 전체 요청 제한 시간 안에서 모델 차례를 기다리며, 대기 중에도 취소할 수 있습니다.
대화에 차례를 양보한 백그라운드 기록은 모델 HTTP 제한 시간이 지나도 대기 자체만으로
실패하지 않습니다.

합성 데이터 성능 측정은 `python -m evaluation.performance_benchmark --mode cpu --output .local/bench/cpu`
및 같은 상위 폴더의 `--mode gpu --output .local/bench/gpu`로 실행합니다.
18081·18082 포트를 사용하며 개인 DB를 읽지 않습니다. 기본값은 시나리오별 준비 실행 1회와
측정 5회입니다. `--scenarios`, `--samples`, `--threads`로 추가 실험을 제한할 수 있습니다.
같은 실험 폴더에서는 `source-snapshot`에 고정한 작업 스케줄러·대화 흐름을 재사용합니다.
새 구현을 비교할 때는 새 상위 폴더를 사용하세요.
`python -m evaluation.performance_report .local/bench`로 실패를 포함한 결과를 집계합니다.
RAM은 Python·두 서버의 작업 집합 합계이고, VRAM은 바탕화면 등을 포함한 GPU 전체 사용량의
1초 간격 관측 최댓값입니다. CPU 모드는 GPU가 있는 PC에서도 오프로딩을 0으로 강제하며,
물리적으로 GPU가 없는 PC에서의 검증을 뜻하지는 않습니다.
같은 모델 시간 초과·연결 실패가 연속 재현되면 해당 시나리오의 나머지 반복은 중단하고
`incomplete_scenarios`에 요청한 횟수와 실제 횟수를 남깁니다. 실패 시간은 성공 처리 시간으로
해석하지 않습니다. `--concurrent-short`는 짧은 백그라운드 기록을 쓰는 별도 대기 정책 검증입니다.

CPU·GPU·혼합 실행의 실제 시간·메모리와 채택하지 않은 실험은
[CPU·GPU 성능 측정 보고서](evaluation/performance_results.rst)에 정리했습니다.
긴 CPU 기록의 600초 제한 진단은 기본 180초 비교와 구분해 기록했습니다.

대량 합성 DB의 조회·검색 최적화 결과는
[DB 성능 측정 보고서](evaluation/database_results.rst)에 정리했습니다.
근거 일괄 조회, 보관·사용자 범위 SQL 개선, 최대 64MiB 예산의 정규화 벡터 캐시와
요청 안의 검색어 정규화 재사용을 적용했습니다. 모델·검증·API·DB 스키마는 유지합니다.
`python -m evaluation.database_benchmark --output .local/db-bench-new --sizes 1000 10000 25000 --samples 5`로
개인 DB와 모델 서버를 사용하지 않고 재현할 수 있습니다. 모델 호출은 고정 대체 구현이므로
보고서의 개선율은 실제 AI 답변 전체의 개선율과 구분해야 합니다.

검색어 매칭에는 검증된 선택적 C++ 경로도 추가했습니다.
한영 번역·발음·유사어 검색 규칙과 검증 방법은 [다국어 검색 문서](docs/multilingual_search.md)에 정리했습니다.
등록 별칭은 동일 개념으로 연결하고, 자동 번역·발음·유사어 후보는 낮은 가중치의 보조 검색으로 사용합니다.
[C++ 시제품 비교·적용 보고서](evaluation/native_keyword_results.rst)에
기존 최적화 Python과의 실제 속도·RAM·전체 응답 일치 결과를 기록했습니다.
기본 `PMA_KEYWORD_BACKEND=auto`는 호환 확장 파일이 있으면 사용하고, 없으면 Python을 사용합니다.
`python`은 기존 구현을 강제하고 `cpp`는 C++를 강제하되 확장이 없으면 원인을 표시합니다.
두 경로 모두 같은 모델·근거 검증·검색 순위를 유지하며 GPU에 의존하지 않습니다.

확장 파일은 Python·운영체제별 빌드가 필요하며 저장소에 바이너리를 포함하지 않습니다.
현재 시제품은 Windows x64 CPython 3.14에서 검증했습니다. 해당 환경에서
[Zig 0.15.2 공식 배포본](https://ziglang.org/download/)을 준비한 후
`python -m evaluation.build_keyword_native --zig <zig.exe 경로> --install`로 빌드·배치할 수 있습니다.
앱을 다시 시작하면 자동으로 사용합니다. 컴파일러와 빌드는 앱 실행의 필수 조건이 아닙니다.
합성 데이터 재측정은
`python -m evaluation.native_keyword_benchmark --output .local/cpp-bench-new --extension .local/native-keyword/_keyword_native.cp314-win_amd64.pyd`로 실행합니다.

앱 재시작 후 실제 C++ 실행 확인과 실제 Qwen/BGE의 CPU·GPU 비교는
[실제 모델 전체 처리 비교](evaluation/native_real_model_results.rst)에 정리했습니다.
이 밀집 합성 입력에서는 검색이 개선됐지만 GPU 답변 전체의 개선은 뚜렷하지 않았고,
CPU 답변은 두 경로 모두 컨텍스트 한도로 완료하지 못했습니다.
`evaluation/run_native_real_models.ps1`는 개인 DB와 분리해 측정한 뒤 모델 서버를 복구하고 앱을 재시작합니다.

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

### 기록 저장과 검색

1. 기록과 기준 시각을 입력하면 원문을 먼저 저장합니다.
2. 백그라운드 작업이 Qwen으로 기억을 추출하고 스키마·원문 인용을 검증합니다. BGE-M3 임베딩까지 성공한 기록만 검색 가능합니다.
3. 질문의 시간 조건을 해석하고 벡터·키워드 검색 결과를 결합합니다. Qwen이 찾은 기억으로 답하며 각 답변에서 원문을 열 수 있습니다.
4. 수정·이전 버전 복귀 시 새 버전을 만들고 다시 처리합니다. 처리 실패 시 원문은 남으며 재시도할 수 있습니다.
5. 삭제한 기록은 즉시 검색에서 제외합니다. 휴지통에서 30일간 복원할 수 있고, 만료 시 앱 시작 또는 실행 중 정리 작업에서 영구 삭제합니다.

기존 단일 질문·답변 이력은 저장하지 않습니다. 별도 AI 대화 탭은 이력과 답변별 근거를 로컬 DB에 저장합니다. 전체 횟수·최초/최후·순위 집계는 지원하지 않습니다. 기간 필터가 있으면 시점이 불명확한 기억을 제외합니다. 기록당 4,000자, 질문당 1,000자로 제한하며 모델 문맥 길이도 검사합니다. 계획을 실행 결과로 오해하는 등 의미 오류는 여전히 가능하므로 근거를 확인하세요.

## 질문 오타 처리

질문 원문과 저장된 기록은 수정하지 않습니다. 기존 질문 분석에서 일반 명사의 철자·띄어쓰기
교정을 최대 두 구간 제안하고, 허용된 일반 명사와 원문 구간·검색 조건을 검증한 경우에만
보정문 하나를 보조 검색에 사용합니다. 초기 어휘는 내용·회의·기록·여행·일정·약속·예약·자료·문서·업무·프로젝트·보고서·음식·운동입니다.
이름·날짜·숫자·부정·동사·조사와 알 수 없는 표현은 자동 교정하지 않으며,
교정으로 사건 종류나 기간 등 조건이 달라지는 경우에도 원문 검색을 유지합니다.
따라서 모든 오타를 복구하는 기능은 아니며, 이름처럼 쓰인 일반 단어의 모호성까지 완전히 판별하지는 못합니다.

원문과 보정문은 같은 스냅샷·필터 안에서 함께 검색합니다. 검색 방식별로 원문 순위 기여와
보정문 순위 기여의 0.8배 중 큰 값만 반영하여 중복 가산을 막습니다. 보정 검색이 최종 답변의
근거 순위에 기여하면 안내와 **원문으로만 다시 검색** 버튼을 표시합니다. 상세 검색 설명에는
보정 표현의 순위와 일치 구간을 별도로 표시합니다. 교정이 거절되어도 원문 검색은 계속합니다.
답변의 **오타 보조 검색**을 펼치면 검색 원문·보정 표현·변경 부분·실제 검색 실행 여부와
표시된 근거 순위에 반영됐는지를 확인할 수 있습니다. 보정 미적용 사유도 같은 곳에 표시합니다.
보조 임베딩 실패 시 원문만 재시도합니다. AI 대화에서 거절된 교정이 있으면 해당 턴의 추가
검색 재작성을 중단해 교정 제한을 우회하지 않게 합니다.

검색·답변·대화 검색·메시지 API의 선택 필드 `correction_enabled`는 기본값 `true`이며,
`false`로 보내면 해당 요청의 오타 보조 검색을 끕니다. 대화 재시도에서 이 값은 요청 ID의
동일성 검사에 포함됩니다. DB 마이그레이션과 기존 기록 재색인은 필요하지 않습니다.

## 구성과 데이터

| 경로 | 역할 |
|---|---|
| `pma/web.py`, `pma/static/` | 로컬 API, 세션/CSRF, 한국어 웹 UI |
| `pma/service.py` | 작업 실행, 검색·답변, 동시 모델 사용 제한 |
| `pma/store.py`, `pma/lock.py` | SQLite 트랜잭션·버전·휴지통·단일 실행 잠금 |
| `pma/models.py` | 로컬 생성·임베딩·질문 분석 |
| `scripts/memory_agent/` | CLI·앱이 공유하는 추출/검증 파이프라인 |
| `schema/`, `prompts/` | 기존 v4 스키마와 추출 지침 |
| `evaluation/` | 평가 관제실 조회에 필요한 저장소·계약·지표·마이그레이션 |

DB 기본 위치는 `%LOCALAPPDATA%\PersonalMemoryAgent\memory.db`입니다. records, revisions, jobs, memories, evidence, embeddings와 파생 facts, memory_links, dismissed_links 테이블을 사용합니다. SQLite user_version은 5이며 기존 DB는 다음 앱 시작 시 원문과 이력을 유지하면서 확장합니다. 저장된 기억의 파생 사실은 50개씩 재구축하며, 완료 전에는 구축 중 상태와 불완전한 검색 범위를 표시합니다. 수정 이력은 기록 영구 삭제 때 함께 삭제됩니다. DB는 암호화되지 않으며 Windows 사용자 계정/디스크 보호가 필요합니다. 백업은 앱을 정상 종료한 후 데이터 디렉터리를 복사하세요. 영구 삭제는 앱 DB에서 제거하지만 OS 백업·SSD 잔존 데이터까지 지우는 기능은 아닙니다.

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

## AI 대화

**AI 대화 → 새 대화**에서 바로 대화할 수 있습니다. 자동 모드는 질문과 최근 맥락에 따라 일반 답변, 개인 기억 검색 또는 혼합 답변을 선택합니다. 일반 대화 모드는 개인 기록을 검색하지 않으며, 내 기억 사용 모드는 검색한 원문을 근거로 답합니다.

검증된 개인 사실과 일반적인 제안·추론은 구분해서 표시합니다. 인용에서 실제 사용한 원문 버전을 확인할 수 있습니다. 원문 수정 시 관련 답변에 변경 상태가 표시되며, 원문 삭제 시 관련 답변과 근거가 제거됩니다. 대화 내용은 개인 기억으로 자동 저장하지 않습니다.

대화 이력과 질문별 근거는 로컬 DB에 저장됩니다. 대화를 다시 열어 이어갈 수 있고, 실패한 요청을 같은 모드로 재시도할 수 있습니다. 코드 블록과 간단한 Markdown 표를 표시하며 HTML은 실행하지 않습니다.

- `POST /api/v1/chat/sessions`: 빈 요청으로 새 대화 생성. 기존 검색 결과를 선택해 시작할 수도 있습니다.
- `GET /api/v1/chat/sessions`, `GET /api/v1/chat/sessions/{id}`, `DELETE /api/v1/chat/sessions/{id}`: 대화 목록·조회·삭제.
- `POST /api/v1/chat/sessions/{id}/messages`: `request_id`, `question`, 선택적 `today`, `context_message_id`, `mode`.
- `mode`: `auto`(기본), `general`, `memory`, `hybrid`. 같은 요청 ID에서 모드를 바꾸면 409 충돌을 반환합니다.
- `GET /api/v1/chat/sessions/{id}/requests/{request_id}`: 진행 상태 조회.
- `POST /api/v1/chat/sessions/{id}/requests/{request_id}/cancel`: 진행 중 요청 취소.

`PMA_CHAT_TIMEOUT`은 대화 요청 전체의 시간 제한이며 기본 300초, 최대 3,600초입니다. `PMA_DIAGNOSTICS=1`이면 검색·검증·소요 시간 진단을 표시합니다.

## 대화에서 기억 저장

세 대화 모드에서 메시지의 **기억에 저장**, 선택 문장, 복수 메시지 선택을 사용할 수 있습니다.
‘이거 기억해’ 같은 요청은 저장 후보만 만들며, 미리보기에서 내용·유형을 확인하고 승인해야 개인 기록으로 등록됩니다.
AI 답변은 제안으로 구분하고 저장 승인을 사실 검증으로 취급하지 않습니다.
**기억 관리**에서 보류 후보, 저장 상태, 정정·이력·삭제·검색 처리 재시도를 확인할 수 있습니다.
기존 Qwen/BGE로 중복·보완·시간 변화·충돌을 비교한 뒤, 별도 추가·관계 연결 또는 정확한 기록의 정정을 승인합니다.
미리보기 내용을 바꾸거나 기존 기록이 변경되면 다시 비교해야 합니다. 기억 보관·보관 해제로 검색 포함 여부를 관리할 수 있습니다.
기본 정책은 수동 저장이며, 기억 관리에서 후보 제안(SUGGEST)을 켤 수 있습니다. 승인 없는 자동 저장은 비활성입니다.

구현 계약·실행한 평가·아직 제공하지 않는 범위는 [기억 저장 구현 보고서](docs/memory_capture/implementation_report.md)와
[남은 범위](docs/memory_capture/remaining_issues.md)를 참조하세요.

## CLI

`python -m scripts.main --help`로 추출 CLI 옵션을 확인할 수 있습니다. `config/`, `prompts/`, `schema/`와 `scripts/memory_agent/`는 웹 앱과 CLI가 사용하는 실행 파일입니다.
