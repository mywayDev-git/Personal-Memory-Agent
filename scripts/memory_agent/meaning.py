"""Conservative checks for explicit action reversals, shared by ingestion and answers.

These checks are deliberately incomplete: absence of a marker is not evidence of
truth. Mixed histories and uncertain/quoted actions remain for source review.
"""

import re

ACTION_PAIRS = (
    (r"시작(?:했|하|해|합|됐|되)|\b(?:started|began)\b",
     r"접었|접었다|접습니다|그만(?:두|뒀)|(?:중단|포기)(?:했|하|해|합)|\b(?:quit|stopped|gave up)\b"),
    (r"(?:(?<!불)합격|성공)(?:했|하|해|합)|\b(?:passed|succeeded)\b",
     r"(?:불합격|실패)(?:했|하|해|합)|\bfailed\b"),
    (r"(?:입사|가입)(?:했|하|해|합)|\bjoined\b",
     r"(?:퇴사|탈퇴)(?:했|하|해|합)|\bresigned\b"),
    (r"(?:구매|구입)(?:했|하|해|합)|샀(?:다|어|습)|\bbought\b",
     r"판매(?:했|하|해|합)|팔았|\bsold\b"),
)


def action_assertions(text):
    found = {}
    for family, alternatives in enumerate(ACTION_PAIRS):
        for state, pattern in enumerate(alternatives):
            for match in re.finditer(pattern, text, re.IGNORECASE):
                before, after = text[max(0, match.start()-8):match.start()], text[match.end():match.end()+20]
                if match[0].startswith("접") and re.search(
                    r"(?:종이|우산|노트북|책|지도|날개)(?:을|를)?\s*$", before
                ):
                    continue
                negative = bool(re.search(r"(?:안|못)\s*$|(?:not|never|didn't)\s*$", before, re.I)
                                or re.match(r"(?:지\s*않|진\s*않)", after))
                if re.match(r"(?:려|려고|고\s*싶|면|다면|라고|다고|라는)", after):
                    continue
                found.setdefault(family, set()).add((state, negative))
    return found


def meaning_conflict(claim, source):
    """An explicit opposite with no supporting occurrence is a contradiction."""
    original = action_assertions(source)
    for family, assertions in action_assertions(claim).items():
        allowed = original.get(family, set())
        for state, negative in assertions:
            if (state, negative) in allowed:
                continue
            if (state, not negative) in allowed:
                return True
            if not negative and (1-state, False) in allowed:
                return True
    return False


def extraction_conflicts(memories):
    issues = []
    for index, memory in enumerate(memories):
        source = "\n".join(e.get("quote", "") for e in memory.get("evidence", []))
        content, predicate = memory.get("content", ""), memory.get("predicate", "")
        if (meaning_conflict(content, source) or meaning_conflict(predicate, source)
                or meaning_conflict(content, predicate) or meaning_conflict(predicate, content)):
            issues.append({"index": index, "rule": "action_reversal"})
    return issues
