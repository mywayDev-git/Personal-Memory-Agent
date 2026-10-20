"""A plan is evidence of intent; it cannot establish actual completion."""

import re

from scripts.memory_agent.provenance import sentences

PLAN = re.compile(r"([가-힣]{2,12})할\s*(?:계획|예정)(?:이다|입니다|이었다|이었습니다|이었어요)[.!?]?$")
UNKNOWN = re.compile(r"확인(?:할\s*수\s*없|되지|하기\s*어렵)|알\s*수\s*없|불명|미상|모르|단정.{0,8}없")


def actual_question(question):
    return bool(re.search(r"실제|실행|완료", question)) and not re.search(r"계획|예정", question)


def plan_form(source):
    text = source.strip()
    if len(text) > 300 or len(sentences(text)) != 1:
        return None
    match = PLAN.search(text)
    if not match:
        return None
    stem = match[1]
    if re.search(re.escape(stem) + r"(?:했|하였|하지\s*않|완료)", text[:match.start()]):
        return None
    return stem


def execution_draft(question, evidence):
    if not actual_question(question):
        return None
    compact = re.sub(r"\s+", "", question)
    candidates = []
    for row in evidence:
        text = row["source_text"].strip()
        stem = plan_form(text)
        key = (row.get("fact") or {}).get("object_key") or ""
        if (not stem or stem not in question or len(key) < 2 or key not in compact
                or key not in re.sub(r"\s+", "", text)):
            continue
        if any(stem in other["source_text"] and not plan_form(other["source_text"])
               for other in evidence):
            continue
        candidates.append((row, stem))
    if len(candidates) != 1:
        return None
    row, stem = candidates[0]
    return {"status": "answered", "items": [{
        "text": "기록에는 “" + row["source_text"].strip() + "”라고 되어 있습니다. "
                "이 기록만으로는 실제 " + stem + " 여부를 확인할 수 없습니다.",
        "citations": [row["id"]],
    }]}


def enforce_execution_limit(question, evidence, response, review):
    if not actual_question(question):
        return
    cited = {cid for item in response["items"] for cid in item["citations"]}
    rows = [row for row in evidence if row["id"] in cited]
    only_plans = bool(rows) and all(plan_form(row["source_text"]) for row in rows)
    if only_plans and not UNKNOWN.search(" ".join(item["text"] for item in response["items"])):
        review["fulfillment"] = "missing"
        review["reason"] = "계획만으로 실제 실행을 확인할 수 없다는 한계가 답변에 필요함"
    if not response["items"] and execution_draft(question, evidence):
        review.update(fulfillment="missing", abstention="excessive",
                      reason="계획과 실제 실행 미확인을 구분하여 답할 수 있음")
