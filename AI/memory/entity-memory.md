> 서로 다른 기억에서 등장하는 동일한 대상을 하나로 관리하기 위해 고유한 ID를 부여한다
---
|필드|타입|필수|설명|
|---|---|---|---|
|`entity_id`|UUID|필수|대상의 고유 ID|
|`entity_type`|VARCHAR|필수|`person`, `place`, `product`, `organization`, `other` 등|
|`canonical_name`|VARCHAR|필수|대표 이름|
|`description`|TEXT|선택|대상에 대한 설명|
|`status`|VARCHAR|필수|`active`, `merged`, `archived` 등|
|`metadata`|JSONB|선택|추가 속성|
|`created_at`|TIMESTAMPTZ|필수|생성 시각|
|`updated_at`|TIMESTAMPTZ|필수|수정 시각|