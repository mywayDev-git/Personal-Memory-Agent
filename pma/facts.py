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

from scripts.memory_agent.meaning import extraction_conflicts
from scripts.memory_agent.provenance import normalize_time, sentences

from .diagnostics import Reason, Stage
from .facts_diagnostics import comparison_check, comparison_reason, observed_facts
from .search_expressions import event_text

FACT_VERSION = 10
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
    "give": r"선물했|선물한|선물하|줬|주었|주다|주지|주려|(?<![가-힣])준(?:\s|거|건|것|선물)|주기로|전달했",
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
    text = event_text(text)
    # Cancellation overrides an embedded visit. Desire overrides its embedded receive.
    for key in ("cancel", "desire", "prefer", "give", "receive", "run", "eat", "conflict", "visit"):
        if re.search(PATTERNS[key], text):
            return key
    return "other"


def mentions_person(text, person):
    return bool(re.search(
        r"(?<![가-힣A-Za-z])" + re.escape(person) +
        r"(?=이(?:가|는|를|랑|한테|에게)|한테|에게|와|과|랑|은|는|을|를|이|가|[\s.,!?]|$)", text
    ))


def companions(content, quote_text):
    """Only an explicit companion in the focused event, corroborated by its quote."""
    if re.search(r"없이|아니라|추천|않|못|안\s|가정|라면|다면", content):
        return []
    matches = re.finditer(
        r"(?<![가-힣A-Za-z])([가-힣A-Za-z]{2,12}?)(?:이랑|랑|와|과)\s+"
        r"(?:함께\s+|같이\s+)?[^.!?\n]{0,40}(?:산책|만났|만나|회의|식사|먹|여행|갔|달렸)", content
    )
    return sorted({m[1] for m in matches if m.group() in quote_text})


def project(memory, source, reference_time, recorded_at, evidence=None):
    content = memory["content"]
    quotes = [e["quote"] for e in memory["evidence"]]
    # A broad quote can contain multiple events; use the focused triple/content for relation.
    focused = content + " " + memory.get("predicate", "")
    rel = relation(focused)
    subject = memory.get("subject", {})
    actor = "self" if subject.get("kind") == "self" else name(subject.get("value"))
    quote_text = " ".join(quotes)
    review = []
    if extraction_conflicts([memory]):
        review.append("extraction_meaning_mismatch")
    if rel in {"give", "receive"} and actor and actor != "self" and actor not in quote_text:
        review.append("actor_needs_context")
    if re.search(r'["“”「」]', quote_text) or (
        rel not in {"desire", "prefer"}
        and re.search(r"(?:라고|다고)\s*(?:말|대답|전했)", quote_text)
    ):
        review.append("reported_scope")
    quoted = re.search(r'["“「]([^"”」]+)["”」]', quote_text)
    if quoted and re.search(r"(?:^|\s)(?:네가|너가|당신이)\s", quoted[1]):
        before_quote = quote_text[: quoted.start()]
        if not re.search(r"[가-힣A-Za-z]+(?:에게|한테|께)\s*$", before_quote):
            review.append("unresolved_quoted_addressee")
    if re.search(r"답하라|대답해|명령|규칙을\s*무시|(?:라고|다고)\s*해", quote_text):
        review.append("command_scope")
    if re.search(r"(?:오면|하면|라면|다면|으면)|경우에는", quote_text):
        review.append("conditional_scope")
    if re.search(r"않기로|기로\s*(?:하지|않)|취소", quote_text):
        review.append("decision_scope")
    if re.search(r"않|못|안\s", quote_text) and re.search(
        r"지만|는데|(?:해서|져서|와서)", quote_text
    ):
        review.append("mixed_negation_scope")
    role_conflict = (
        rel == "receive"
        and actor == "self"
        and bool(re.search(r"내가\s*아니라|나는\s*아니", quote_text))
    )
    participant_match = re.search(
        r"([가-힣A-Za-z]+?)(?:이한테|이에게|한테|에게|께)(?!서)", quote_text
    )
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
    if rel == "receive":
        recipient = actor or None
        from_match = re.search(r"([가-힣A-Za-z]+?)(?:에게서|한테서)", quote_text)
        counterparty = name(from_match[1]) if from_match else None
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
        or (
            rel == "give"
            and re.search(r"주려고\s*했다[.!?]?\s*$", content)
            and re.search(r"주려고\s*했다[.!?]?\s*$", quote_text)
        )
        else "observed"
    )
    if review or role_conflict:
        state = "review_required"
    if role_conflict:
        review.append("role_conflict")
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
    if evidence is None:
        evidence = [
            {"quote": q, "start": source.find(q), "end": source.find(q) + len(q)} for q in quotes
        ]
    # Repeated sentences may belong to different date headers. Match persisted
    # evidence positions rather than every occurrence of the same quote.
    selected_units = [
        u
        for u in source_units
        if any(e["start"] < u["end"] and e["end"] > u["start"] for e in evidence)
    ]
    checked = {"time": event_time}
    time_validation = normalize_time(checked, selected_units, reference_time)
    event_time = checked["time"]
    if "reported_scope" in review and re.search(r"어제|오늘|그제|그저께|내일", quote_text):
        event_time.update(start=None, end=None, precision="unknown", certainty="uncertain")
        review.append("quoted_time_anchor")
        time_validation = {"status": "review_required", "reason": "quoted_time_anchor"}
    return {
        "projection_version": FACT_VERSION,
        "actor": actor,
        "recipient": recipient,
        "counterparty": counterparty,
        "participants": companions(content, quote_text),
        "speaker": None,
        "review_reasons": review,
        "action_relation": next(
            (
                key
                for key in ("give", "receive", "run", "visit")
                if re.search(PATTERNS[key], event_text(focused))
            ),
            rel,
        ),
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
        "evidence": evidence,
    }


