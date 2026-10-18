"""Conservative extraction checks; uncertain relations are never guessed into facts."""

import re
from copy import deepcopy

POLICY_VERSION = 5
RULES = """
추가 추출 규칙:
같은 사건의 인물·장소·대상을 각각 별도 기억으로 반복하지 않는다.
"유진과 카페에서 보고서를 완성했다"는 사건 1개이며 object는 보고서다.
동행인과 장소는 content에 보존한다. 독립된 백업과 OS 재설치 행동은 분리한다.
subject는 실제 행동 주체, object는 행동 대상이다. 동행인·수신자·시간을 object에 넣지 않는다.
"유진이 나에게 책을 줬다": subject=유진, predicate=주다, object=책.
"나는 유진에게 책을 줬다": subject=사용자, predicate=주다, object=책.
"나는 유진에게서 책을 받았다": subject=사용자, predicate=받다, object=책.
target은 선택적인 추가 관계다. 명확한 관계 하나만 표현하고 확신이 없으면 null이다.
"사용자가 유진과 도서관에서 공부했다": target은 사용자→함께하다→유진으로 표현할 수 있다.
유진→동반하다→도서관 또는 유진→동반하다→다음 주 금요일은 잘못된 관계다.
장소 관계는 사용자→공부한 장소→도서관처럼 사건의 의미와 주체가 맞아야 한다.
"유진은 민수의 동생이다" 같은 인물 관계와 "연구실은 학교에 소속된다" 같은 조직 관계를 보존한다.
원문에 없는 관계나 동명이인의 동일성을 추측하지 않는다. 부정·계획·인용·불확실성을 보존한다.
time.raw는 선택한 근거에 있는 해당 사건의 시간 표현만 복사한다.
날짜 계산은 Python이 담당한다. time.start/end=null, precision=relative 또는 unknown,
certainty=uncertain으로 출력한다. 시간 표현이 없으면 raw=null이다.
"""

SELF = {"나", "내", "저", "제", "사용자"}
GIVE = {"주다", "줬다", "주었다", "줌"}
RECEIVE = {"받다", "받았다", "받음"}
COMPANION = re.compile(r"(?:(?:동반|동행)(?:하다|했다|함|인)?|(?:함께|같이)(?:하다|했다|함))")
# Only a complete, simple transfer clause is checked. Quoted, compound and
# omitted-subject clauses need semantic review and are deliberately not parsed.
TRANSFER = re.compile(
    r"(?P<actor>[가-힣A-Za-z]+?)(?:은|는|이|가)\s+"
    r"(?P<peer>[가-힣A-Za-z]+?)(?P<particle>에게서|한테서|로부터|에게|한테)\s+"
    r"(?P<object>[가-힣A-Za-z0-9 ]+?)(?:을|를)\s+"
    r"(?P<verb>줬다|주었다|받았다|주지\s+않았다|받지\s+않았다)[.!]?"
)


def same_entity(ref, name):
    if name in SELF:
        return ref.get("kind") == "self"
    return ref.get("kind") != "self" and ref.get("value") == name


def remove_duplicate_target(memory):
    """An exact duplicate adds no relation; do not infer a replacement."""
    target = memory.get("target")
    if target and all(target[key] == memory[key] for key in ("subject", "predicate", "object")):
        memory["target"] = None
        return [dict(code="TARGET_DUPLICATE_REMOVED", rule="identical_primary_triple")]
    return []


