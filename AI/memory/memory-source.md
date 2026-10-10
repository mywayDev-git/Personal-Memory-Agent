> 사용자가 입력한 원본 기록을 보존하는 테이블
>
> 핵심 세 모델에는 포함되지 않지만, 기억의 출처와 신뢰성을 관리하기 위해 필요

|필드|타입|필수|설명|
|---|---|---|---|
|`source_id`|UUID|필수|원본 기록 ID|
|`source_type`|VARCHAR|필수|`diary`, `chat`, `note`, `schedule` 등|
|`raw_content`|TEXT|필수|사용자 원문|
|`recorded_at`|TIMESTAMPTZ|필수|시스템에 기록된 시각|
|`metadata`|JSONB|선택|원본별 추가 정보|
|`created_at`|TIMESTAMPTZ|필수|DB 저장 시각|
---
### 관계
- Source 1 : N Memory-unit