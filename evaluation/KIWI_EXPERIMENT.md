# Kiwi + LLM 비교 실험

운영 앱과 분리된 합성 데이터 평가기다. 개인 DB를 읽지 않으며 각 실행은 별도 임시 SQLite DB를 사용한다.
운영 코드의 변경 전부터 있던 작업 내용은 그대로 유지한다.

## 준비

Python 3.14, uv, 실행 중인 로컬 생성/임베딩 서버가 필요하다. Kiwi는 선택적인 `evaluation` 의존성 그룹에만 있다.
기본 `uv sync --frozen`에는 Kiwi가 포함되지 않는다.

```powershell
uv sync --frozen --group evaluation
$env:PMA_EMBEDDING_REVISION = (Get-FileHash -LiteralPath 'C:\models\bge-m3-Q8_0.gguf' -Algorithm SHA256).Hash.ToLowerInvariant()
```

실제 서버에 로드된 임베딩 파일을 지정한다. 평가기는 모델 서버 `/v1/models`의 식별 정보도 보존한다.
서버가 파일 해시를 제공하지 않으므로 환경 변수의 파일 해시만으로 실제 로드 파일의 일치를 증명하지는 못한다.

## 실행

```powershell
# 개발용 첫 4개 사례의 전체 비교군. 미실행 사례는 보고서에 남는다.
uv run --frozen --group evaluation python -X utf8 -B -m evaluation.kiwi_compare --output output/kiwi-dev --split dev --limit 4

# 같은 출력 폴더로 이어서 개발용 24개 전체 실행
uv run --frozen --group evaluation python -X utf8 -B -m evaluation.kiwi_compare --output output/kiwi-dev --split dev

# 개발 실행 완료 후 동일 설정을 동결하여 고정 평가 실행
uv run --frozen --group evaluation python -X utf8 -B -m evaluation.kiwi_compare --output output/kiwi-test --split test --freeze-from output/kiwi-dev

# 결과에서 보고서 재생성. 실행 중에도 완료된 체크포인트만 읽는다.
uv run --frozen --group evaluation python -B -m evaluation.kiwi_report output/kiwi-test
```

`--arms AC`로 Kiwi 없는 기본 추출과 Kiwi + LLM만 시험할 수도 있다.
`--no-repeats`, `--no-supplements`는 별도 탐색 실행에만 사용한다.
비교군·데이터·코드·모델 식별 정보·설정이 바뀌면 기존 폴더의 재개를 거부한다. 새 출력 폴더를 사용한다.
개발 단계에서 프롬프트를 수정한 이전 실행 결과는 탐색 기록이며 고정 평가 결과와 합치지 않는다.
실패한 실행도 완료된 **실패 관측**으로 보존한다. 기본 재개는 실패를 몰래 재시도하지 않는다.
현재 재개 단위는 사례/비교군/조건이다. 중단된 한 단위는 임시 DB를 새로 만들어 다시 처리한다.

## 비교군

| 비교군 | 문법 지침 | Kiwi 형태소 단서 | 추가 검증 |
|---|---|---|---|
| A | 없음 | 없음 | 없음 |
| B | 있음 | 없음 | 없음 |
| C | 없음 | 있음 | 없음 |
| D | 있음 | 있음 | 없음 |
| E | 없음 | 없음 | 있음 |
| F | 있음 | 없음 | 있음 |
| G | 없음 | 있음 | 있음 |
| H | 있음 | 있음 | 있음 |
| L | 현재 앱의 기존 처리·검색·답변 경로를 그대로 실행 |

A~H의 스키마·원문/문장 ID·검색·답변 프롬프트는 같다. C-A, D-B, G-E, H-F가 Kiwi 추가 효과의 비교 쌍이다.
검증은 실제 추출 결과와 원문만 받으며 정답을 받지 않는다. E~H는 검증을 한 번 추가하며 그 호출 비용을 포함한다.
A~H의 모델 전송 재시도는 0회다. L은 기존 앱의 재시도·복구 정책을 그대로 사용하므로 별도 시스템 기준선이다.
공통 근거 검사에서 잘못된 인용·참조·달력 값은 실패로 처리한다.
원문에 없는 시간 표현은 해당 시간 필드만 미확정으로 만들고 `validation_issues`에 제안된 값을 보존한다.
보고서의 `ungrounded_times_removed`에 표시하므로 모델이 처음부터 정확히 추출한 것으로 간주하지 않는다.
Kiwi 단서는 형태소·품사·문자 위치이며 의미역이나 관계 정답이 아니다.
문장 분리는 `sentence_boundaries.json`에서 별도 비교한다. 주 실험에서는 Kiwi로 문장 경계를 바꾸지 않는다.

