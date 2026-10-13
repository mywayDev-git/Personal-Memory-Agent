"""Grounded, versioned projections of v4 memories. Never replaces source memories.

Rules only canonicalize explicit text/roles; uncertain identity and links stay inferred.
Unrecognized predicates remain `other` and use the verified model path.
"""

import calendar
import hashlib
import json
import re
from datetime import date, timedelta
from decimal import Decimal

from scripts.memory_agent.provenance import normalize_time, sentences

FACT_VERSION = 4
RELATIONS = (
    "desire",
    "give",
    "receive",
    "prefer",
    "run",
    "visit",
    "eat",
    "conflict",
    "cancel",
    "other",
)
PATTERNS = {
    "desire": r"받고\s*싶|(?:^|\s)원(?:하|했|한)|갖고\s*싶|희망",
    "give": r"선물했|선물한|선물하|줬|주었|주다|(?<![가-힣])준(?:\s|거|건|것|선물)|주기로|전달했",
    "receive": r"받았|받은|받다",
    "prefer": r"좋아|선호|싫어",
    "run": r"달리|달렸|달린|달릴|달렸다|달려|달림|뛰었|뛰기|런닝|러닝",
    "visit": r"방문|갔다|갔어|가다|다녀|여행|산책",
    "eat": r"먹|마셨|마시",
    "conflict": r"다퉜|다툰|다투|다툼|싸웠|싸운|싸우|말다툼",
    "cancel": r"취소",
}
COLORS = {
    "파란": "파란색",
    "파랑": "파란색",
    "빨간": "빨간색",
    "빨강": "빨간색",
    "푸른": "파란색",
    "노란": "노란색",
    "검은": "검은색",
    "하얀": "흰색",
}
DISTANCE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(km|킬로미터|킬로|m|미터)(?![a-zA-Z])", re.I)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def name(value):
    value = str(value or "").strip()
    if value in {"나", "내", "내가", "나는", "저", "제가", "사용자", "기록 작성자"}:
        return "self"
    return re.sub(r"(?:이가|이는|이를|이한테|이에게|한테|에게|께|은|는|이|가|을|를)$", "", value)


def distance_values(text):
    return [
        Decimal(m.group(1)) * (1000 if m.group(2).lower() in {"km", "킬로미터", "킬로"} else 1)
        for m in DISTANCE.finditer(text)
    ]


def relation(text):
    # Cancellation overrides an embedded visit. Desire overrides its embedded receive.
    for key in ("cancel", "desire", "prefer", "give", "receive", "run", "eat", "conflict", "visit"):
        if re.search(PATTERNS[key], text):
            return key
    return "other"


