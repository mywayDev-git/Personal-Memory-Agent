"""Precommitted source-span gold, independent of generated answers."""

import json
from pathlib import Path

from evaluation.answer_validation import cases as regression_cases


def span(record, text, quote, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(quote, start + 1)
    return {"record": record, "start": start, "end": start + len(quote), "quote": quote}


def gold(records, quotes):
    return [[span(r, records[r]["text"], q)] for r, q in quotes]


def build():
    result = []
    for case in regression_cases():
        case = dict(case, cohort="regression", split="regression")
        records = case["records"]
        chosen = range(len(records))
        if case["id"].startswith("distractor-"):
            chosen = [0]
        quotes = [(i, records[i]["text"]) for i in chosen]
        overrides = {
            "av-negative-0": "서연은 도윤에게 우산을 주지 않았다.",
            "av-cause-2": "하린은 버스를 놓쳐서 걸어갔다.",
            "untrusted-1": "민수는 책을 주지 않았다.",
            "emotion-2": "민수는 시험에 떨어져서 슬펐지만",
        }
        if case["id"] in overrides:
            quotes = [(0, overrides[case["id"]])]
        # Date heading and event are separate requirements; a record ID alone is not gold.
        if case["id"] == "headers-0":
            quotes = [(0, "2026-10-01"), (0, "2026-10-03")]
            case["gold"] = gold(records, quotes) + [
                [span(0, records[0]["text"], "나는 달렸다.", n)] for n in [0, 1]
            ]
        elif case["id"] in {"headers-1", "headers-2"}:
            case["gold"] = gold(records, [(0, "2026-10-01"), (0, "나는 달렸다.")])
        else:
            case["gold"] = gold(records, quotes)
        case["excluded"] = case["id"] == "correction-2"
        case["gold_note"] = "원문 확인에 필요한 문맥. 불명확한 질문에도 미확인의 근거가 포함됨."
        result.append(case)

    groups = ["phrasing", "roles", "scope", "multitopic", "context", "multihop"]
    for category in groups:
        for half, (person, friend, other, food) in enumerate(
            [("민수", "지연", "영희", "김밥"), ("도윤", "하린", "서연", "샌드위치")]
        ):
            target = f"{person}는 시험 공부를 하면서 {food}을 먹었다."
            if food == "샌드위치":
                target = target.replace("샌드위치을", "샌드위치를")
            give = f"{person}가 {friend}에게 책을 줬다."
            reverse = f"{friend}이 {person}에게 책을 줬다."
            negative = f"{person}는 피자를 먹지 않았다."
            plan = f"{person}는 토요일에 수영하기로 했다."
            cancel = f"{person}는 그 수영 계획을 취소했다."
            speech = f'{person}는 "어제 {friend}을 만났어"라고 말했다.'
            # Same visible name does not identify two occupationally distinct people.
            doctor = f"의사 {person}는 카레를 먹었다."
            teacher = f"교사 {person}는 국수를 먹었다."
            sentences = [
                target,
                f"{person}는 여행 중에 우동을 먹었다.",
                f"{other}는 시험 공부를 하면서 사과를 먹었다.",
                give,
                reverse,
                negative,
                plan,
                cancel,
                doctor,
                teacher,
                f"{person}는 수학 시험을 준비했다.",
                f"{friend}은 자전거를 탔다.",
            ]
            padding = " ".join(
                f"이 날의 메모 {n}은 날씨와 풍경에 관한 설명이다." for n in range(25)
            )
            text = "\n\n".join(sentences) + f"\n\n2026-10-10\n{padding}\n{speech}"
            records = [{"text": text, "reference_time": "2026-10-14T12:00:00+09:00"}]
            families = {
                "phrasing": [
                    (f"{person}가 공부하면서 먹은 음식은?", [target], food),
                    (f"{person}가 공부하면서 먹은 음식은", [target], food),
                    (f"공부할 때 {person}는 무엇을 먹었나요?", [target], food),
                    (f"시험 준비 중 {person}의 식사 메뉴를 알려줘.", [target], food),
                ],
                "roles": [
                    (f"{friend}에게 책을 준 사람은?", [give], person),
                    (f"{person}가 준 책을 받은 사람은?", [give], friend),
                    (f"의사 {person}가 먹은 음식은?", [doctor], "카레"),
                    (f"교사 {person}가 먹은 음식은?", [teacher], "국수"),
                ],
                "scope": [
                    (f"{person}가 피자를 먹었어?", [negative], "먹지 않았다"),
                    (f"{person}가 피자를 먹었어", [negative], "먹지 않았다"),
                    (f"{person}가 수영을 실제로 했어?", [plan, cancel], "계획 취소, 실행 미확인"),
                    (f"{person}의 수영 계획은 어떻게 됐어?", [plan, cancel], "취소"),
                ],
                "multitopic": [
                    (f"{person}가 시험 공부하면서 먹은 것은?", [target], food),
                    (f"{person}가 여행 중 먹은 것은?", [sentences[1]], "우동"),
                    (
                        f"{person}와 {other}가 공부하면서 먹은 음식을 각각 알려줘.",
                        [target, sentences[2]],
                        f"{person}: {food}, {other}: 사과",
                    ),
                    (
                        f"{person}가 공부하면서 우동을 먹었어?",
                        [target, sentences[1]],
                        "공부 중 음식과 여행 중 우동 구분; 공부 중 우동 근거 없음",
                    ),
                ],
                "context": [
                    (
                        f"{person}의 발언에서 {friend}을 만난 날짜는?",
                        ["2026-10-10", speech],
                        "2026-10-09; 발언 내용",
                    ),
                    (f"누가 어제 {friend}을 만났다고 말했어?", [speech], person),
                    (
                        f"{person}가 {friend}을 만났다고 말한 날짜는?",
                        ["2026-10-10", speech],
                        "2026-10-10; 사건 날짜와 구분",
                    ),
                    (f"{person}가 {friend}을 만난 시각은 몇 시야?", [speech], "시각 미확인"),
                ],
                "multihop": [
                    (
                        f"{person}의 공부 식사와 여행 식사를 각각 알려줘.",
                        [target, sentences[1]],
                        f"{food}, 우동",
                    ),
                    (
                        f"{person}와 {friend}은 서로 책을 줬어?",
                        [give, reverse],
                        "두 방향의 전달 기록",
                    ),
                    (
                        f"{person}가 공부 후에 여행을 갔다고 확인할 수 있어?",
                        [target, sentences[1]],
                        "두 사건의 선후 관계 미확인",
                    ),
                    (f"{person}가 공부 중 음식을 먹은 이유는?", [target], "원인 미확인"),
                ],
            }
            for j, (question, required, expected) in enumerate(families[category]):
                result.append(
                    {
                        "id": f"qt-{category}-{half * 4 + j}",
                        "cohort": "new48",
                        "category": category,
                        "family": f"{category}-{half}",
                        "split": "development" if half == 0 else "holdout",
                        "records": records,
                        "questions": [{"text": question}],
                        "gold": gold(records, [(0, q) for q in required]),
                        "expected": expected,
                        "forbidden": "이름만으로 인물 병합 금지. 역할·시점·실행·인과를 근거 없이 연결하지 않음.",
                        "excluded": False,
                        "analysis_gold": {
                            "entities": [person] if category != "context" or j != 1 else [friend]
                        },
                    }
                )
    return result


if __name__ == "__main__":
    path = Path("data/query_tree_cases.json")
    path.write_text(json.dumps(build(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
