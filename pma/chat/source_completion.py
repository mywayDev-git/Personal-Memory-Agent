"""Closed extractive proposals for a fresh independent completion check."""

import re
from datetime import date

from .source_fact import source_fact_draft, source_date_draft

ABSOLUTE = r'(?:\d{4}(?:년\s*\d{1,2}월\s*\d{1,2}일|-\d{2}-\d{2})\s*)?'
WHAT = re.compile(ABSOLUTE + r'([가-힣]{2,5})(?:에게|한테)\s*(?:무엇|뭘|뭐|어떤\s*물건)(?:을|를)?\s*(?:선물했(?:어|나요|습니까)?|줬(?:어|나요)?|주었(?:어|나요)?)[?.!]*')
WHEN = re.compile(r'([가-힣]{2,5})(?:에게|한테)\s+.{1,30}?(?:을|를)\s*(?:선물한|준|주었던|선물했던)\s*날짜(?:는|가)?[?.!]*')


def draft(question, evidence, settings):
    """No inferred referent, missing recipient, relative date or extra clause."""
    if len(evidence)!=1:
        return None  # Never discard other candidates to make this shortcut fit.
    question=question.strip()
    match=WHAT.fullmatch(question)
    result=(source_fact_draft(question,evidence) if match and settings.source_fact_drafts else None)
    if match is None:
        match=WHEN.fullmatch(question)
        result=source_date_draft(question,evidence) if match and settings.source_date_drafts else None
    if match is None or result is None:
        return None
    recipient=match[1]
    rows={row['id']:row for row in evidence}
    cited={cid for item in result['items'] for cid in item['citations']}
    # A giver's name elsewhere in the same record cannot stand for its recipient.
    if not all(re.search(r'(?<![가-힣])'+re.escape(recipient)+r'(?:에게|한테)', rows[cid]['source_text']) for cid in cited):
        return None
    requested=list(re.finditer(r'(\d{4})(?:년\s*|-)(\d{1,2})(?:월\s*|-)(\d{1,2})(?:일)?',question))
    if requested:
        if len(requested)!=1:
            return None
        try:
            day=date(*(int(v) for v in requested[0].groups())).isoformat()
        except ValueError:
            return None
        for cid in cited:
            fact=rows[cid].get('fact') or {}
            event=fact.get('event_time') or {}
            source_dates=list(re.finditer(r'(\d{4})(?:년\s*|-)(\d{1,2})(?:월\s*|-)(\d{1,2})(?:일)?',rows[cid]['source_text']))
            if len(source_dates)!=1:
                return None
            try:
                source_day=date(*(int(v) for v in source_dates[0].groups())).isoformat()
            except ValueError:
                return None
            if source_day!=day:
                return None
            if (event.get('start')!=day or event.get('end') or event.get('certainty')!='explicit'
                    or event.get('precision')!='day' or (fact.get('time_validation') or {}).get('status')!='verified'):
                return None
    return result