def project(memory, source, reference_time, recorded_at):
    content = memory["content"]
    quotes = [e["quote"] for e in memory["evidence"]]
    # A broad quote can contain multiple events; use the focused triple/content for relation.
    focused = content + " " + memory.get("predicate", "")
    rel = relation(focused)
    subject = memory.get("subject", {})
    actor = "self" if subject.get("kind") == "self" else name(subject.get("value"))
    quote_text = " ".join(quotes)
    role_conflict = (
        rel == "receive"
        and actor == "self"
        and bool(re.search(r"내가\s*아니라|나는\s*아니", quote_text))
    )
    participant_match = re.search(r"([가-힣A-Za-z]+?)(?:이한테|이에게|한테|에게|께)", quote_text)
    recipient = name(participant_match.group(1)) if participant_match else None
    if rel == "give":
        explicit_actors = {
            name(m[1])
            for m in re.finditer(
                r"(?:^|\s)([가-힣]{1,8}?)(?:은|는|이|가)\s+[^.!?]*(?:선물했|줬|주었)", quote_text
            )
        }
        if len(explicit_actors) == 1 and actor not in explicit_actors:
            role_conflict = True
    if not recipient and rel == "give":
        target = memory.get("target") or {}
        candidate = (target.get("object") or {}).get("value")
        if (
            candidate
            and str(candidate) in quote_text
            and not any(str(candidate) in c for c in ("머그컵", "선물"))
        ):
            recipient = name(candidate)
    # Recover a clearly quoted person's desire/preference when the extractor used self.
    if rel in {"desire", "prefer"}:
        match = re.search(
            r"(?:^|[.!?]\s*|\s)([가-힣]{2,8}?)(?:이는|이가|은|는|이|가)\s+[^.!?]*(?:받고\s*싶|원했|좋아|선호)",
            quote_text,
        )
        if match:
            actor = name(match.group(1))
    colors = sorted({v for k, v in COLORS.items() if k in focused})
    obj = str((memory.get("object") or {}).get("value") or "")
    core = "머그컵" if "머그컵" in focused + obj else re.sub(r"\s+", "", obj)
    counterparty = None
    if rel == "conflict":
        match = re.search(r"([가-힣A-Za-z]+?)(?:랑|와|과)\s", content)
        counterparty = name(match.group(1)) if match else name(obj)
    if rel == "run":
        core = "달리기"
    values = distance_values(content)
    # A projected numeric value must also occur, with equivalent units, in its quote.
    verified_values = sorted({str(v) for v in values if v in distance_values(quote_text)})
    negative = memory.get("assertion_polarity") == "negated" or bool(
        re.search(r"않|못했|안\s|취소", focused)
    )
    state = (
        "negated"
        if negative
        else "uncertain"
        if memory.get("assertion_polarity") == "uncertain"
        or memory.get("content_certainty") == "uncertain"
        else "desire"
        if rel == "desire"
        else "preference"
        if rel == "prefer"
        else "planned"
        if memory["memory_type"] in {"plan", "decision"}
        else "observed"
    )
    event_time = dict(memory["time"])
    time_in_source = bool(
        re.search(
            r"\d{4}(?:년|-)|\d{1,2}월|오늘|어제|그제|그저께|내일|(?:다음|지난|이번)\s*주|작년|올해|지난달|이번달",
            source,
        )
    )
    time_corrected = not time_in_source and bool(event_time.get("start") or event_time.get("end"))
    if not time_in_source:
        event_time.update(
            raw=None, start=None, end=None, precision="unknown", certainty="uncertain"
        )
    if event_time.get("raw") in {"어제", "오늘", "그제", "그저께", "내일"} and reference_time:
        base = date.fromisoformat(reference_time[:10])
        delta = {"어제": -1, "오늘": 0, "그제": -2, "그저께": -2, "내일": 1}[event_time["raw"]]
        event_time.update(
            start=(base + timedelta(days=delta)).isoformat(),
            end=None,
            precision="day",
            certainty="inferred",
        )
    source_units = sentences(source)
    selected_units = [
        u
        for u in source_units
        if any(q.strip() in u["text"] or u["text"].strip() in q for q in quotes)
    ]
    checked = {"time": event_time}
    time_validation = normalize_time(checked, selected_units, reference_time)
    event_time = checked["time"]
    return {
        "projection_version": FACT_VERSION,
        "actor": actor,
        "recipient": recipient,
        "counterparty": counterparty,
        "speaker": actor if re.search(r"말했|말했다|말하", quote_text) else None,
        "relation": rel,
        "object": obj,
        "object_key": core,
        "colors": colors,
        "distance_m": verified_values,
        "state": state,
        "event_time": event_time,
        "time_validation": time_validation,
        "warnings": (["ungrounded_event_time_removed"] if time_corrected else [])
        + (["role_conflict"] if role_conflict else []),
        "recorded_at": recorded_at,
        "reference_time": reference_time,
        "identity": "self" if actor == "self" else "name_only",
        "explicit_change": bool(re.search(r"이제|더\s*좋|바뀌|바꿨|변했|대신", focused)),
        "evidence": [
            {"quote": q, "start": source.find(q), "end": source.find(q) + len(q)} for q in quotes
        ],
    }


