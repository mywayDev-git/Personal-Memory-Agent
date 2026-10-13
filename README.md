# Personal Memory Agent — 기억 추출 v4

일기·메모 한 편에서 여러 기억을 추출합니다. 팀원 브랜치의 JSON Schema v4.0,
추출 프롬프트, llama.cpp 클라이언트와 검증기를 기반으로 기억별 시간 정규화와
긴 원문 분할을 추가했습니다. Python 3.13에서 자동 테스트했습니다.

## 실행

```powershell
python -m pip install -r requirements.txt
```

팀원과 동일한 **Qwen3-8B-Q4_K_M GGUF 파일**을 llama.cpp 서버로 실행합니다.
모델 이름 설정만으로 모델 파일이 다운로드되거나 교체되지는 않습니다.
서버 빌드, GGUF 체크섬, chat template와 thinking 설정도 팀원 환경에 맞춰야 합니다.
다음은 모델 파일과 실행 파일을 준비한 환경에서의 실행 예시입니다.

```powershell
llama-server -m "C:\models\Qwen3-8B-Q4_K_M.gguf" --alias Qwen3-8B-Q4_K_M --port 8081 -c 32768
```

현재 서버 빌드가 최상위 `json_schema` 요청을 지원해야 합니다. 실제 빌드의
옵션과 메모리 용량을 확인하고, `--context-tokens`를 서버에서 요청당 사용 가능한
컨텍스트 크기에 맞추세요. 동시 처리 슬롯으로 컨텍스트가 나뉘는 설정도 확인해야 합니다.

```powershell
$env:PMA_ENDPOINT = 'http://127.0.0.1:8081/v1/chat/completions'
$env:PMA_MODEL = 'Qwen3-8B-Q4_K_M'
python pma_extract.py --text '어제 팀원들과 회의했다. 다음 주에 모델을 결정하기로 했다.' --source-id diary-001 --reference-time '2026-10-10T12:00:00+09:00' --output results/local_sample.json
python pma_extract.py --input diary.txt --source-id diary-002 --context-tokens 32768 --chunk-bytes 6000 --output results/local_long.json
```

`--input`은 UTF-8 텍스트 파일입니다. 기준 시간이 없으면 `--reference-time`을 생략합니다.
공통 스키마가 date-time을 요구하므로 날짜만 있는 문자열은 받지 않습니다.
작성 시각을 모르는 경우 임의의 자정을 넣지 마세요.

기본 요청 설정은 temperature=0, seed=42, top_p=1, max_tokens=4096, timeout=180초입니다.
`PMA_MAX_TOKENS`, `PMA_TIMEOUT`, `PMA_TEMPERATURE`, `PMA_TOP_P`, `PMA_SEED`로 조정할 수 있습니다.
서버와 GPU/CPU 설정에 따라 재현성과 지연 시간이 달라질 수 있습니다.

## 공통 출력과 Python 사용

```python
from pma_extract import extract_document, embed_text

result, metadata = extract_document(
    '어제 회의했다. 다음 주에 결정한다.',
    source_id='diary-001',
    reference_time='2026-10-10T12:00:00+09:00',
)
for memory in result['memories']:
    print(memory['local_id'], embed_text(memory))
```

CLI 출력은 `{"result": ..., "metadata": ...}`입니다. DB에 전달할 공통 객체는
`result`이며 `schema_version`, `source_context`, `memories`만 포함합니다.
각 기억에는 팀원 스키마의 content, memory_type, subject/predicate/object,
target, time, assertion_polarity, polarity, content_certainty, evidence와 local_id가 있습니다.
`local_id`는 원문 내부 ID입니다. DB의 영구 ID로 단독 사용하지 마세요.
요청 상태·원문 구간 위치·검증 결과는 스키마 바깥 `metadata`에 둡니다.
구간 위치는 원문 Python 문자열의 문자 인덱스이며 end는 포함하지 않습니다.

## 기억별 시간

LLM은 각 기억에 연결된 `time.raw`와 이를 포함하는 원문 근거를 추출합니다.
Python은 이 표현만 정규화하며 LLM이 계산한 날짜를 그대로 저장하지 않습니다.

