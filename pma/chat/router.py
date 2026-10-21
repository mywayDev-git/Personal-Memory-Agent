"""Pure routing policy: no retrieval or response generation."""

import re
from dataclasses import dataclass
from enum import StrEnum

from ..search_expressions import canonical_query


def social_reply(question):
    if re.fullmatch(r"(?:안녕(?:하세요)?|고마워|감사합니다|hello|hi)[!?.\s]*", question, re.I):
        return "천만에요. 또 필요할 때 이야기해 주세요." if re.search(r"고마워|감사", question) else "안녕하세요. 편하게 이야기해 주세요."
    return None


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
               classify=None, force_memory=False, has_record_reference=None):
        from .interpretation import intent
        from .policy import memory_disabled

        if memory_disabled(question):
            return Route(RoutingMode.CHAT_ONLY, "MEMORY_REFUSED")
        if not memory_enabled:
            return Route(RoutingMode.CHAT_ONLY, "MEMORY_DISABLED")
        if explicit_search:
            return Route(RoutingMode.EXPLICIT_SEARCH, "SEARCH_BUTTON", question)
        if social_reply(question):
            return Route(RoutingMode.CHAT_ONLY, "GREETING")
        if re.search(r"^(?:내|나의|내가|나는)\s*.*(?:취향|선호|혈액형)", question):
            return Route(RoutingMode.MEMORY_REQUIRED, "PERSONAL_FACT", question)
        if history and re.fullmatch(r"\s*(?:그\s*(?:내용|설명)|다시)\s*(?:을|를)?\s*(?:다시\s*)?설명해\s*줘[.!?\s]*", question):
            previous = history[-1].get("response") or {}
            if previous.get("conversation_mode", previous.get("conversation_type")) == "general":
                return Route(RoutingMode.CHAT_ONLY, "GENERAL_FOLLOWUP")
        if intent(question) == "progress" and not re.search(r"이어서|계속|다시|다음\s*단계|계획", question):
            return Route(RoutingMode.MEMORY_REQUIRED, "PROGRESS_RECALL", question)
        if intent(question) in {"resume", "progress", "experience", "reconsider", "next_step"}:
            return Route(RoutingMode.MEMORY_AUGMENTED, "MEMORY_CONTINUITY", question)
        if force_memory and not history:
            return Route(RoutingMode.MEMORY_REQUIRED, "USER_MEMORY_MODE", question)
        if (intent(question) in {"latest", "timeline"} and
                re.search(r"기록|진도|상태|결정|결과|선택|이력|과정", question)):
            return Route(RoutingMode.MEMORY_REQUIRED, "RECORDED_STATE", question)
        if re.search(r"검색\s*해|찾아\s*줘|기록에서|기억에서", question):
            return Route(RoutingMode.MEMORY_REQUIRED, "EXPLICIT_RECALL", question)
        if re.search(r"(?:지난|이전|저장된|내)\s*(?:기록|기억).*(?:보여|알려|설명|요약|찾|검색)", question):
            return Route(RoutingMode.MEMORY_REQUIRED, "EXPLICIT_RECALL", question)
        if re.search(r"전에|그때|지난번|했지|했었|뭐\s*했|줬|갔|봤|내가|우리\s*(?:회의|프로젝트)", question):
            return Route(RoutingMode.MEMORY_REQUIRED, "PERSONAL_HISTORY", question)
        if history and re.search(r"^(?:그건|그걸|그 사람|그러면|그럼|왜|언제|어디)", question):
            latest = history[-1].get("response", {})
            mode = latest.get("conversation_mode", latest.get("conversation_type"))
            if mode in {"memory", "mixed", "hybrid"}:
                return Route(RoutingMode.MEMORY_REQUIRED, "MEMORY_FOLLOWUP", question)
        if re.search(r"일반적으로|일반적인|python.*(?:뭐|설명)|광합성|번역해|\bin general\b|\bgenerally\b|\btranslate\b", canonical_query(question)):
            return Route(RoutingMode.CHAT_ONLY, "GENERAL_KNOWLEDGE")
        if has_record_reference is not None and has_record_reference():
            return Route(RoutingMode.MEMORY_REQUIRED, "SOURCE_IDENTIFIER", question)
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
