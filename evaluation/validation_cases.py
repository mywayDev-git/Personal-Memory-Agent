"""Deterministic, source-disjoint diagnostic fixtures (not a population benchmark)."""

import argparse
import copy
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from evaluation.query_tree_run import write

CATEGORIES = ("roles", "polarity", "time", "correction", "conditions", "resolution")
NAMES = "서연 도윤 하린 지연 민수 수아 지호 예린 유진 태호".split()
FAMILIES = "김 이 박 최 정 강".split()
OBJECTS = "우산 책 가방 열쇠 노트 시계 모자 지도 사진 지갑".split()
PLACES = "도서관 공원 카페 학교 병원 서점 수영장 극장 우체국 정류장".split()
DATA = Path("data/memory_validation_cases.json")


def particles(text):
    """Correct template particles without rewriting quotations or predicates."""
    words = [family + name for family in FAMILIES for name in NAMES] + OBJECTS
    for word in words:
        final = (ord(word[-1]) - 0xAC00) % 28 != 0
        for consonant, vowel in (("이", "가"), ("은", "는"), ("을", "를")):
            text = re.sub(
                re.escape(word) + consonant + r"(?=[\s?.])",
                word + (consonant if final else vowel),
                text,
            )
    return text


def ref(value, kind="entity"):
    return dict(kind=kind, value=value, value_type="string")


def fact(text, actor, predicate, obj, recipient=None, day=None, denied=False):
    text = particles(text)
    return dict(
        text=text,
        memory=dict(
            local_id="pending",
            content=text,
            memory_type="event",
            subject=ref(actor),
            predicate=predicate,
            object=ref(obj, "literal"),
            target=None,
            time=dict(
                raw=day,
                start=day,
                end=day,
                precision="day" if day else "unknown",
                certainty="explicit" if day else "uncertain",
            ),
            assertion_polarity="negated" if denied else "affirmed",
            polarity="neutral",
            content_certainty="explicit",
            evidence=[],
        ),
    )