def explicit_dates(question, today):
    """Only locally parsed, explicit date phrases can impose a hard filter."""
    base = date.fromisoformat(today)
    for word, delta in (("그저께", -2), ("그제", -2), ("어제", -1), ("오늘", 0), ("내일", 1)):
        if word in question:
            d = (base + timedelta(days=delta)).isoformat()
            return {"date_from": d, "date_to": d}
    if "지난달" in question or "이번 달" in question or "이번달" in question:
        d = base.replace(day=1)
        if "지난달" in question:
            d = (d - timedelta(days=1)).replace(day=1)
        return {
            "date_from": d.isoformat(),
            "date_to": d.replace(day=calendar.monthrange(d.year, d.month)[1]).isoformat(),
        }
    if "작년" in question or "올해" in question:
        year = base.year - int("작년" in question)
        return {"date_from": f"{year}-01-01", "date_to": f"{year}-12-31"}
    matches = list(
        re.finditer(r"(?:(\d{4})(?:년\s*|-))?(\d{1,2})(?:월\s*|-)(\d{1,2})(?:일)?", question)
    )
    if matches:
        dates = []
        for m in matches:
            try:
                dates.append(date(int(m[1] or base.year), int(m[2]), int(m[3])).isoformat())
            except ValueError:
                return {"date_from": None, "date_to": None}
        return {"date_from": dates[0], "date_to": dates[-1]}
    return {"date_from": None, "date_to": None}


def query_plan(question, understood, today):
    recipient_match = re.search(r"([가-힣A-Za-z]+?)(?:이에게|이한테|에게|한테|께)", question)
    actor_match = re.search(r"(?:^|\s)([가-힣A-Za-z]+?)(?:이가|이는|이|가|은|는)\s", question)
    if actor_match and actor_match[1] in {"누", "누구", "뭐", "무엇", "선물", "기록", "사람", "것"}:
        actor_match = None
    rel = relation(question)
    if re.search(r"달린|달렸|달려|달리", question):
        rel = "run"
    kind = (
        "why"
        if re.search(r"왜|이유|원인", question)
        else "change"
        if re.search(r"바뀌|바뀐|바꾼|변했|변한|변화", question)
        else "compare"
        if re.search(r"같아|같은|달라|다른|비교|차이", question)
        else "when"
        if re.search(r"언제|날짜|시점", question)
        else "current"
        if re.search(r"지금|현재|요즘", question)
        else "recall"
    )
    if kind == "recall" and re.search(r"무슨\s*일|뭐\s*했|뭘\s*했|무엇을\s*했", question):
        kind = "activities"
    amount = distance_values(question)
    operator = (
        "ge"
        if "이상" in question
        else "gt"
        if "초과" in question
        else "le"
        if "이하" in question
        else "lt"
        if "미만" in question
        else "eq"
    )
    return {
        "recipient": name(recipient_match[1]) if recipient_match else None,
        "actor": name(actor_match[1]) if actor_match else None,
        "needs_time_anchor": bool(re.search(r"당시|그때", question))
        and not explicit_dates(question, today)["date_to"],
        "relation": rel,
        "kind": kind,
        "question": question,
        "distance_m": str(amount[0]) if len(amount) == 1 else None,
        "operator": operator,
        "planned": bool(re.search(r"계획|예정|하려|하기로", question)),
        "self": bool(re.search(r"(?:^|\s)(?:나|내가|나는|내|제가|저는)(?:\s|$)", question)),
        "filters": explicit_dates(question, today),
        "intent": understood["intent"],
    }


def quantity_matches(fact, plan):
    if plan["distance_m"] is None:
        return True
    expected = Decimal(plan["distance_m"])
    for number in fact["distance_m"]:
        value = Decimal(number)
        if {
            "eq": value == expected,
            "ge": value >= expected,
            "gt": value > expected,
            "le": value <= expected,
            "lt": value < expected,
        }[plan["operator"]]:
            return True
    return False


