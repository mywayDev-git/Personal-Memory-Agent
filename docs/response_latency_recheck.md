# 응답 속도 최적화 재검증과 직접 실행 안내

기존 작업은 `e6cdb1c`로 `codex/chat-memory-integration`에 보존·푸시했습니다.
최적화는 `codex/response-latency-recheck`에서 진행합니다. 모델은
Qwen3-8B-Q4_K_M·BGE-M3-Q8_0, 문맥 한도는 16,384·8,192로 유지합니다.
개인 DB, 일반 모델 서버, 제품의 기본 최적화 설정과 메인 평가 합격선은 바꾸지 않습니다.

## 이전 시도와 이번 변경

| 항목 | 이전 결과 | 이번 구현·검증 |
|---|---|---|
| 중단 기록의 원문 초안 | 20회씩 교차 비교, 35.373→21.951초; 최종 독립 검증 유지 | 현재 기준선에 포함. 새 개선으로 다시 계산하지 않음 |
| 짧은 인물·직업 원문 초안 | 이미 `direct_statement`에 구현 | 중복 추가하지 않음. 현재 의미·인용 회귀 검사 유지 |
| 토큰 계산 캐시 | 구성 요소 5회, 적중 0; 29.449→29.462초 | 같은 구현을 별도 옵션으로 재검증 |
| 판정 배치 8개 | 구성 요소 5회, 호출 3→2지만 29.449→30.243초 | 호출 감소와 최종 응답 시간 감소를 분리해 재검증 |
| 관련성 판정 재사용 | 구현됨, 주요 비교에서 적중 0 | 문맥 해석 생략과 독립된 옵션으로 분리 |
| 명확한 인물의 문맥 해석 생략 | 중단된 실험의 후속 질문 그룹에서만 예비 개선 | 별도 옵션으로 분리, 의미 검증과 후속 질문 검사 유지 |
| 추가 검색 판단 입력 축소 | 단순 질문에서 빨랐으나 실행 순서·검색 분기에 영향; 미채택 | 제품 경로에 비활성화 옵션으로 연결. 원문·의미 주의사항 보존 |
| 프리픽스 재사용 | 별도 효과 비교 없음 | 요청별 명시적 켜기/끄기, 재사용 토큰·입력 처리 시간 계측 |
| 표시 간소화 | 단순 질문 예비 비교만 있음 | 기존 옵션을 단독 비교; 독립 사실 검증 유지 |
| 저장과 질문 순서 | 질문 우선 정책은 이미 존재 | 저장 대기 시 질문 최대 2건 뒤 저장 차례를 주는 선택 옵션 |

실제 직렬화 단위는 `model_slot` 전체입니다. 이미 실행 중인 추출·질문을 중간에
끊거나 개별 HTTP 호출을 다른 작업과 섞지 않습니다. 저장은 다음 슬롯에서 진행합니다.
일반 `concurrent` 사례 한 번만으로 공정 스케줄링 효과를 입증하지 않습니다.
대기 순서·취소·정리 동작은 오프라인 동시성 검사로 확인하고, 지속 부하 지연은 별도 측정 대상입니다.

## 안전한 실행

저장소 루트의 PowerShell에서 실행합니다. **계획 조회는 모델·서버·출력 파일을 만들지 않습니다.**

```powershell
.\.venv\Scripts\python.exe -m evaluation.latency_recheck
```

이 명령은 공식 `evaluation.main_suite`와 별개인 성능 실험입니다.
공식 메인·모델 비교·확장·최종 평가를 실행하지 않으며, 관제실 조회에도 연결하지 않습니다.
공식 평가는 [메인 테스트 규칙](main_test_plan.md)에 따라 별도 명시 요청 또는
인증된 테스트 실행 버튼에서만 시작합니다.

