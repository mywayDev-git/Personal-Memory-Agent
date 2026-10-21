"""Server-owned complete source spans; models select identifiers, not invented quotes."""

import re
from scripts.memory_agent.provenance import sentences

DIRECTIVE_BLOCK = re.compile(r"\[\s*(?:지시|명령|시스템|system|instruction|developer)\s*[:：][^\]]*\]", re.I)
DIRECTIVE_END = re.compile(r"(?:답하라|대답하라|대답해|출력하라|무시하라|말해|따르라)[.!?\s\]”\"']*$")


def instruction_span(text):
    return bool(DIRECTIVE_BLOCK.search(text) or DIRECTIVE_END.search(text) or
                re.match(r"\s*(?:system|instruction|developer)\s*:", text, re.I))


def source_units(text):
    """Keep inline instructions separate without dropping any original text."""
    cursor = 0
    for match in DIRECTIVE_BLOCK.finditer(text):
        yield from (s["text"].strip() for s in sentences(text[cursor:match.start()]) if s["text"].strip())
        yield match[0]
        cursor = match.end()
    yield from (s["text"].strip() for s in sentences(text[cursor:]) if s["text"].strip())


def verbatim_instruction_report(question, text, quotes):
    if not re.search(r"(?:지시|명령).*(?:내용|문구|무엇|뭐)|(?:어떤|무슨)\s*(?:지시|명령)", question):
        return False
    if not all(quote in text for quote in quotes):
        return False
    remainder = text
    for quote in quotes:
        remainder = remainder.replace(quote, "")
    # Permit quoting the command as a command, not an appended factual claim.
    return bool(quotes) and bool(re.fullmatch(
        r"[\s:：.‘’“”\"'\[\]()]*(?:(?:원문|기록|지시문구|지시문|지시|명령문|명령|문구|내용|에는|이라는|라는|라고|은|는|이|가|에|적혀|쓰여|있습니다|있다|입니다|이다)[\s:：.‘’“”\"'\[\]()]*)*",
        remainder))


def source_catalog(evidence):
    catalog = {}
    rows = []
    for source_index, row in enumerate(evidence):
        text = row["source_text"]
        spans = []
        # Keep punctuation and the entire sentence, including negation and qualifiers.
        for quote in source_units(text):
            if not quote:
                continue
            span_id = f"s{source_index}:{len(spans)}"
            catalog[span_id] = {"id": row["id"], "quote": quote}
            spans.append({"span_id": span_id, "text": quote,
                          **({"span_type": "untrusted_instruction"} if instruction_span(quote) else {})})
        if not spans and text.strip():
            span_id = f"s{source_index}:0"
            catalog[span_id] = {"id": row["id"], "quote": text}
            spans.append({"span_id": span_id, "text": text})
        if any(span.get("span_type") == "untrusted_instruction" for span in spans):
            for span in spans:
                span.setdefault("span_type", "source_statement")
            # Preserve every character in source_context and every stable span
            # ID. Put the factual statements after the untrusted directives so
            # the last source unit is not an instruction overriding the facts.
            spans.sort(key=lambda span: span["span_type"] != "untrusted_instruction")
        rows.append({"id": row["id"], "source_context": text, "spans": spans})
    return rows, catalog


def instruction_statement_draft(question, evidence):
    """Narrow repair proposal; the next independent review remains mandatory."""
    from ..facts import COLORS
    from ..search_expressions import entity_overlap
    from .questions import question_parts
    if (not re.search(r"색|무엇|어떤|뭐|무슨", question) or question_parts(question)
            or re.search(r"왜|이유|원인|언제|날짜|실제|실행|완료|누가|누구에게|몇|비교|모두|각각", question)):
        return None
    color = re.compile("|".join(re.escape(key) for key in sorted(set(COLORS) | set(COLORS.values()), key=len, reverse=True)))
    choices = {}
    for row in evidence:
        obj = (row.get("fact") or {}).get("object")
        if not isinstance(obj, str):
            continue
        noun = re.sub(r"\s+", " ", color.sub("", obj)).strip()
        if len(noun) < 2 or not entity_overlap(question, noun):
            continue
        sources, _ = source_catalog([row])
        units = sources[0]["spans"]
        if not any(unit.get("span_type") == "untrusted_instruction" for unit in units):
            continue
        for unit in units:
            quote = unit["text"]
            if (unit.get("span_type") != "untrusted_instruction" and len(quote) <= 1800
                    and entity_overlap(quote, noun)):
                choices[row["id"], quote] = {"text": "기록 원문: “" + quote + "”", "citations": [row["id"]]}
    if len(choices) != 1:
        return None
    return {"status": "answered", "items": list(choices.values())}
