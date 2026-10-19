"""Source-based limits for questions with an explicit study topic."""

import re

from .search_expressions import ALIASES, PARTICLES, canonical_query, noun_parts


def study_topic(question):
    stem, _ = noun_parts(question.strip().rstrip("?!。.!"))
    canonical = canonical_query(stem)
    if canonical in set(ALIASES.values()):
        return canonical
    # Limit this guard to a clearly stated topic immediately before study; broad
    # questions, people, and follow-up references continue through normal review.
    masked = question
    for alias in sorted(ALIASES, key=len, reverse=True):
        masked = re.sub(re.escape(alias), lambda m: " " * len(m[0]), masked, flags=re.I)
    study = re.search(r"공부|(?<![가-힣])(?:학습|배운|배웠|배우)", masked)
    if not study:
        return None
    prefix = question[:study.start()]
    suffix = "|".join(map(re.escape, PARTICLES))
    for alias in sorted(ALIASES, key=len, reverse=True):
        if re.search(r"(?:^|\s)" + re.escape(alias) + r"(?:" + suffix +
                     r")?(?:\s*(?:관련된|관련|대한|했던|한|기록))*\s*$", prefix, re.I):
            return ALIASES[alias]
    match = re.search(r"([A-Za-z][A-Za-z0-9.+#_-]*|[가-힣]+)(?:을|를)?\s*(?:공부|학습|배운|배웠|배우)", question, re.I)
    if not match:
        return None
    topic = match[1]
    if topic.endswith(("을", "를")):
        topic = topic[:-1]
    if topic in {"내가", "나는", "나", "그거", "그것", "무엇", "뭘", "어떤", "최근", "어제", "오늘", "했던", "관련된", "관련", "대한", "한"}:
        return None
    return canonical_query(topic)


def topic_supported(question, row):
    topic = study_topic(question)
    if not topic:
        return True
    source = row.get("source_text", row.get("text", ""))
    # Keep notes from the same study passage (e.g. asyncio.gather), but not a
    # different paragraph mentioning an unrelated activity in a long document.
    quotes = [e.get("quote", "") for e in row.get("evidence", [])]
    for paragraph in re.split(r"\n\s*\n", source):
        folded = canonical_query(paragraph)
        if re.search(r"(?<![a-z0-9가-힣])" + re.escape(topic) + r"(?![a-z0-9])", folded):
            if not quotes or any(q and q in paragraph for q in quotes):
                return True
    return False