| 입력 표현 / 기준일 2026-10-10 | 정규화 |
|---|---|
| 어제 | 2026-10-09, day |
| 다음 주 | 2026-10-12 ~ 2026-10-18, range |
| 지난달 | 2026-09, month |
| 작년 | 2025, year |
| 2024년 2월 29일 / 2024-02-29 | 기준 시간 없이도 2024-02-29 |
| 표현 없음 | raw/start/end=null, unknown |
| 기준 시간 없는 내일 | raw 보존, start/end=null, relative |

주는 월요일 시작입니다. 작성일을 사건 날짜로 자동 대입하지 않습니다.
시각만 있는 표현, 연도 없는 월·일, '그다음 날', 지속 시간, 여러 대안,
날짜와 시각이 혼합된 아직 지원하지 않는 표현은 raw를 보존하고 start/end를 null로 둡니다.
정규화하지 못한 표현을 조용히 확정 날짜로 바꾸지 않습니다.
시간 표현이 해당 기억의 근거 인용에 없으면 문서 전체 처리를 실패시킵니다.
LLM이 다른 사건의 시간을 잘못 연결하는 의미 오류까지 자동 검증하는 것은 아닙니다.

## 긴 원문

- UTF-8 바이트 한도로 분할하고 가능한 한 문단·문장 경계를 선택합니다.
- 기본 한도는 구간당 6000바이트, 앞 구간과 최대 160문자 겹침입니다.
- 프롬프트·스키마·메타데이터·출력 한도·메시지 여유분도 컨텍스트 예산에 포함합니다.
- 정확한 토크나이저 계수 대신 Qwen의 byte-fallback에 대한 보수적인 바이트 상한을 사용합니다.
- 모든 원문 문자가 적어도 한 구간에 포함됩니다. 요약으로 원문을 대체하지 않습니다.
- `finish_reason=length`이면 해당 구간을 더 작게 나눠 최대 3단계까지 재처리합니다.
- 중복은 정규화한 기억 필드가 같고 동일한 원문 인용 위치를 공유할 때만 합칩니다.
- 구간 하나라도 스키마·근거 검증이나 분할 재시도에 실패하면 성공한 일부만 반환하지 않습니다.

연결 문맥이 겹침 범위를 넘는 대명사/시간 표현, 패러프레이즈 중복, 의미 누락은 남을 수 있습니다.
모든 문자 전달과 JSON 유효성은 기억 내용의 완전성을 보장하지 않습니다.
추론 오류를 평가하려면 실제 모델로 긴 일기와 여러 날짜·인물이 섞인 자료를 별도 채점해야 합니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
python timeparse.py
```

자동 테스트는 날짜 분리·누락 날짜·월/연도 정밀도·윤년·연말 경계,
한글/이모지 분할·원문 범위 보존·중복 판정·출력 잘림 재분할,
스키마/근거 실패와 실제 로컬 모의 HTTP 서버 요청을 검증합니다.
모의 서버 테스트는 모델 품질 평가가 아닙니다.

## 기존 코드와 범위

- `pma_extract.py`: 새 v4 진입점. 기존 extract_unit/MemoryUnit API는 교체되었습니다.
- `scripts/memory_agent/`: 클라이언트, 분할, 시간 정규화, 파이프라인, 검증.
- `schema/`: 팀원 원본 스키마 두 개를 변경 없이 사용.
- `prompts/extraction.txt`: 팀원 원본. 실행 시 시간 계산/분할 지침을 덧붙임.
- `legacy_pma_extract.py`: 기존 Ollama 카드 추출기 보존.
- `run_test.py`, `check_order.py`: 기존 카드 형식을 평가하므로 legacy 추출기 사용.
- `extract_memory.py`, `eval_extract.py`: 기존 baseline. Ollama와 pydantic 별도 설치 필요.
- `timeparse.py`: 기존 규칙 파서 보존. 새 시간 모듈은 표현 전체가 일치하는 규칙만 사용.

DB 저장·과거 기억 검색·질의응답·기억 간 모순 해결은 이번 변경 범위에 포함하지 않습니다.
