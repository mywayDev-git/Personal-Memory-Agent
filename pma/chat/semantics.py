"""Explicit event-denial checks; uncertainty about dates remains legitimate."""

import re

from ..relevance import study_topic

STOP = r"접었|그만뒀|그만두었|중단했|포기했"
DENIAL = re.compile(
    r"(?:중단(?:한|했다는|했던)?|접었다는|그만둔|포기한)\s*"
    r"(?:기록|내용|사실|증거)(?:은|는|이|가)?\s*"
    r"(?:없(?!지)|확인되지|찾을\s*수\s*없)"
)


def denies_stopping(question, text, sources):
    if not study_topic(question):
        return False
    # Only assert contradiction when an explicit affirmative stop is available.
    affirmative = any(re.search(STOP, source) and not re.search(
        r"(?:중단|포기)하지\s*않|그만두지\s*않|접지\s*않|(?:중단|포기)했다면", source
    ) for source in sources)
    return affirmative and bool(DENIAL.search(text))


def stop_record_draft(question, evidence):
    """Exact single stop sentence as a draft; normal independent review is mandatory."""
    if (not study_topic(question) or not re.search(r"중단|그만|접", question)
            or not re.search(r"기록.*(?:있|찾|알려)", question)
            or re.search(r"왜|이유|언제|날짜|현재|지금|순서|그리고|함께|모두|각각|시작|이전|이후|전후|전에|후에|기록[과와]", question)):
        return None
    from scripts.memory_agent.provenance import sentences

    from ..relevance import topic_supported

    candidates = {}
    for row in evidence:
        if not topic_supported(question, row):
            continue
        for span in sentences(row["source_text"]):
            quote = span["text"].strip()
            if re.search(r"(?:접었다|그만뒀다|그만두었다|중단했다|포기했다)[.!]?$", quote):
                candidates[(row["id"], quote)] = {"text": "기록 원문: “" + quote + "”", "citations": [row["id"]]}
    if len(candidates) != 1:
        return None
    return {"status": "answered", "items": list(candidates.values())}