def restore_explicit_companion(memory):
    """Restore only a single leading companion in a simple positive shared activity.

    The content must equal the source with only its companion and/or time prefix
    removed. This is not name recognition or a general relation inference rule.
    """
    if (
        memory["subject"]["kind"] != "self"
        or memory["assertion_polarity"] != "affirmed"
        or memory["content_certainty"] != "explicit"
        or memory["memory_type"] not in ("event", "plan")
        or len(memory["evidence"]) != 1
    ):
        return []
    source = memory["evidence"][0]["quote"].strip().rstrip(".!?")
    if re.search(r'["\'“”‘’\n]|(?:라고|다고)\s*(?:말|했|전)', source):
        return []
    # Restrict this rule to named shared activities; comparisons and relational
    # adjectives ("민수와 다르다/친하다") do not imply accompaniment.
    if not re.search(r"마치|완료|공부|준비|산책|회의|운동|작업|관람", memory["predicate"]):
        return []
    raw = memory["time"].get("raw")
    scoped = source
    prefix = ""
    if raw and scoped.startswith(raw):
        match = re.match(re.escape(raw) + r"(?:에는|에)?\s+", scoped)
        if match:
            prefix, scoped = scoped[: match.end()], scoped[match.end() :]
    scoped = re.sub(r"^(?:나는|저는)\s+", "", scoped)
    match = re.fullmatch(r"(?P<name>[가-힣A-Za-z]{2,12})(?:와|과)\s+(?P<body>.+)", scoped)
    if not match or re.search(r"[가-힣A-Za-z]+(?:와|과)\s", match["body"]):
        return []
    name, body = match["name"], match["body"]
    if re.search(r"않|못|아니|없|아마|같다|듯|만약|거나|지만|으며|면서|고\s|[;,]", body):
        return []
    obj = memory["object"].get("value")
    if not isinstance(obj, str) or obj not in body:
        return []
    content = memory["content"].strip().rstrip(".!?")
    alternatives = {source, scoped, body, prefix + body}
    if content not in alternatives:
        return []
    warnings = []
    if name not in content:
        memory["content"] = source
        warnings.append(dict(code="CONTENT_PARTICIPANT_RESTORED", rule="single_leading_companion"))
    target = memory.get("target")
    invalid_companion = (
        target
        and COMPANION.fullmatch(target["predicate"].strip())
        and any(issue["field"] == "target" for issue in relation_issues(memory))
    )
    if target is None or invalid_companion:
        memory["target"] = dict(
            subject=deepcopy(memory["subject"]),
            predicate="함께하다",
            object=dict(kind="entity", value=name, value_type="string"),
        )
        warnings.append(dict(code="TARGET_GROUNDED_FROM_SOURCE", rule="single_leading_companion"))
    return warnings