@observed_facts(Stage.DATE_PARSING)
def explicit_dates(question, today):
    """Only locally parsed, explicit date phrases can impose a hard filter."""
    base = date.fromisoformat(today)
    # Resolve the most specific expression before broad year/month phrases.
    matches = list(
        re.finditer(
            r"(?<!\d)(?:(\d{4})(?:년\s*|-))?(\d{1,2})(?:월\s*|-)(\d{1,2})(?:일)?(?!\d)", question
        )
    )
    if matches:
        dates = []
        for m in matches:
            try:
                year = int(m[1]) if m[1] else base.year - int("작년" in question)
                dates.append(date(year, int(m[2]), int(m[3])).isoformat())
            except ValueError:
                return {"date_from": None, "date_to": None}
        if dates[0] > dates[-1]:
            return {"date_from": None, "date_to": None}
        return {"date_from": dates[0], "date_to": dates[-1]}
    relative = list(re.finditer(r"그저께|그제|어제|오늘|내일", question))
    if relative:
        offsets = {"그저께": -2, "그제": -2, "어제": -1, "오늘": 0, "내일": 1}
        dates = [(base + timedelta(days=offsets[m[0]])).isoformat() for m in relative]
        return {"date_from": min(dates), "date_to": max(dates)}
    month = re.search(r"(?:(\d{4})년\s*)?(\d{1,2})월", question)
    if month:
        year = int(month[1]) if month[1] else base.year - int("작년" in question)
        try:
            d = date(year, int(month[2]), 1)
        except ValueError:
            return {"date_from": None, "date_to": None}
        return {
            "date_from": d.isoformat(),
            "date_to": d.replace(day=calendar.monthrange(d.year, d.month)[1]).isoformat(),
        }
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
    return {"date_from": None, "date_to": None}


