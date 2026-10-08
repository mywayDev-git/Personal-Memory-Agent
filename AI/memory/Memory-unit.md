# memory unit v1

> Memory Unit은 하나의 독립적인 기억 의미를 표현한다.

> 기억의 대상(Target), 상태(State), 관계(Relationship), 사건(Event), 또는 시간적 발생이 독립적이면 Memory Unit을 분리한다.

---
- 기본 원칙은 "기억의 대상(Target)이나 시간적 사건이 독립적이면 Memory Unit을 분리한다"로 잡는다. 다만 무조건 문장마다 하나씩 만드는 게 아니라, 하나의 Memory Unit이 하나의 독립적인 사실/관계/상태를 표현하도록 하는 게 핵심
---

## 예시

```json
{
  "id": "mem_01JXYZ",

  "type": "preference",

  "content": "사용자는 매운 음식을 좋아한다",

  "importance": 0.85,
  "confidence": 0.95,

  "created_at": "2026-10-08T14:30:00+09:00",
  "occurred_at": null,

  "source_id": "msg_01JABC",
  "source_type": "conversation",

  "entities": [
    {
      "type": "food",
      "name": "매운 음식"
    }
  ],

  "keywords": [
    "매운 음식",
    "음식",
    "선호"
  ],

  "related_memory_ids": []
  
  "status": "active"
}
```

### Memory Unit Schema

| 분류             | 필드                   | 타입            |  필수 | 설명                               | 예시                     |
| -------------- | -------------------- | ------------- | :-: | -------------------------------- | ---------------------- |
| **Identity**   | `id`                 | String        |  ✅  | Memory Unit 고유 ID                | `mem_01JXYZ`           |
|                | `version`            | Integer       |  ✅  | 기억의 수정 버전                        | `1`                    |
| **Content**    | `type`               | Enum          |  ✅  | 기억의 종류                           | `preference`           |
|                | `content`            | String        |  ✅  | 기억의 핵심 내용                        | `사용자는 매운 음식을 좋아한다`     |
| **Importance** | `importance`         | Float         |  ✅  | 장기 기억으로서의 중요도                    | `0.85`                 |
|                | `confidence`         | Float         |  ✅  | 원본으로부터 해당 기억을 올바르게 추출했다고 판단하는 정도 | `0.95`                 |
|                | `status`             | Enum          |  ✅  | 현재 기억의 상태                        | `active`               |
| **Temporal**   | `created_at`         | DateTime      |  ✅  | Memory Unit이 생성된 시간              | `2026-10-08T14:30:00`  |
|                | `occurred_at`        | DateTime      |  ❌  | 실제 사건·상태가 발생한 시간                 | `2026-10-01T18:00:00`  |
| **Source**     | `source_id`          | String        |  ✅  | 기억을 생성한 원본 데이터 ID                | `msg_01JABC`           |
|                | `source_type`        | Enum          |  ✅  | 원본 데이터의 종류                       | `conversation`         |
| **Entity**     | `entities`           | Array         |  ❌  | 기억에 등장하는 사람·장소·사물 등              | `매운 음식`                |
| **Search**     | `keywords`           | Array[String] |  ❌  | 검색에 활용할 핵심 키워드                   | `["매운 음식","선호"]`       |
| **Relation**   | `related_memory_ids` | Array[String] |  ❌  | 관련된 다른 Memory Unit ID            | `["mem_02", "mem_03"]` |


### `type` 종류
| Type         | 의미              | 예시                |
| ------------ | --------------- | ----------------- |
| `profile`    | 사용자 기본 정보       | 컴퓨터공학과 학생         |
| `preference` | 취향·선호           | 매운 음식을 좋아함        |
| `person`     | 사람과 관련된 기억      | 민수는 대학 동기         |
| `event`      | 발생한 사건          | 지난주 부산 여행         |
| `experience` | 경험 및 경험에서 얻은 정보 | 제주도 여행이 힘들었음      |
| `plan`       | 미래 계획           | 다음 달 부산에 갈 예정     |
| `decision`   | 결정·선택           | 다음 학기에 휴학하지 않기로 함 |
| `fact`       | 기타 중요한 사실       | 노트북을 2025년에 구매    |
### `status` 종류
| Status        | 의미                 | 예시            |
| ------------- | ------------------ | ------------- |
| `active`      | 현재 유효한 기억          | 부산 여행 예정      |
| `superseded`  | 새로운 기억으로 대체됨       | 여행 예정 → 여행 취소 |
| `invalidated` | 잘못된 기억으로 판정됨       | 잘못 추출된 정보     |
| `archived`    | 더 이상 적극적으로 사용하지 않음 | 오래된 일회성 기억    |

### 분리 규칙
| 상황                  |  분리 여부 | 예시                        |
| ------------------- | :----: | ------------------------- |
| Target이 다름          |    ✅   | 민수는 취업 고민 / 나는 대학원 고민     |
| 사건이 다름              |    ✅   | 부산 여행 / 비행기표 예약           |
| 상태가 다름              |    ✅   | 커피를 싫어함 / 운동을 좋아함         |
| 시간적으로 독립된 사건        |    ✅   | 작년 제주 여행 / 올해 부산 여행       |
| 동일 사건의 여러 인물        |    ❌   | 나와 민수가 부산 여행을 감           |
| 동일 사건의 여러 장소·물건     |    ❌   | 부산에서 호텔에 묵음               |
| 한 문장에 독립적인 기억 여러 개  |    ✅   | 각각 별도의 Unit               |
| 단순히 Entity가 여러 개 존재 |    ❌   | Entity 수만으로 분리하지 않음       |
| 독립적으로 검색할 필요가 있는 정보 | 가능하면 ✅ | 서로 다른 기억으로 활용될 가능성이 높은 경우 |