def relation_issues(memory):
    """Return only mechanically supported violations, not a semantic score."""
    issues = []
    quotes = [item["quote"] for item in memory["evidence"]]
    target = memory.get("target")
    if target and COMPANION.fullmatch(target["predicate"].strip()):
        # A time expression or a destination marked with 에서/에 cannot be the
        # participant of a companion relation. Literal alone is not an error.
        for field in ("subject", "object"):
            ref = target[field]
            value = ref.get("value")
            if not isinstance(value, str) or ref.get("kind") == "self":
                continue
            raw = memory["time"].get("raw")
            temporal = (raw and value == raw) or re.fullmatch(
                r"(?:오늘|어제|내일|(?:다음|이번|지난)\s*주(?:\s*[월화수목금토일]요일)?|"
                r"\d{4}-\d{2}-\d{2}|\d+시(?:\s*\d+분)?)",
                value,
            )
            place = any(re.search(re.escape(value) + r"(?:에서|에)\s", q) for q in quotes)
            if temporal or place:
                issues.append({"field": "target", "code": "INVALID_COMPANION_ARGUMENT"})
                break
        for field in ("subject", "object"):
            ref = target[field]
            if ref["kind"] in ("entity", "literal") and isinstance(ref["value"], str):
                if not any(ref["value"] in q for q in quotes):
                    issues.append({"field": "target", "code": "UNGROUNDED_COMPANION"})
                    break
    if len(quotes) == 1:
        # A leading companion cannot be the object of these intransitive shared
        # activities. Detect the error; do not invent an unstated action object.
        scoped = quotes[0].strip()
        raw = memory["time"].get("raw")
        if raw:
            scoped = re.sub(r"^" + re.escape(raw) + r"(?:에는|에)?\s+", "", scoped)
        scoped = re.sub(r"^(?:나는|저는)\s+", "", scoped)
        companion = re.fullmatch(
            r"(?P<name>[가-힣A-Za-z]{2,12})(?:와|과)\s+"
            r"(?:[가-힣A-Za-z]+에서\s+)?"
            r"(?:산책|운동)(?:했다|할 예정이다|하기로 했다)[.!]?",
            scoped,
        )
        if (
            companion
            and memory["subject"]["kind"] == "self"
            and memory["object"]["value"] == companion["name"]
        ):
            issues.append({"field": "object", "code": "COMPANION_AS_ACTION_OBJECT"})
        clause = re.sub(r"^(?:어제|오늘|그저께|내일)\s+", "", quotes[0].strip())
        match = TRANSFER.fullmatch(clause)
        if match:
            d = match.groupdict()
            receiving = d["verb"].startswith("받")
            negated = "않았다" in d["verb"]
            if receiving != (d["particle"] in ("에게서", "한테서", "로부터")):
                return issues
            if not same_entity(memory["subject"], d["actor"]):
                issues.append({"field": "subject", "code": "TRANSFER_ACTOR_MISMATCH"})
            predicates = (
                {"받다", "받았다", "받음"} if receiving else {"주다", "줬다", "주었다", "줌"}
            )
            if memory["predicate"] not in predicates:
                # Synonyms are not proven wrong; only the opposite transfer is.
                opposite = (
                    {"주다", "줬다", "주었다", "줌"} if receiving else {"받다", "받았다", "받음"}
                )
                if memory["predicate"] in opposite:
                    issues.append({"field": "predicate", "code": "TRANSFER_DIRECTION_MISMATCH"})
            value = memory["object"]["value"]
            original_object = d["object"].strip()
            if (
                not isinstance(value, str)
                or not value
                or (value not in original_object and original_object not in value)
            ):
                issues.append({"field": "object", "code": "TRANSFER_OBJECT_MISMATCH"})
            if (
                memory["assertion_polarity"] != ("negated" if negated else "affirmed")
                or memory["memory_type"] == "plan"
            ):
                issues.append({"field": "assertion_polarity", "code": "TRANSFER_STATE_MISMATCH"})
            if target and target["predicate"] in GIVE | RECEIVE:
                giver, receiver = (d["peer"], d["actor"]) if receiving else (d["actor"], d["peer"])
                target_actor = giver if target["predicate"] in GIVE else receiver
                if not same_entity(target["subject"], target_actor):
                    issues.append({"field": "target", "code": "TRANSFER_TARGET_ACTOR_MISMATCH"})
                target_object = target["object"]["value"]
                if (
                    not isinstance(target_object, str)
                    or not target_object
                    or (
                        target_object not in original_object
                        and original_object not in target_object
                    )
                ):
                    issues.append({"field": "target", "code": "TRANSFER_TARGET_OBJECT_MISMATCH"})
    return issues


def restore_transfer_participants(memory):
    """Preserve explicit sender/receiver text only after the core triple passes."""
    if len(memory["evidence"]) != 1 or relation_issues(memory):
        return []
    source = memory["evidence"][0]["quote"].strip()
    clause = re.sub(r"^(?:어제|오늘|그저께|내일)\s+", "", source)
    match = TRANSFER.fullmatch(clause)
    if not match:
        return []
    receiving = match["verb"].startswith("받")
    if receiving != (match["particle"] in ("에게서", "한테서", "로부터")):
        return []
    names = [match["peer"]]
    if match["actor"] not in SELF:
        names.append(match["actor"])
    if any(name not in memory["content"] for name in names):
        memory["content"] = source.rstrip(".!?")
        return [dict(code="TRANSFER_PARTICIPANTS_RESTORED", rule="explicit_simple_transfer")]
    return []


def align_evidence(memory, units):
    """Re-anchor only a unique verbatim full-content match inside target units."""
    content = memory["content"].strip().rstrip(".!?")
    if len(content) < 8 or any(content in u["text"] for u in units["selected"]):
        return None
    candidates = [u for u in units["allowed"] if content in u["text"]]
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    refs = [memory["subject"], memory["object"]]
    if memory.get("target"):
        refs += [memory["target"]["subject"], memory["target"]["object"]]
    if any(
        r["kind"] not in ("self", "unknown")
        and r["value"] is not None
        and str(r["value"]) not in candidate["text"]
        for r in refs
    ):
        return None
    return [candidate]
