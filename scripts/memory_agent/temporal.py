"""Conservative per-memory normalization; never default events to writing time."""
import re
from datetime import date, datetime

import timeparse


def reference_date(value):
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()


def normalize_time(memory, reference_time):
    raw = memory['time']['raw']
    result = dict(raw=raw, start=None, end=None, precision='unknown', certainty='uncertain')
    if not raw:
        return result
    quotes = [item['quote'] for item in memory['evidence']]
    if not any(raw in quote for quote in quotes):
        raise ValueError('time.raw must occur in this memory\'s evidence')
    ref = reference_date(reference_time)
    value = raw.strip()
    # Fully qualified ISO dates are independent of reference_time.
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        try:
            parsed = date.fromisoformat(value).isoformat()
        except ValueError:
            return result
        return dict(raw=raw, start=parsed, end=parsed, precision='day', certainty='explicit')
    absolute = bool(re.match(r'^\d{4}\s*년', value))
    # Bare month/day, weekday, clock times and vague/anaphoric expressions stay unresolved.
    relative = bool(re.match(r'^(그저께|엊그제|그제|어제|오늘|내일|모레|재작년|작년|올해|내년|이번|지난|저번|다음)', value)
                    or re.fullmatch(r'(\d+\s*(일|주|주일|개월|달|년)|하루|이틀|사흘|나흘|일주일|한\s*달)\s*전', value))
    if not absolute and not relative:
        return result
    result['precision'] = 'relative' if relative else 'unknown'
    if relative and ref is None:
        return result
    # Only a whole-expression match can normalize; partial matches lose precision.
    for regex, handler in timeparse.RULES:
        match = regex.fullmatch(value)
        if match is None:
            continue
        try:
            span = handler(match, ref or date(2000, 1, 1), 'auto')
        except (ValueError, OverflowError):
            return result
        if span is None:
            return result
        start, end, kind = span
        precision = 'range' if kind == 'week' else kind
        a, b = start.isoformat(), end.isoformat()
        if kind == 'month':
            a = b = a[:7]
        elif kind == 'year':
            a = b = a[:4]
        return dict(raw=raw, start=a, end=b, precision=precision,
                    certainty='inferred' if relative else 'explicit')
    return result