def build():
    cases = []
    for ci, category in enumerate(CATEGORIES):
        for i in range(10):
            group = f"mv-{category}-{i:02}"
            a, b = FAMILIES[ci] + NAMES[i], FAMILIES[(ci + 1) % 6] + NAMES[(i + 3) % 10]
            obj, place = OBJECTS[i], PLACES[i]
            d = date(2026, 5, 1) + timedelta(days=ci * 12 + i)
            day, previous, earlier = str(d), str(d - timedelta(days=1)), str(d - timedelta(days=2))
            specs = []
            records_facts = [[]]
            if category == "roles":
                records_facts[0] = [
                    fact(
                        f"{earlier}에 {a}이 {b}에게 {obj}을 주었다.", a, "주었다", obj, b, earlier
                    ),
                    fact(
                        f"{day}에 {b}이 {a}에게 {obj}을 돌려주었다.", b, "돌려주었다", obj, a, day
                    ),
                ]
                specs = [
                    (
                        f"{earlier}에 {a}이 {obj}을 준 상대는 누구야?",
                        b,
                        [(0, 0)],
                        "recipient",
                        None,
                    ),
                    (f"{day}에 {a}에게 {obj}을 돌려준 사람은 누구야?", b, [(0, 1)], "actor", None),
                ]
            elif category == "polarity":
                variants = [
                    (
                        f"{a}은 {obj}을 {b}에게 주지 않았다.",
                        "주지 않았다",
                        True,
                        "전달하지 않았다",
                        "answerable",
                    ),
                    (
                        f"{a}은 {obj}을 {b}에게 주기로 했다. 아직 전달하지 않았다.",
                        "주기로 했다",
                        False,
                        "전달할 계획이며 아직 전달하지 않았다",
                        "answerable",
                    ),
                    (
                        f"{a}은 {b}이 {obj}을 받았을 것이라고 추측했다.",
                        "추측했다",
                        False,
                        "추측만 있으며 실제 수령 여부는 미확인",
                        "unknown",
                    ),
                    (f"{a}은 {obj}을 {b}에게 주었다.", "주었다", False, "전달했다", "answerable"),
                    (
                        f"{a}은 {obj}을 {b}에게 주기로 하지 않았다.",
                        "주기로 하지 않았다",
                        True,
                        "전달 결정을 하지 않았으며 실제 전달 여부는 미확인",
                        "unknown",
                    ),
                ]
                sentence, predicate, denied, expected, state = variants[i % 5]
                records_facts[0] = [fact(sentence, a, predicate, obj, b, denied=denied)]
                specs = [
                    (
                        f"{a}이 {b}에게 {obj}을 실제로 전달했어?",
                        expected,
                        [(0, 0)],
                        "execution",
                        state,
                    ),
                    (
                        f"{a}이 {b}에게 {obj}을 전달하지 않았다는 기록이 있어?",
                        expected,
                        [(0, 0)],
                        "claim",
                        None,
                    ),
                ]
            elif category == "time":
                records_facts[0] = [
                    fact(
                        f'{day}에 {a}은 "어제 {place}에서 {b}을 만났어"라고 말했다.',
                        a,
                        "말했다",
                        f"어제 {b}을 만났다는 발언",
                        day=day,
                    )
                ]
                specs = [
                    (f"{a}의 발언에서 {b}을 만난 날짜는?", previous, [(0, 0)], "event_date", None),
                    (f"{a}이 {b}을 만났다고 말한 날짜는?", day, [(0, 0)], "utterance_date", None),
                ]
            elif category == "correction":
                records_facts[0] = [
                    fact(
                        f"{a}은 {b}을 만난 날짜가 {earlier}이라고 기록했다.", a, "기록했다", earlier
                    ),
                    fact(
                        f"{a}은 앞선 만남 날짜를 정정했다. 실제로 {b}을 만난 날짜는 {day}이다.",
                        a,
                        "정정했다",
                        day,
                    ),
                    fact(f"{a}은 예전에 부산에 살았지만 지금은 전주에 산다.", a, "산다", "전주"),
                ]
                specs = [
                    (
                        f"정정된 기록에 따르면 {a}이 {b}을 만난 날짜는?",
                        day,
                        [(0, 1)],
                        "event_date",
                        None,
                    ),
                    (f"{a}은 지금 어디에 살아?", "전주", [(0, 2)], "current_location", None),
                ]
            elif category == "conditions":
                records_facts[0] = [
                    fact(
                        f"{day}에 {a}은 {place}에서 {b}에게 빨간 {obj}을 주었다.",
                        a,
                        "주었다",
                        f"빨간 {obj}",
                        b,
                        day,
                    ),
                    fact(
                        f"{day}에 {a}은 {place}에서 {b}에게 파란 {obj}을 받았다.",
                        a,
                        "받았다",
                        f"파란 {obj}",
                        b,
                        day,
                    ),
                    fact(
                        f"{earlier}에 {a}은 집에서 {b}에게 빨간 {obj}을 주었다.",
                        a,
                        "주었다",
                        f"빨간 {obj}",
                        b,
                        earlier,
                    ),
                ]
                specs = [
                    (
                        f"{day}에 {a}이 {place}에서 {b}에게 준 {obj}은 무슨 색이야?",
                        "빨간색",
                        [(0, 0)],
                        "color",
                        None,
                    ),
                    (
                        f"{day}에 {a}이 {place}에서 {b}에게 받은 {obj}은 무슨 색이야?",
                        "파란색",
                        [(0, 1)],
                        "color",
                        None,
                    ),
                ]
            else:
                mode = i % 5
                first = fact(
                    f"{a}은 {obj}을 누군가에게 맡겼다. 상대의 이름은 적지 않았다.", a, "맡겼다", obj
                )
                later = fact(f"앞서 {a}이 {obj}을 맡긴 상대는 {b}이었다.", a, "맡겼다", obj, b)
                if mode in (0, 1):
                    records_facts = [[first, later]] if mode == 0 else [[first], [later]]
                    support = [(0, 0), (0, 1)] if mode == 0 else [(0, 0), (1, 0)]
                    expected, state = b, "answerable"
                elif mode == 2:
                    records_facts = [[first]]
                    support, expected, state = [(0, 0)], "상대 이름 미확인", "unknown"
                elif mode == 3:
                    other = FAMILIES[(ci + 2) % 6] + NAMES[(i + 6) % 10]
                    records_facts = [
                        [first],
                        [
                            later,
                            fact(
                                f"다른 기록에는 같은 {obj}을 맡긴 상대가 {other}이라고 되어 있다. 어느 기록이 맞는지는 미확인이다.",
                                a,
                                "기록되어 있다",
                                obj,
                                other,
                            ),
                        ],
                    ]
                    support, expected, state = (
                        [(0, 0), (1, 0), (1, 1)],
                        "상대 이름 상충, 확인 필요",
                        "conflicting",
                    )
                else:
                    records_facts = [
                        [first],
                        [
                            fact(
                                f"{a}은 다른 날 {b}에게 책을 빌렸다. 앞서 맡긴 {obj}의 상대는 여전히 모른다.",
                                a,
                                "빌렸다",
                                "책",
                                b,
                            )
                        ],
                    ]
                    support, expected, state = [(0, 0), (1, 0)], "상대 이름 미확인", "unknown"
                specs = [
                    (f"{a}이 {obj}을 맡긴 상대는 누구야?", expected, support, "recipient", state),
                    (
                        f"{a}이 {obj}을 맡긴 상대의 이름을 확정할 수 있어?",
                        expected,
                        support,
                        "certainty",
                        state,
                    ),
                ]
            # More than eight memories per group; distractors share people and objects.
            for j in range(10):
                noise = fact(
                    f"{str(d - timedelta(days=j + 10))}에 {a}은 {PLACES[(i + j + 1) % 10]}에서 "
                    f"{b}과 {OBJECTS[(i + j + 1) % 10]}의 보관 방법을 의논했다.",
                    a,
                    "의논했다",
                    OBJECTS[(i + j + 1) % 10],
                    b,
                )
                records_facts[0].append(noise)
            records, references, spans = [], [], {}
            for ri, facts in enumerate(records_facts):
                text = "\n".join(f["text"] for f in facts)
                records.append(dict(text=text, reference_time="2026-10-14T12:00:00+09:00"))
                memories, position = [], 0
                for fi, f in enumerate(facts):
                    span = dict(
                        record=ri, start=position, end=position + len(f["text"]), quote=f["text"]
                    )
                    spans[ri, fi] = span
                    memory = copy.deepcopy(f["memory"])
                    evidence = {k: span[k] for k in ("start", "end", "quote")}
                    memory.update(
                        local_id=f"m{fi + 1}",
                        evidence=[dict(quote=f["text"])],
                        _evidence_spans=[evidence],
                    )
                    memories.append(memory)
                    position = span["end"] + 1
                references.append(memories)
            for qi, (question, expected, support, requested, state) in enumerate(specs):
                question = particles(question)
                fields = dict(requested=requested, actor=a)
                if category == "roles":
                    fields.update(
                        target=obj,
                        time=earlier if qi == 0 else day,
                        action="준" if qi == 0 else "돌려준",
                    )
                    if qi == 1:
                        fields.pop("actor")
                        fields["recipient"] = a
                elif category == "polarity":
                    fields.update(
                        recipient=b,
                        target=obj,
                        action="전달",
                        scope="실제로" if qi == 0 else "전달하지 않았다는",
                    )
                elif category == "time":
                    fields.update(target=b, action="만난" if qi == 0 else "말한")
                    if qi == 0:
                        fields["scope"] = "발언"
                elif category == "correction":
                    fields.update(
                        action="만난" if qi == 0 else "살아",
                        scope="정정된 기록" if qi == 0 else "지금",
                    )
                    if qi == 0:
                        fields["target"] = b
                elif category == "conditions":
                    fields.update(
                        actor=a if qi == 0 else b,
                        recipient=b if qi == 0 else a,
                        target=obj,
                        time=day,
                        scope=place,
                        action="준" if qi == 0 else "받은",
                    )
                else:
                    fields.update(target=obj, action="맡긴")
                constraints = [dict(field=k, value=v) for k, v in fields.items()]
                cases.append(
                    dict(
                        id=f"{group}-q{qi + 1}",
                        group=group,
                        category=category,
                        cohort="validation-v1",
                        split="development" if i < 5 else "holdout",
                        excluded=False,
                        records=copy.deepcopy(records),
                        questions=[dict(text=question)],
                        expected=expected,
                        gold=[[spans[s]] for s in support],
                        reference_memories=copy.deepcopy(references),
                        validation=dict(
                            answerability=state or "answerable",
                            requested=requested,
                            mandatory=category in {"roles", "polarity", "time", "correction"},
                            constraints=constraints,
                            semantic_review_required=True,
                            time_basis="utterance"
                            if requested == "utterance_date"
                            else "event"
                            if requested == "event_date"
                            else None,
                            expected_reason="conflict"
                            if state == "conflicting"
                            else "missing"
                            if state == "unknown"
                            else None,
                            clarification=f"{a}이 {obj}을 맡긴 상대를 확인해 줄 수 있나요?"
                            if state in {"unknown", "conflicting"} and category == "resolution"
                            else None,
                            reference_status="fixture_author_reviewed_not_independent",
                        ),
                    )
                )
    return cases


def validate(cases):
    assert len(cases) == 120 and len({c["id"] for c in cases}) == 120
    assert Counter(c["category"] for c in cases) == Counter({c: 20 for c in CATEGORIES})
    groups = {}
    for c in cases:
        groups.setdefault(c["group"], []).append(c)
        for group in c["gold"]:
            for s in group:
                assert c["records"][s["record"]]["text"][s["start"] : s["end"]] == s["quote"]
        for r, memories in zip(c["records"], c["reference_memories"], strict=True):
            for m in memories:
                for s in m["_evidence_spans"]:
                    assert r["text"][s["start"] : s["end"]] == s["quote"]
    assert len(groups) == 60
    assert all(len(v) == 2 and len({c["split"] for c in v}) == 1 for v in groups.values())
    dev = {r["text"] for c in cases if c["split"] == "development" for r in c["records"]}
    held = {r["text"] for c in cases if c["split"] == "holdout" for r in c["records"]}
    assert not dev & held


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, default=DATA)
    args = parser.parse_args()
    values = build()
    validate(values)
    write(args.output, values)
    print(f"Wrote {len(values)} questions / 60 groups to {args.output}")
