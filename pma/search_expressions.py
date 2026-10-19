"""Shared, offset-preserving search expressions and bounded query expansion."""

import re
from dataclasses import dataclass
from datetime import date

PARTICLES = (
    "이라는", "이란", "과는", "와는", "에는", "란",
    "에서부터", "으로부터", "에게서", "에서는", "으로는", "에게는", "에서도",
    "까지는", "부터는", "으로도", "에서도", "에게도", "로부터", "로는", "로도",
    "에서", "에게", "한테", "으로", "까지", "부터", "처럼", "보다",
    "에", "은", "는", "이", "가", "을", "를", "와", "과", "도", "만", "로",
)
GROUPS = {
    "python": ("python", "파이썬", "파이선"),
    "api": ("api", "에이피아이", "에이 피 아이"),
    "machine learning": ("machine learning", "머신러닝", "머신 러닝", "기계 학습", "기계학습"),
    "deep learning": ("deep learning", "딥러닝", "딥 러닝", "심층 학습", "심층학습"),
}
ALIASES = {alias: concept for concept, aliases in GROUPS.items() for alias in aliases}


def width_normalize(text):
    # One code point in, one code point out: offsets remain original-text offsets.
    return "".join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E
                   else " " if c == "\u3000" else c for c in text)


def fold(text):
    return width_normalize(text).casefold()


def alias_parts(word):
    word = re.sub(r"\s+", " ", fold(word))
    if word in ALIASES:
        return ALIASES[word], ""
    for suffix in PARTICLES:
        if word.endswith(suffix) and word[:-len(suffix)] in ALIASES:
            return ALIASES[word[:-len(suffix)]], suffix
    return None, ""


def canonical_word(word):
    concept, _ = alias_parts(word)
    return concept or fold(word)


_suffix = "(?:" + "|".join(re.escape(s) for s in PARTICLES) + ")?"
_aliases = "|".join(re.escape(a).replace(r"\ ", r"\s+")
                     for a in sorted(ALIASES, key=len, reverse=True))
# Keep punctuation inside technical identifiers. Never reduce C++ or C# to C.
_pattern = re.compile(
    r"(?<!\w)(?:" + _aliases + r")" + _suffix + r"(?!\w)"
    r"|(?<!\w)(?:[a-z][a-z0-9_]*(?:\++|\#+)[a-z0-9_]*|\.[a-z][a-z0-9_]*|"
    r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)" + _suffix + r"(?!\w)"
    r"|[\w가-힣]+", re.I,
)


@dataclass(frozen=True)
class Token:
    text: str
    begin: int
    stop: int

    def group(self):
        return self.text

    def start(self):
        return self.begin

    def end(self):
        return self.stop


class Tokenizer:
    def finditer(self, text):
        return (Token(text[m.start():m.end()], m.start(), m.end())
                for m in _pattern.finditer(width_normalize(text)))

    def findall(self, text):
        return [token.group() for token in self.finditer(text)]


TOKEN = Tokenizer()


def token_spans(text):
    """Native matcher contract: original offsets/quote and normalized spelling."""
    return [(t.start(), t.end(), t.group(), fold(t.group())) for t in TOKEN.finditer(text)]


def canonical_query(question):
    pieces, cursor = [], 0
    for token in TOKEN.finditer(question):
        concept, suffix = alias_parts(token.group())
        pieces.extend((width_normalize(question[cursor:token.start()]),
                       (concept + suffix) if concept else fold(token.group())))
        cursor = token.end()
    pieces.append(width_normalize(question[cursor:]))
    return "".join(pieces)


def event_text(text):
    """Mask registered topic nouns even with an unrecognised Korean ending.

    Masking is only for event detection; retrieval tokens and source offsets stay intact.
    """
    masked = re.sub(r"(?<!\w)(?:" + _aliases + r")", lambda m: " " * len(m[0]),
                    width_normalize(text), flags=re.I)
    # The contrast marker "A와 달리 B" is not a running action.
    return re.sub(r"(?:과|와)(?:는)?\s+달리(?=\s|[,.!?]|$)",
                  lambda m: " " * len(m[0]), masked)


