"""Shared, offset-preserving search expressions and bounded query expansion."""

import re
from dataclasses import dataclass

PARTICLES = (
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
    r"|(?<!\w)(?:[a-z][a-z0-9_]*(?:\++|\#+)|\.[a-z][a-z0-9_]*|"
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
    r"\b(?:안|못|not|no|never|without|cancel\w*|complete\w*|plan\w*|"
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
        return not re.search(r"섬|island" if meaning == "development" else r"언어|program|language", after, re.I)
    # Korean 코드 is ambiguous; require the English spelling to agree with the
    # explicit context. English spellings themselves retain their own sense.
    expected = {"development": "code", "music": "chord", "wire": "cord"}[meaning]
    if fold(before) in {"code", "chord", "cord"} and fold(before) != expected:
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


def build_expansion(question, edits, rows, understood):
    result = {"status": "none", "original_query": question, "edits": [],
              "queries": [], "searched": False, "reason": None, "rejected": []}
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
    seen = {canonical_query(question)}
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
        if not 0 <= start < end <= len(question) or question[start:end] != before:
            reason = "invalid_span"
        elif (start and question[start-1].isalnum()) or (end < len(question) and question[end].isalnum()):
            reason = "partial_word"
        elif not re.fullmatch(r"[A-Za-z가-힣\s.+#_-]+", before + after) or _protected.search(before + " " + after):
            reason = "protected_expression"
        elif any(fold(v) in fold(before) or fold(v) in fold(after) for v in protected):
            reason = "protected_entity"
        elif fold(before) in _ambiguous and not unambiguous_context(before, after, question[:start] + question[end:]):
            reason = "ambiguous_expression"
        elif edit["kind"] in {"translation", "transliteration"} and not crosses_languages(before, after):
            reason = "language_mismatch"
        else:
            from .facts import query_plan
            original_plan = query_plan(question, understood, "2000-01-01")
            expanded = question[:start] + after + question[end:]
            expanded_plan = query_plan(expanded, understood, "2000-01-01")
            if {k:v for k,v in original_plan.items() if k != "question"} != {
                    k:v for k,v in expanded_plan.items() if k != "question"}:
                reason = "changed_constraints"
        if reason:
            result["rejected"].append({"before": before, "kind": edit["kind"], "reason": reason})
            continue
        query = canonical_query(question[:start] + after + question[end:])
        if query in seen:
            continue
        if len(result["queries"]) >= 2:
            result["rejected"].append({"before": before, "kind": edit["kind"], "reason": "query_limit"})
            continue
        seen.add(query)
        result["edits"].append({**edit, "start": start, "end": end,
                                "span_source": "unique_quote" if resolved else "model_span"})
        result["queries"].append({"query": query, "kind": edit["kind"],
                                  "weight": 0.5 if edit["kind"] == "similar" else 0.8})
    result["status"] = "applied" if result["queries"] else "rejected" if result["rejected"] else "none"
    return result
