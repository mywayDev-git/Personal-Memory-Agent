"""Pure routing policy: no retrieval or response generation."""

import re
from dataclasses import dataclass
from enum import StrEnum

from ..search_expressions import canonical_query


class RoutingMode(StrEnum):
    CHAT_ONLY = "CHAT_ONLY"
    MEMORY_AUGMENTED = "MEMORY_AUGMENTED"
    MEMORY_REQUIRED = "MEMORY_REQUIRED"
    EXPLICIT_SEARCH = "EXPLICIT_SEARCH"


@dataclass(frozen=True)
class Route:
    mode: RoutingMode
    reason_code: str
    query: str = ""


class RetrievalRouter:
    def decide(self, question, *, history=(), memory_enabled=True, explicit_search=False,
               classify=None, force_memory=False):
        from .policy import memory_disabled
        from .interpretation import intent

        if memory_disabled(question):
            return Route(RoutingMode.CHAT_ONLY, "MEMORY_REFUSED")
        if not memory_enabled:
            return Route(RoutingMode.CHAT_ONLY, "MEMORY_DISABLED")
        if explicit_search:
            return Route(RoutingMode.EXPLICIT_SEARCH, "SEARCH_BUTTON", question)
        if force_memory and not history:
            return Route(RoutingMode.MEMORY_REQUIRED, "USER_MEMORY_MODE", question)
        if re.fullmatch(r"(?:안녕(?:하세요)?|고마워|감사합니다|hello|hi)[!?.\s]*", question, re.I):
            return Route(RoutingMode.CHAT_ONLY, "GREETING")
        if intent(question) in {"resume", "progress", "experience", "reconsider", "next_step"}:
            return Route(RoutingMode.MEMORY_AUGMENTED, "MEMORY_CONTINUITY", question)
        if re.search(r"검색\s*해|찾아\s*줘|기록에서|기억에서", question):
            return Route(RoutingMode.MEMORY_REQUIRED, "EXPLICIT_RECALL", question)
        if re.search(r"전에|그때|지난번|했지|했었|뭐\s*했|줬|갔|봤|내가|우리\s*(?:회의|프로젝트)", question):
            return Route(RoutingMode.MEMORY_REQUIRED, "PERSONAL_HISTORY", question)
        if history and re.search(r"^(?:그건|그걸|그 사람|그러면|그럼|왜|언제|어디)", question):
            latest = history[-1].get("response", {})
            mode = latest.get("conversation_mode", latest.get("conversation_type"))
            if mode in {"memory", "mixed", "hybrid"}:
                return Route(RoutingMode.MEMORY_REQUIRED, "MEMORY_FOLLOWUP", question)
        if re.search(r"일반적으로|일반적인|python.*(?:뭐|설명)|광합성|번역해", canonical_query(question)):
            return Route(RoutingMode.CHAT_ONLY, "GENERAL_KNOWLEDGE")
        if classify is not None:
            try:
                value = classify()
                mode = {"general": RoutingMode.CHAT_ONLY, "memory": RoutingMode.MEMORY_REQUIRED,
                        "mixed": RoutingMode.MEMORY_AUGMENTED,
                        "hybrid": RoutingMode.MEMORY_AUGMENTED}[value["mode"]]
                return Route(mode, "MODEL_CLASSIFIED", value.get("query", ""))
            except Exception:
                return Route(RoutingMode.MEMORY_REQUIRED, "CLASSIFIER_FAILED", question)
        return Route(RoutingMode.MEMORY_REQUIRED, "CONSERVATIVE_FALLBACK", question)
