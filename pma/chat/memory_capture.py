"""Lossless, local capture: never rewrite negation, people, dates or execution state."""

import re


def capture_intent(text):
    return bool(
        re.search(
            r"기억(?:해|해줘|해\s*둬)|저장해|앞으로.{0,80}(?:설명해줘|답해줘)|(?:기록|기억).{0,80}(?:아니라|정정|잘못)",
            text,
        )
    )


def classify(text, source="user_message"):
    if source == "assistant_message":
        return "proposal"
    if re.search(r"아니라|정정|잘못", text):
        return "correction"
    if re.search(r"결정했|결정한|채택했|하기로", text):
        return "project_decision"
    if re.search(r"앞으로|선호|좋아해|설명해줘", text):
        return "preference"
    if re.search(r"계획|예정|할 거|할거", text):
        return "plan"
    if re.search(r"가설|아마|추측", text):
        return "hypothesis"
    if re.search(r"제안|하는 게 좋|하는 것이 좋", text):
        return "proposal"
    if re.search(r"갔다|갔어|다녀왔|만났다|완료했", text):
        return "event"
    return "user_statement"


def is_reference(text):
    return bool(
        re.fullmatch(
            r"\s*(?:이거|이것|방금 결정한 (?:내용|구조))?[ .,!]*"
            r"(?:기억해(?:줘)?|저장해줘)[.!\s]*",
            text,
        )
    )