# Reviewed lexical correspondences, not model-learned aliases or entity identities.
# Unknown proposals remain unused; the original multilingual embedding still runs.
TRANSLATIONS = (
    ("쿠버네티스", "kubernetes"), ("자바스크립트", "javascript"),
    ("영수증", "receipt"), ("냉장고", "refrigerator", "fridge"),
    ("예산", "budget"), ("항공권", "flight ticket"),
    ("근력 운동", "근력 훈련", "strength training"), ("식물", "plant"), ("행성", "planet"),
    ("학습", "공부", "learning", "studying"),
    ("자료", "내용"),
    ("코드", "code", "chord", "cord"), ("자바", "java"),
    ("게이트웨이", "gateway"),
)


def lexical_key(text):
    return re.sub(r"\s+", " ", fold(text)).strip()


def changed_parts(before, after):
    a, b = lexical_key(before).split(), lexical_key(after).split()
    while a and b and a[0] == b[0]:
        a.pop(0)
        b.pop(0)
    while a and b and a[-1] == b[-1]:
        a.pop()
        b.pop()
    return " ".join(a), " ".join(b)


def correspondence(before, after):
    """Return a verified retrieval kind, never trust the model's kind for weight."""
    left, right = changed_parts(before, after)
    if not left or not right or not any(left in group and right in group
                                       for group in (*GROUPS.values(), *TRANSLATIONS)):
        return None
    return "translation" if crosses_languages(before, after) else "similar"


def noun_parts(text):
    """Split only reviewed nouns, never guess a stem from an arbitrary name."""
    key = lexical_key(text)
    nouns = set(ALIASES) | {word for group in TRANSLATIONS for word in group}
    if key in nouns:
        return text, ""
    for suffix in sorted(PARTICLES, key=len, reverse=True):
        if key.endswith(suffix) and key[:-len(suffix)] in nouns:
            return text[:-len(suffix)], text[-len(suffix):]
    return text, ""


def identifier_spans(text):
    # Includes named aliases embedded inside an opaque key/path (API-key, api/v1).
    for match in re.finditer(r"(?<!\w)[A-Za-z][A-Za-z0-9_]*(?:[-/:.][A-Za-z0-9_]+)+", width_normalize(text)):
        yield match.start(), match.end()
    for token in TOKEN.finditer(text):
        value = fold(token.group())
        if any(c in value for c in ".+#_") or re.search(r"[a-z].*\d|\d.*[a-z]", value):
            yield token.start(), token.end()


def entity_overlap(text, entity):
    """Whole entity, optionally followed by a known Korean particle."""
    return bool(re.search(r"(?<!\w)" + re.escape(fold(entity)) + _suffix + r"(?!\w)", fold(text)))


def keyword_weight(match):
    return 1.0 if match["kind"] == "exact" or alias_parts(match["quote"])[0] else 0.7


def describe_matches(matches):
    return [{**m, "match_type": "alias" if alias_parts(m["quote"])[0]
             and fold(m["quote"]) != fold(m["term"]) else m["kind"]} for m in matches]


EXPANSION_SCHEMA = {
    "type": "array", "maxItems": 4,
    "items": {
        "type": "object", "additionalProperties": False,
        "required": ["start", "end", "before", "after", "kind"],
        "properties": {
            "start": {"type": "integer", "minimum": 0},
            "end": {"type": "integer", "minimum": 1},
            "before": {"type": "string", "minLength": 1, "maxLength": 60},
            "after": {"type": "string", "minLength": 1, "maxLength": 60},
            "kind": {"enum": ["translation", "transliteration", "similar"]},
        },
    },
}

# Conservative runtime checks supplement (and do not trust) the model's policy.
_protected = re.compile(
    r"\d|(?:않|없|아니|못|취소|완료|예정|계획|실행|어제|오늘|내일|지난|다음|"
    r"이전|이후|부터|까지|이상|이하|초과|미만)|"
    r"\b(?:안|못|not|no|never|without|cancel(?:s|led|ing|lation)?|"
    r"complete(?:s|d|ly)?|plan(?:s|ned|ning)?|"
    r"before|after|since|until|yesterday|today|tomorrow)\b", re.I)