## 데이터와 정답

`data/kiwi_comparison.json`은 미리 작성한 32개 사건 가족과 가족별 3개 형식 변형이다.
24개 개발 사례(8가족), 72개 고정 평가 사례(24가족)이며, 96개 독립 사건이 아니다.
각 범주 4가족 중 첫 가족만 개발용이다. 같은 가족이 개발/평가에 동시에 나타나지 않는다.
형식 변형은 문장 줄바꿈 및 기록 제목 추가다. 새로운 의미를 임의로 추가하지 않는다.
정답 위치는 원문에 대조하고 스냅샷과 데이터 해시를 보존한다.

주 평가 질문은 사례당 직접 회상·관계/시간·정보 부재 각 1개로 총 1,944개다.
고정 평가 범주별 첫 사례는 2회 추가 실행한다. 정정/취소 등은 마지막 기록 추가 전 질문도 별도 실행한다.
실행 순서는 사례별 고정 난수로 비교군을 섞고 모델 호출은 직렬로 처리한다.
`supplement`는 미리 작성한 사용자 보충을 별도 입력 기록으로 추가해 재분석하는 **시뮬레이션**이다.
제품의 사용자 확인 UI나 필드 수정 API를 구현한 것이 아니다. 기본 조건과 점수를 섞지 않는다.
`before`도 별도 스냅샷 DB로 재현한다. 운영 DB의 증분 갱신 성능 시험은 아니다.

데이터 재생성은 `python -m evaluation.build_kiwi_dataset`이다.
고정 평가 실행 후 데이터/별칭/정답을 수정했다면 새 데이터 버전과 새 실행으로 평가해야 한다.

## 평가 의미와 한계

- 근거 범위와 사전에 작성한 서술어 별칭으로 사건을 일대일 대응시킨다. 동의어를 못 알아본 사건은 검토 대기다.
- `event_*_lower_bound`는 이 보수적 자동 대응의 하한 지표다. 완전한 의미 F1이 아니다.
- 주체·시간·상태·부정 범위 등은 정답에 지정된 필드에 한해 비교한다. 분모를 `field_checks`에 표시한다.
- 관계 정답 목록은 명시적으로 지정한 검증 조건이다. 미기재 관계의 참/거짓은 원문 검토가 필요하다.
- L은 스키마가 달라 중첩 연산자·관계 F1을 직접 비교하지 않는다. 원시 기억/관계를 함께 보존한다.
- 질문의 문자열 포함은 보조 검사다. 의미 정확도와 인용이 주장을 뒷받침하는지는 별도 검토한다.
- `review_queue.json`에는 답변, 실행 ID, 결과 해시가 포함된다. reviewer, rationale, verdict를 채운 별도 JSON을
  `python -m evaluation.kiwi_report OUTPUT --reviews REVIEWS.json`으로 적용한다.
- verdict는 correct, partial, incorrect, appropriate_abstention, excessive_abstention 중 하나다.
- 다른 결과의 해시나 중복 리뷰, 검토자·이유 없는 판정은 거부한다. 검토 전 의미 정확도는 null이다.
- 동일 설정을 반복해도 GPU 실행의 비결정성 가능성이 있다. 반복별 원문 결과를 비교한다.
- 비용은 모델 HTTP 호출, 알려진 토큰 수, 토큰 사용량 미제공 건수, 경과 시간으로 보고한다.
  로컬 모델에 외부 API 가격을 임의로 적용하지 않는다.
- 합성 소규모 자료의 결과를 실제 사용자 기록 전체의 정확도로 일반화하지 않는다.

## 결과 파일

- `manifest.json`, `dataset.json`: 설정 동결·예정 실행·원문/정답 스냅샷
- `completed/*.json`: 원자적으로 저장되는 재개 체크포인트와 결과 해시
- `results.jsonl`: 완료 및 실패 결과, 단계별 원시 생성·비용 로그
- `progress.json`: 최근 완료 실행과 전체 진행 수
- `sentence_boundaries.json`, `startup.json`: 문장 분리 비교와 Kiwi 초기화 시간
- `summary.csv`: 방식·범주·조건별 결과와 실패/미실행 분모
- `report.json`, `report.html`: Kiwi 비교 쌍, 반복 안정성, 단계별 상세 결과
- `review_queue.json`: 아직 의미 검토되지 않은 답변

자동 보고서는 검토가 끝나지 않았을 때 채택을 주장하지 않고 보류로 표시한다.
Kiwi를 채택하려면 같은 조건의 비Kiwi 비교군 대비 잘못된 확정·누락·보류·최종 답변·비용을 함께 확인한다.
