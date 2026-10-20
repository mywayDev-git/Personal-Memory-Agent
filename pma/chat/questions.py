"""Literal search clauses for a narrowly recognizable independent conjunction."""

import re

from .identity import positive_labels


def question_parts(question):
    match = re.fullmatch(
        r"(.+?직업)\s*과\s*(.+(?:이유|원인)(?:은|는|이|가)?\s*"
        r"(?:뭐야|뭐예요|무엇인가요|무엇이야|알려줘|알려주세요)?[?.!]*)", question.strip()
    )
    if not match or re.match(r"관련|관계|연관|때문|덕분|탓|인한", match[2].strip()):
        return []
    first, second = match[1].strip(), match[2].strip()
    labels = positive_labels(first)
    if len(labels) != 1:
        return []
    tail = re.sub(r"\s+", "", first.replace(labels[0], "", 1))
    if tail not in {"직업", "의직업"}:
        return []
    return [first, second]
