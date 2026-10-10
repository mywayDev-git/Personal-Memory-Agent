# Data Schema 정의

![alt text](image.png)


### `Source` — 원본 기록

- 사용자가 입력한 원본 기록을 보존하는 테이블
- 핵심 세 모델에는 포함되지 않지만 기억의 출처와 신뢰성을 관리하기 위해 필요

|필드|타입|필수|설명|
|---|---|---|---|
|`source_id`|UUID|필수|원본 기록 ID|
|`source_type`|VARCHAR|필수|`diary`, `chat`, `note`, `schedule` 등|
|`raw_content`|TEXT|필수|사용자 원문|
|`recorded_at`|TIMESTAMPTZ|필수|시스템에 기록된 시각|
|`metadata`|JSONB|선택|원본별 추가 정보|
|`created_at`|TIMESTAMPTZ|필수|DB 저장 시각|

원본 기록 하나에서 여러 Memory Unit이 생성될 수 있어. 따라서 `Source 1 : N MemoryUnit` 관계로 설계할게.

### `Entity` — 대상 식별

Entity는 사람, 장소, 제품, 조직 등 반복해서 등장하는 대상을 관리함

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

### `MemoryUnit` — 개별 기억

|필드|타입|필수|설명|
|---|---|---|---|
|`memory_id`|UUID|필수|기억 ID|
|`source_id`|UUID|선택|원본 기록 ID|
|`memory_type`|VARCHAR|필수|`fact`, `event`, `preference`, `plan`, `decision`, `experience` 등|
|`content`|TEXT|필수|자연어로 표현한 기억|
|`subject_entity_id`|UUID|선택|기억의 주체|
|`predicate`|VARCHAR|선택|주체와 대상 사이의 관계 또는 행위|
|`object_entity_id`|UUID|선택|대상이 Entity인 경우 해당 ID|
|`object_value`|JSONB|선택|대상이 문자열·숫자·날짜 등 값인 경우|
|`target_entity_id`|UUID|선택|행위의 상대방 또는 수신자|
|`occurred_start`|TIMESTAMPTZ|선택|사건 발생 시작 시각|
|`occurred_end`|TIMESTAMPTZ|선택|사건 발생 종료 시각|
|`time_precision`|VARCHAR|필수|시간 정보의 정밀도|
|`valid_from`|TIMESTAMPTZ|선택|사실 또는 상태가 유효해진 시각|
|`valid_until`|TIMESTAMPTZ|선택|사실 또는 상태의 유효 종료 시각|
|`importance`|SMALLINT|필수|중요도, 1~5|
|`confidence`|NUMERIC(4,3)|필수|추출 결과에 대한 신뢰도, 0~1|
|`status`|VARCHAR|필수|`active`, `superseded`, `invalidated`, `archived` 등|
|`metadata`|JSONB|선택|추가 정보|
|`created_at`|TIMESTAMPTZ|필수|기억 생성 시각|
|`updated_at`|TIMESTAMPTZ|필수|마지막 수정 시각|

`subject_entity_id`, `object_entity_id` 등은 Entity와 연결되는 외래 키
아직 대상의 동일성을 확정하지 못했거나 특정 Entity가 필요하지 않은 기억도 있을 수 있으므로, 일부는 NULL을 허용해.

`object_entity_id`와 `object_value`는 하나의 기억에서 동시에 채우지 않도록 제약을 두는 게 좋아. 예를 들어 "민수가 맥북을 추천했다"에서는 대상이 Entity인 맥북을 참조하고, "나는 매운 음식을 좋아한다"에서는 대상이 단순 값이나 범주라면 `object_value`를 사용할 수 있어.

또한 `time_precision`은 다음 값을 고려할 수 있어.

- `exact`: 정확한 시각
    
- `day`: 날짜만 확인됨
    
- `month`: 월 단위
    
- `year`: 연도만 확인됨
    
- `range`: 기간으로 표현됨
    
- `unknown`: 시점을 알 수 없음
    

날짜만 알고 있는 사건에 임의로 자정 시각을 부여해 정확한 시각인 것처럼 취급하지 않도록 하기 위한 설계야.

### 3-4. `MemoryRelation` — 기억 간 관계

MemoryRelation은 서로 다른 기억이 어떻게 연결되는지를 나타내.

|필드|타입|필수|설명|
|---|---|---|---|
|`relation_id`|UUID|필수|관계 ID|
|`source_memory_id`|UUID|필수|관계의 시작 기억|
|`target_memory_id`|UUID|필수|관계의 도착 기억|
|`relation_category`|VARCHAR|필수|`semantic`, `temporal`|
|`relation_type`|VARCHAR|필수|구체적인 관계 종류|
|`confidence`|NUMERIC(4,3)|필수|관계 추출 신뢰도|
|`evidence`|TEXT|선택|관계를 판단한 근거|
|`created_at`|TIMESTAMPTZ|필수|생성 시각|

추천 관계 유형은 아래와 같아.

|분류|관계 유형 예시|의미|
|---|---|---|
|의미|`related_to`|관련된 기억|
|의미|`caused_by`|원인과 결과 관계|
|의미|`supports`|다른 기억을 뒷받침함|
|의미|`contradicts`|서로 모순됨|
|의미|`supersedes`|이전 기억을 대체함|
|시간|`before`|시간상 먼저 발생|
|시간|`after`|시간상 나중에 발생|
|시간|`overlaps`|사건 기간이 겹침|
|시간|`during`|다른 사건의 기간 안에 발생|

관계의 방향도 중요해. `A caused_by B`는 A가 B 때문에 발생했다는 의미고, `A before B`는 A가 B보다 먼저 발생했다는 의미야. 관계 유형을 명확히 정의해야 검색 과정에서 의미가 뒤집히지 않아.

참고로 `related_to`는 방향성이 중요하지 않을 수 있지만, `caused_by`, `before`, `supersedes`는 방향성이 중요해. 양방향 관계를 무조건 두 행으로 저장하기보다는 한쪽 방향만 저장하고 조회할 때 반대 방향을 해석하는 편이 중복을 줄이기 좋아.