_ambiguous = {"java", "자바", "code", "cord", "chord", "코드"}
_contexts = {
    "development": re.compile(r"개발|프로그래|언어|컴파일|리뷰|배포|develop|program|language|review", re.I),
    "music": re.compile(r"음악|화음|진행|악보|music|chord|progression", re.I),
    "wire": re.compile(r"전선|전기|케이블|wire|electric|cable", re.I),
    "travel": re.compile(r"섬|여행|island|travel", re.I),
}


def unambiguous_context(before, after, context):
    java = fold(before) in {"java", "자바"}
    relevant = ("development", "travel") if java else ("development", "music", "wire")
    meanings = [meaning for meaning in relevant if _contexts[meaning].search(context)]
    if len(meanings) != 1:
        return False
    meaning = meanings[0]
    if java:
        # Travel implies a named place; it needs an approved entity alias, not a lexical translation.
        return meaning == "development" and not re.search(r"섬|island", after, re.I)
    # Korean 코드 is ambiguous; require the English spelling to agree with the
    # explicit context. English spellings themselves retain their own sense.
    expected = {"development": "code", "music": "chord", "wire": "cord"}[meaning]
    if fold(before) in {"code", "chord", "cord"} and fold(before) != expected:
        return False
    if fold(after) in {"code", "chord", "cord"} and fold(after) != expected:
        return False
    return fold(before) != "코드" or bool(re.search(r"\b" + expected + r"\b", after, re.I))


def crosses_languages(before, after):
    left, right = TOKEN.findall(before), TOKEN.findall(after)
    common = {fold(token) for token in left} & {fold(token) for token in right}
    left = " ".join(token for token in left if fold(token) not in common)
    right = " ".join(token for token in right if fold(token) not in common)
    def language(text):
        korean, english = bool(re.search(r"[가-힣]", text)), bool(re.search(r"[A-Za-z]", text))
        return "ko" if korean and not english else "en" if english and not korean else None
    return {language(left), language(right)} == {"ko", "en"}


def location_terms(question, rows):
    """Require travel wording or corpus evidence of a visit place for hard filters."""
    known = {r["fact"].get("object_key") for r in rows
             if r.get("fact") and r["fact"].get("relation") == "visit"}
    locations = []
    for match in re.finditer(r"([가-힣A-Za-z]+?)(에서|(?:에\s*)?\s+가서)", question):
        place = match.group(1)
        if alias_parts(place)[0]:
            continue
        if place in known or re.match(r"\s*(?:갔|다녀|가서|방문|여행)", question[match.end():]) or "가서" in match.group(2):
            locations.append(place)
    return locations


