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

### 브라우저에서 직접 추출 테스트

llama.cpp 서버를 `127.0.0.1:8081`, 컨텍스트 32768로 실행한 후 프로젝트 폴더에서:

```powershell
python pma_web.py
```

`http://127.0.0.1:8766`에 접속해 원문을 입력하고 **기억 추출하기**를 누릅니다.
짧은/긴 예시, 한국 시간 기준 시각, 분할 크기를 선택할 수 있습니다.
긴 예시는 작은 조각(1,500 바이트)을 선택하면 여러 조각으로 처리됩니다.
기억 카드, 날짜, 원문 근거 강조, 최종 JSON, 검증 결과, 호출 정보와 원본 응답을 확인합니다.
실패 시에도 오류와 수신한 모델 응답을 확인하고 JSON으로 내려받을 수 있습니다.
**이번 정확도 테스트 결과** 버튼은 로컬에 저장된 재검증/이어 실행 보고서를 표시합니다.
저장 응답을 활용한 결과는 새 모델 호출과 구분해서 표시하며, 사례별 미통과 항목도 함께 보여줍니다.

기존 CLI와 동일한 추출기를 호출하며 추출 규칙이나 스키마를 변경하지 않습니다.
스키마 통과는 의미 정확성·누락 없음을 보장하지 않습니다.
웹 요청은 백그라운드에서 한 번에 하나씩 실행하며 페이지 새로고침 후 작업 상태를 복구합니다.
서버 메모리에 최근 20개 작업만 유지하고, 서버 종료 시 삭제합니다.
브라우저에는 마지막 작업 ID만 저장합니다. 결과 파일은 저장 버튼을 눌렀을 때만 다운로드합니다.
모델 응답 제한 시간은 호출별 30분입니다. CPU에서는 긴 입력에 많은 시간이 걸릴 수 있습니다.
웹 서버는 로컬 주소에만 바인딩됩니다. 이 화면은 입력별 추출 실험용이며 대화 이력 검색 기능은 없습니다.

`PMA_ENDPOINT`, `PMA_MODEL` 등 기존 모델 환경변수를 사용할 수 있습니다.
웹 서버 종료는 실행한 터미널에서 Ctrl+C입니다.

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

## 정확도 개선: 문장 근거와 날짜 계산

- 모델 호출 시에만 사용하는 스키마에서 근거를 `sentence_id`로 제한합니다.
  코드가 선택된 ID를 원문의 문장으로 복원하며, 저장용 v4 스키마는 동일합니다.
- 잘못 선택된 근거는 기억 내용 전체가 원문 한 문장에 그대로 일치하고 명시된 대상도 그 문장에 있는
  경우에만 다시 연결합니다. 반복 문장처럼 후보가 여러 개이거나 패러프레이즈이면 추측해 연결하지 않습니다.
  이 보정도 `metadata.warnings`에 원래 근거와 새 근거를 함께 기록합니다.
- 생성 스키마는 `time.start/end=null`을 강제합니다. 상대 날짜 계산은 코드가 담당하며,
  한국 시간대 기준 날짜를 사용합니다. 기억에 연결된 근거에 없는 시간 표현은 제거하고 미확정으로 유지하며,
  제외한 원래 값과 이유를 `metadata.warnings`에 기록합니다.
- 원문 구조 검증 후 날짜를 정규화하고, 최종 v4 스키마와 원문 근거를 검증합니다.
- 같은 사건의 참여자·장소·대상을 별도 사건으로 반복하지 않는 예시와,
  독립 행동·부정·주고받는 인물 관계를 보존하는 예시를 실행 프롬프트에 추가했습니다.
- 문장 ID와 동적 스키마 크기도 보수적인 컨텍스트 예산에 포함합니다.

원본 공통 프롬프트와 스키마 파일은 유지합니다. 문장 근거 일치는 의미 정확성의 보장이 아니며,
유사한 기억을 문자열 유사도만으로 삭제하지 않습니다. 긴 글의 경계 문맥과 모호한 대명사는 여전히 검토가 필요합니다.

실제 모델 회귀 확인: `python -B scripts/eval_accuracy.py`
결과는 `results/local_accuracy_report.json`에 저장되며 Git에서 제외됩니다.
짧은 사건, 관계·부정·계획, 이전 긴 입력(로컬 파일이 없으면 짧은 분할 예제)을 실행합니다.
`checks`는 이 소수 사례의 명시적 기대값만 검사하며 일반 정확도 점수로 해석하면 안 됩니다.
