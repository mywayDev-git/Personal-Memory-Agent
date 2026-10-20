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
