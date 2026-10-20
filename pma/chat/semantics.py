"""Explicit event-denial checks; uncertainty about dates remains legitimate."""

import re

from scripts.memory_agent.provenance import sentences

from ..relevance import study_topic

LEARNING_STOP = re.compile(
    r"(?:공부|학습)(?:을|를|은|는)?\s*"
    r"(?:(?:완전히|결국|잠시|아예|이미)\s*)?"
    r"(?:접었|그만뒀|그만두었|중단했|포기했)(?:다|어(?:요)?|습니다|음)[.!?]?$"
)
TEMPORAL_SCOPE = re.compile(r"현재|지금|최근|최초|마지막|처음|당시|올해|작년|지난|이번|오늘|어제|내일|시점|\d")
DENIAL = re.compile(
    r"(?:중단(?:한|했다는|했던)?|접었다는|그만둔|포기한)\s*"
    r"(?:기록|내용|사실|증거)(?:은|는|이|가)?\s*"
    r"(?:없(?!지)|확인되지|찾을\s*수\s*없)"
)


def denies_stopping(question, text, sources):
    if not study_topic(question):
        return False
    # Only assert contradiction when an explicit affirmative stop is available.
    affirmative = any(LEARNING_STOP.search(span["text"].strip())
                      for source in sources for span in sentences(source))
    if not affirmative or TEMPORAL_SCOPE.search(question):
        return False
    for match in DENIAL.finditer(text):
        prefix = re.split(r"[.!?\n]", text[:match.start()])[-1]
        if not TEMPORAL_SCOPE.search(prefix):
            return True
    return False


def stop_record_draft(question, evidence):
    """Exact single stop sentence as a draft; normal independent review is mandatory."""
    stop_question = re.search(
        r"(?:공부|학습).{0,8}(?:중단(?:한|했|하|된|되)|중단(?=\s*기록)|그만(?:둔|뒀|두)|접(?:은|었)|포기(?:한|했|하))",
        question,
    )
    if (not study_topic(question) or not stop_question
            or not re.search(r"기록.*(?:있|찾|알려)", question)
            or TEMPORAL_SCOPE.search(question)
            or re.search(r"지\s*않|아닌|아니|말고|제외|안\s*(?:접|그만|중단|포기)", question)
            or re.search(r"왜|이유|언제|날짜|순서|그리고|함께|모두|각각|시작|이전|이후|전후|전에|후에|기록[과와]", question)):
        return None
    from ..relevance import topic_supported

    candidates = {}
    for row in evidence:
        if not topic_supported(question, row):
            continue
        for span in sentences(row["source_text"]):
            quote = span["text"].strip()
            if len(quote) <= 300 and LEARNING_STOP.search(quote):
                candidates[(row["id"], quote)] = {"text": "기록 원문: “" + quote + "”", "citations": [row["id"]]}
    if len(candidates) != 1:
        return None
    return {"status": "answered", "items": list(candidates.values())}