@observed_facts(Stage.QUERY_PLAN)
def query_plan(question, understood, today):
    from .search_expressions import canonical_query
    # Model roles remain hints. A source substring proves provenance, not semantics.
    hints = {}
    for role in ("actor", "recipient"):
        candidate = understood.get(role) or {}
        value, evidence = candidate.get("value"), candidate.get("evidence")
        if (
            isinstance(value, str)
            and isinstance(evidence, str)
            and value
            and evidence
            and value in evidence
            and evidence in question
            and value not in {"누가", "누구", "언제", "주는", "주", "받은", "받", "날짜", "감정"}
            and not re.search(r"누구|누가|언제", evidence)
        ):
            hints[role] = {"value": name(value), "evidence": evidence, "verified": False}
    # Registered noun phrases (e.g. 머신러닝) must not trigger an activity
    # condition merely because they contain 러닝. Keep the original question.
    relation_question = canonical_query(question)
    rel = relation(relation_question)
    if re.search(r"달린|달렸|달려|달리", event_text(relation_question)):
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
        "recipient": None,
        "actor": None,
        "role_hints": hints,
        "requested_slots": understood.get("requested_slots", []),
        "execution_check": bool(
            re.search(r"(?:줬|주었|받았|달렸|실행|완료).*\?|(?:했어|했나|했니)\?", question)
        )
        and not re.search(r"누구|누가|언제|날짜|몇\s*km|얼마|왜|이유", question),
        "event_listing": bool(
            re.search(r"달린.*(?:기록|날짜)|(?:준|받은).*목록|실행.*목록", question)
        ),
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


def _incompatible(reason, on_exclude):
    comparison_reason(reason)
    if on_exclude is not None:
        try:
            on_exclude(reason)
        except Exception:
            pass
    return False


@observed_facts(Stage.FACT_COMPARISON)
def compatible(fact, plan, *, on_exclude=None, diagnostic_id=None):
    review = bool(fact.get("review_reasons"))
    if plan["relation"] != "other" and plan["kind"] not in {"compare", "change"}:
        if (
            fact["relation"] != plan["relation"]
            and not (plan["relation"] == "receive" and fact["relation"] == "give")
            and fact.get("action_relation") != plan["relation"]
        ):
            return _incompatible(Reason.RELATION_MISMATCH, on_exclude)
    comparison_check(
        "relation",
        True,
        applied=plan["relation"] != "other" and plan["kind"] not in {"compare", "change"},
    )
    actor = (
        fact["recipient"]
        if plan["relation"] == "receive" and fact["relation"] == "give"
        else fact["actor"]
    )
    if (
        not review
        and plan["self"]
        and plan["relation"] in {"run", "give", "receive"}
        and actor != "self"
    ):
        return _incompatible(Reason.PERSON_MISMATCH, on_exclude)
    comparison_check(
        "person",
        True,
        applied=not review and plan["self"] and plan["relation"] in {"run", "give", "receive"},
    )
    if plan.get("event_listing") and fact["state"] != "observed" and not review:
        return _incompatible(Reason.STATUS_MISMATCH, on_exclude)
    if plan["relation"] == "run" and not plan.get("execution_check") and not review:
        if (fact["state"] == "planned") != plan["planned"] or fact["state"] in {
            "negated",
            "uncertain",
        }:
            return _incompatible(Reason.STATUS_MISMATCH, on_exclude)
    comparison_check(
        "state",
        True,
        applied=not review
        and bool(
            plan.get("event_listing")
            or (plan["relation"] == "run" and not plan.get("execution_check"))
        ),
    )
    matched = quantity_matches(fact, plan)
    if not matched:
        return _incompatible(Reason.QUANTITY_MISMATCH, on_exclude)
    comparison_check("quantity", True, applied=plan["distance_m"] is not None)
    return matched


def connection(a, b):
    """Conservative candidate links. No inferred edge changes the truth of a fact."""
    if not a["object_key"] or a["object_key"] != b["object_key"]:
        return None
    if any(
        fact.get("review_reasons") or "role_conflict" in fact.get("warnings", []) for fact in (a, b)
    ):
        return None
    if a["state"] == "uncertain" or b["state"] == "uncertain":
        return None
    if a["relation"] == "give" and b["relation"] == "desire":
        a, b = b, a
    if a["relation"] == "desire" and b["relation"] == "give":
        if (
            a["state"] == "desire"
            and b["state"] == "observed"
            and a["actor"]
            and a["actor"] == b["recipient"]
        ):
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