def compatible(fact, plan):
    if plan.get("recipient") and fact.get("recipient") != plan["recipient"]:
        return False
    if "role_conflict" in fact.get("warnings", []):
        return False
    if plan["relation"] != "other" and plan["kind"] not in {"compare", "change"}:
        if fact["relation"] != plan["relation"] and not (
            plan["relation"] == "receive" and fact["relation"] == "give"
        ):
            return False
    actor = (
        fact["recipient"]
        if plan["relation"] == "receive" and fact["relation"] == "give"
        else fact["actor"]
    )
    if plan["self"] and plan["relation"] in {"run", "give", "receive"} and actor != "self":
        return False
    if plan.get("actor") and plan["kind"] not in {"compare", "change"} and actor != plan["actor"]:
        return False
    if plan["relation"] in {"give", "receive"} and plan["kind"] not in {"compare", "change"}:
        wants_negative = bool(re.search(r"안\s*줬|주지\s*않|못\s*받|받지\s*않", plan["question"]))
        if not plan["planned"] and not wants_negative and fact["state"] != "observed":
            return False
    if plan["relation"] == "run":
        if (fact["state"] == "planned") != plan["planned"] or fact["state"] in {
            "negated",
            "uncertain",
        }:
            return False
    return quantity_matches(fact, plan)


def connection(a, b):
    """Conservative candidate links. No inferred edge changes the truth of a fact."""
    if not a["object_key"] or a["object_key"] != b["object_key"]:
        return None
    if a["relation"] == "give" and b["relation"] == "desire":
        a, b = b, a
    if a["relation"] == "desire" and b["relation"] == "give":
        if a["actor"] and a["actor"] == b["recipient"]:
            return {
                "kind": "desire_action",
                "basis": "inferred",
                "explanation": "같은 이름의 인물이 원한 대상과 실제 선물이 연결될 수 있습니다. 취향 변경을 뜻하지 않습니다.",
                "identity_uncertain": a["identity"] != "self",
            }
    if not a["actor"] or a["actor"] != b["actor"] or a["relation"] != b["relation"]:
        return None
    if a["state"] == "planned" or b["state"] == "planned":
        planned, done = (a, b) if a["state"] == "planned" else (b, a)
        planned_at = planned["event_time"].get("start")
        done_at = done["event_time"].get("start")
        if planned_at and done_at and done_at < planned_at:
            return None
        if (
            done["state"] == "observed"
            and planned["colors"] == done["colors"]
            and planned["distance_m"] == done["distance_m"]
        ):
            return {
                "kind": "plan_action",
                "basis": "inferred",
                "explanation": "같은 대상의 계획과 실행 기록입니다. 해당 계획을 실행한 것인지는 추정입니다.",
                "identity_uncertain": a["identity"] != "self",
            }
    if a["relation"] == "prefer" and a["colors"] != b["colors"]:
        return {
            "kind": "preference_change"
            if a["explicit_change"] or b["explicit_change"]
            else "different_preferences",
            "basis": "inferred",
            "explanation": "같은 이름과 대상에 서로 다른 선호가 기록되어 있습니다. 각 사건 시각과 원문을 확인하세요.",
            "identity_uncertain": a["identity"] != "self",
        }
    if (
        {a["state"], b["state"]} == {"negated", "observed"}
        and a["colors"] == b["colors"]
        and a["distance_m"] == b["distance_m"]
    ):
        if a["event_time"].get("start") and a["event_time"].get("start") == b["event_time"].get(
            "start"
        ):
            return {
                "kind": "conflicting_claims",
                "basis": "inferred",
                "explanation": "같은 시점·대상에 긍정과 부정 진술이 함께 있습니다. 어느 기록이 맞는지 확정하지 않았습니다.",
                "identity_uncertain": a["identity"] != "self",
            }
    return None