다음은 사용자가 **실제로 실행할 때** 사용하는 명령입니다. 후보별 준비 실행 1회 후
현재 기준선과 후보를 5회씩 교차 비교합니다. 기본 CPU 실행은 오래 걸릴 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m evaluation.latency_recheck --execute --name screen-user-001
```

작은 범위로 시작하는 예시:

```powershell
.\.venv\Scripts\python.exe -m evaluation.latency_recheck --execute --name token-user-001 --candidates token_cache --cases simple_search
.\.venv\Scripts\python.exe -m evaluation.latency_recheck --execute --name batch-user-001 --candidates batch8 --cases selection_batch long_evidence followup
.\.venv\Scripts\python.exe -m evaluation.latency_recheck --execute --name prefix-user-001 --candidates prefix_off prefix_on --cases simple_search simple_answer long_evidence
.\.venv\Scripts\python.exe -m evaluation.latency_recheck --execute --name planning-user-001 --candidates planning_compact --cases simple_answer stopped plan identity followup multi_hop additional_search
```

GPU는 `--placement gpu`를 추가합니다. 실행기는 여유 VRAM을 확인하며,
부족하면 실패하고 **기존 서버를 종료하거나 재사용하지 않습니다.** CPU와 GPU 결과를 합치지 않습니다.
전용 포트는 18581·18582이며 `--port`로 변경할 수 있습니다. 사용 중인 포트는 실패 처리합니다.
모델은 기존 로컬 파일만 사용하며 다운로드하지 않습니다.

별도 CPU 서버는 이번에 시작을 확인한 스레드 4·임베딩 배치 4096을 기본으로 사용합니다.
GPU 기본은 스레드 자동·임베딩 배치 8192입니다. `--threads`, `--embedding-batch`로 명시할 수 있고
양쪽 비교에 같은 값을 적용합니다. 이는 평가 서버 설정이며 제품 설정을 바꾸지 않습니다.
입력이 배치를 초과하면 실패로 남기며 원문을 잘라 통과시키지 않습니다.
기억 답변 실험은 명시적 기억 모드이며, 자동 모드 전체 UX의 성능을 대신하지 않습니다.

후보별 품질 검사 후, 명시적으로 선택한 조합을 20회씩 측정하는 예시:

```powershell
.\.venv\Scripts\python.exe -m evaluation.latency_recheck --execute --stage final --name final-user-001 --combine --candidates planning_compact context_shortcut
```

위 후보가 통과했다고 가정하는 명령이 아닙니다. 해당 조합의 선별 결과와 의미 검토를 먼저 확인해야 합니다.
`prefix_off`와 `prefix_on`은 함께 조합할 수 없습니다.
중단은 Ctrl+C입니다. 재실행은 **새 이름**을 사용합니다. 기존 결과는 덮어쓰지 않습니다.
하위 실행기는 자신이 시작한 서버만 정리합니다. 중단 시 기존 결과와 미실행 상태를 보존합니다.

## 기록 열람과 판정

결과 위치는 `.local/latency-recheck/<실행 이름>/`입니다.

| 파일 | 확인할 내용 |
|---|---|
| `report.md` | 비교 표와 실제 재현 명령 |
| `verification.json` | 후보별 완료 여부·결과 해시·자동 품질 선별·성능 기준 |
| `<후보>/results.json` | 표본별 시간, 모델 호출, 캐시 적중, 검색 반복, RAM·VRAM, 소스·실행 파일 해시 |
| `<후보>/quality/*.json` | 합성 질문 응답·전체 근거·인용을 직접 대조할 자료 |

질문·원문·답변은 합성 품질 자료에만 저장합니다. 성능 메타데이터는 수치 허용 목록만 사용합니다.
성능 응답 반환 시 타이머를 멈추며 답변의 독립 검증·최종 저장은 포함하고,
이후 정답 채점과 평가 파일 저장은 제외합니다. 검색 결과 세션 저장·HTTP·브라우저 렌더링은 별도입니다.
후속 질문은 같은 검증된 이전 대화를 복제합니다.

프리픽스는 매 요청 전에 **전용 실험 서버의 슬롯만** 지워 후보 간 상태를 분리합니다.
이 비교는 요청 내부 단계 간 재사용이며, 장기 운영의 요청 간 캐시 적중률을 입증하지 않습니다.
서버가 슬롯 삭제 API를 지원하지 않으면 비교를 실패 처리하고 캐시 효과를 추정하지 않습니다.

현재 기준선은 중단 원문 초안 켜기·배치 4·검토된 표시·추가 캐시 끄기입니다.
과거 평가기의 `baseline`은 중단 초안을 끄므로 이번 비교에는 `current`와 `candidate`를 사용합니다.

자동 정답 검사는 후보 선별용입니다. 단어·인용 위치 일치만으로 의미 정확성을 승인하지 않습니다.
보고서의 의미 검토는 `PENDING_REVIEW`, 기본값 변경 허용은 `false`로 남습니다.
동명이인·제외 대상, 부정·중단, 날짜 미상, 계획과 실행, 복합 질문의 완전성, 과도한 거절을 직접 대조합니다.
실행 실패·품질 실패·검토 대기·미실행을 구분합니다.

정식 채택은 새 다국어 90문항의 질문별 P@8·R@8 비하락, 핵심 사례 전수 통과,
전체 Python·화면 회귀 검사, 답변 문항별 중앙값 비율의 동일 가중 기하평균 20% 이상 감소,
문항별 P95·실패율 비악화를 모두 요구합니다. 검색·판정 구성 요소는 답변 평균에 포함하지 않습니다.
공정 스케줄링은 저장 성공률·완료 P95도 별도 확인해야 하므로 기존 단일 동시성 사례만으로 채택하지 않습니다.
지연 선별 기준 통과만으로 제품 설정을 자동 변경하지 않습니다.

## 옵션과 복구

모든 새 옵션은 기본 비활성화이며, 프리픽스 기본값은 서버 동작을 그대로 따릅니다.

| 환경 변수 | 효과 |
|---|---|
| `PMA_SELECTION_REUSE=1` | 요청 내부 관련성 판정 캐시만 켬 |
| `PMA_CONTEXT_SHORTCUT=1` | 명확한 원문 기반 인물 문맥 해석 생략만 켬 |
| `PMA_PROMPT_CACHE=0` 또는 `1` | 모델 요청의 프리픽스 재사용 정책 지정 |
| `PMA_COMPACT_SEARCH_PLANNING=1` | 추가 검색 판단의 중복 입력 축소 |
| `PMA_FAIR_MODEL_SCHEDULING=1` | 저장 대기 중 질문 연속 처리 제한 |

기존 `PMA_REQUEST_REUSE` 호환성을 유지하며 새 캐시·문맥 옵션이 명시되면 해당 부분만 우선합니다.
복구는 새 환경 변수를 제거하고 재시작하면 됩니다. DB 변경·재색인이 필요하지 않습니다.
기존 토큰 캐시·배치·표시 옵션은 그대로 유지합니다.

오프라인 재검사(실제 모델 호출 없음):

```powershell
$env:TEMP = (Resolve-Path .local).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.local/pytest-recheck-user --junitxml=.local/recheck-user.xml
node tests/evaluation_execution_ui.mjs
node tests/evaluation_refresh_ui.mjs
```

이전 작업 보존 시 재검사 결과는 Python 781개와 화면 검사 8종 통과입니다.
기본 시스템 임시 폴더 권한 오류가 있어 위와 같이 저장소 내부 임시 경로를 사용했습니다.
최적화 추가 후 결과와 실제 실행한 범위는 별도 검증 기록에 남깁니다.