def build_expansion(question, edits, rows, understood, *, today=None, original_plan=None):
    result = {"status": "none", "original_query": question, "edits": [],
              "queries": [], "searched": False, "reason": None, "rejected": [],
              "ignored": [], "verification": "reviewed_lexicon_v1"}
    if edits is None or edits == []:
        return result
    from scripts.memory_agent.validator import schema_errors
    if schema_errors(edits, EXPANSION_SCHEMA):
        return {**result, "status": "rejected", "reason": "invalid_expansions"}
    protected = set(location_terms(question, rows))
    for row in rows:
        fact = row.get("fact") or {}
        protected.update(v for v in (fact.get("actor"), fact.get("recipient"),
                         fact.get("counterparty"), *fact.get("participants", []))
                         if v and v != "self")
        if fact.get("relation") == "visit" and fact.get("object_key"):
            protected.add(fact["object_key"])
    for role in ("actor", "recipient"):
        if (understood.get(role) or {}).get("value"):
            protected.add(understood[role]["value"])
    from .facts import query_plan
    today = today or date.today().isoformat()
    original_plan = original_plan or query_plan(question, understood, today)
    proposals = {}
    for edit in edits:
        start, end, before, after = (edit[k] for k in ("start", "end", "before", "after"))
        resolved = False
        # Models often count Korean syllables incorrectly. An exact quote that
        # occurs once can establish its own span without guessing any wording.
        if (not 0 <= start < end <= len(question) or question[start:end] != before) and question.count(before) == 1:
            start = question.index(before)
            end = start + len(before)
            resolved = True
        reason = None
        suffix = ""
        stem_before, stem_after = before, after
        if not 0 <= start < end <= len(question) or question[start:end] != before:
            reason = "invalid_span"
        elif any(start < b and a < end for a, b in identifier_spans(question)):
            reason = "protected_identifier"
        elif not after.strip() or not any(c.isalpha() for c in after):
            reason = "empty_expression"
        elif not re.fullmatch(r"[A-Za-z가-힣\s.+#_-]+", before + after) or _protected.search(before + " " + after):
            reason = "protected_expression"
        elif any(entity_overlap(before, v) or entity_overlap(after, v) for v in protected):
            reason = "protected_entity"
        if reason is None:
            stem_before, suffix = noun_parts(before)
            if suffix:
                stem_after, after_suffix = noun_parts(after)
                if after_suffix and after_suffix != suffix:
                    reason = "changed_constraints"
            # A model may quote only the noun in a particle-bearing token. Accept
            # that exact span only for reviewed nouns; leave the original suffix.
            if (start and question[start-1].isalnum()):
                reason = "partial_word"
            if end < len(question) and question[end].isalnum():
                tail = next((t for t in TOKEN.finditer(question)
                             if t.start() == start and t.end() >= end), None)
                if not tail or question[end:tail.end()] not in PARTICLES or noun_parts(tail.group())[0] != before:
                    reason = "partial_word"
            changed_before, changed_after = changed_parts(stem_before, stem_after)
            context = re.sub(re.escape(changed_before), "", fold(question), count=1)
            if reason is None and changed_before in _ambiguous and not unambiguous_context(
                    changed_before, changed_after, context):
                reason = "ambiguous_expression"
            elif reason is None and edit["kind"] in {"translation", "transliteration"} and not crosses_languages(stem_before, stem_after):
                reason = "language_mismatch"
        if reason is None and lexical_key(before) == lexical_key(after):
            result["ignored"].append({"before": before, "reason": "equivalent_original"})
            continue
        verified_kind = correspondence(stem_before, stem_after) if reason is None else None
        if reason is None and verified_kind is None:
            reason = "verification_required"
        replacement = stem_after + suffix
        expanded = question[:start] + replacement + question[end:]
        if reason is None and canonical_query(expanded) == canonical_query(question):
            result["ignored"].append({"before": before, "reason": "equivalent_original"})
            continue
        if reason is None:
            expanded_plan = query_plan(expanded, understood, today)
            if {k:v for k,v in original_plan.items() if k != "question"} != {
                    k:v for k,v in expanded_plan.items() if k != "question"}:
                reason = "changed_constraints"
        if reason:
            result["rejected"].append({"before": before, "after": after, "kind": edit["kind"], "reason": reason})
            continue
        query = canonical_query(expanded)
        if query == canonical_query(question):
            result["ignored"].append({"before": before, "reason": "equivalent_original"})
            continue
        accepted = {**edit, "start": start, "end": end, "after": replacement,
                    "kind": verified_kind, "verification": "reviewed_lexicon_v1",
                    "span_source": "unique_quote" if resolved else "model_span"}
        item = {"query": query, "kind": verified_kind,
                "weight": 0.5 if verified_kind == "similar" else 0.8}
        key = (start, end, before, replacement)
        if query in proposals:
            result["ignored"].append({"before": before, "reason": "duplicate_query"})
        if query not in proposals or key < proposals[query][0]:
            proposals[query] = (key, accepted, item)
    for _, accepted, item in sorted(proposals.values(), key=lambda p: (-p[2]["weight"], p[2]["query"])):
        if len(result["queries"]) < 2:
            result["edits"].append(accepted)
            result["queries"].append(item)
        else:
            result["rejected"].append({"before": accepted["before"], "kind": accepted["kind"], "reason": "query_limit"})
    result["rejected"].sort(key=lambda r: (r["before"], r["kind"], r["reason"]))
    result["ignored"].sort(key=lambda r: (r["before"], r["reason"]))
    result["status"] = "applied" if result["queries"] else "rejected" if result["rejected"] else "none"
    return result
