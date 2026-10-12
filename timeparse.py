"""한국어 시간 표현을 날짜 범위로 바꾸는 규칙 기반 파서 (LLM 불필요).

보고서 F-08(시간 정보 처리)과 F-01(기록에 포함된 날짜와 실제 작성 날짜 구분)에 쓴다.
- 질문 분석: "작년에 이직 고민한 이유?" -> 2025-01-01 ~ 2025-12-31 (DB 시간 검색 조건)
- 일기 추출: "어제 팀원들과 회의" + 작성일 -> 사건 날짜

날짜 계산은 LLM이 틀리기 쉬워서 코드로 처리하고, LLM은 의미 파악(사람, 주제, 의도)에만 쓴다.

사용법
    python timeparse.py                      # 내장 테스트 실행
    python timeparse.py "작년에 이직 고민" 2026-10-10   # 문장과 기준일(생략하면 오늘)

약속한 해석 규칙
- 주(week)는 월요일 시작. "N월 둘째 주"는 7일 단위(1~7일 첫째, 8~14일 둘째, ...), 마지막 주는 22일~말일.
- "최근", "요즘"은 기준일 포함 최근 30일.
- 요일만 말하면 기준일 이전의 가장 가까운 그 요일("화요일에" -> 지난 화요일).
- 연도 없는 "N월"은 기준일 이전이면 올해, 가까운 미래(약 4개월 이내)면 올해, 그보다 멀면 작년.
  질문처럼 과거를 묻는 경우에는 prefer="past"를 쓴다.
"""
from __future__ import annotations

import calendar
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
ORDINAL = {"첫째": 1, "둘째": 2, "셋째": 3, "넷째": 4, "다섯째": 5, "마지막": -1}
WEEK_OFFSET = {"이번": 0, "지난": -1, "저번": -1, "다음": 1}
YEAR_OFFSET = {"재작년": -2, "작년": -1, "올해": 0, "내년": 1}
DAY_WORDS = {"그저께": -2, "엊그제": -2, "그제": -2, "어제": -1, "오늘": 0, "내일": 1, "모레": 2}
AGO_WORDS = {
    "하루": (1, "일"), "이틀": (2, "일"), "사흘": (3, "일"), "나흘": (4, "일"),
    "일주일": (1, "주"), "이주일": (2, "주"), "한주": (1, "주"), "두주": (2, "주"),
    "한달": (1, "달"), "두달": (2, "달"), "세달": (3, "달"), "석달": (3, "달"),
    "한해": (1, "년"),
}


@dataclass
class Span:
    text: str        # 문장에서 찾은 원래 표현
    start: date
    end: date
    kind: str        # day | week | month | year | range

    def iso(self) -> tuple[str, str]:
        return self.start.isoformat(), self.end.isoformat()


# ---------- 날짜 계산 도구 ----------
def _week(d: date) -> tuple[date, date]:
    s = d - timedelta(days=d.weekday())
    return s, s + timedelta(days=6)


def _month(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def _add_months(d: date, n: int) -> date:
    y, m0 = divmod(d.year * 12 + d.month - 1 + n, 12)
    m = m0 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _year_for(today: date, month: int, day: int | None, prefer: str) -> int:
    """연도가 없는 'N월(M일)'의 연도를 정한다."""
    start = date(today.year, month, day or 1)
    if start <= today:
        return today.year
    if prefer == "past":
        return today.year - 1
    if prefer == "future":
        return today.year
    return today.year if (start - today).days <= 120 else today.year - 1


def _shift(today: date, n: int, unit: str) -> date:
    if unit == "일":
        return today - timedelta(days=n)
    if unit in ("주", "주일"):
        return today - timedelta(weeks=n)
    if unit in ("개월", "달"):
        return _add_months(today, -n)
    return date(today.year - n, today.month, min(today.day, calendar.monthrange(today.year - n, today.month)[1]))


# ---------- 규칙별 처리 (Span 재료 (start, end, kind) 를 돌려준다) ----------
def _h_full(m, today, prefer):
    x = date(int(m[1]), int(m[2]), int(m[3]))
    return x, x, "day"


def _h_md(m, today, prefer):
    mo, d = int(m[1]), int(m[2])
    x = date(_year_for(today, mo, d, prefer), mo, d)
    return x, x, "day"


def _h_month_week(m, today, prefer):
    mo, n = int(m[1]), ORDINAL[m[2]]
    y = _year_for(today, mo, None, prefer)
    last = calendar.monthrange(y, mo)[1]
    if n == -1:
        return date(y, mo, 22), date(y, mo, last), "week"
    first = 7 * (n - 1) + 1
    if first > last:
        return None
    return date(y, mo, first), date(y, mo, min(first + 6, last)), "week"


def _h_yearword_month(m, today, prefer):
    y = today.year + YEAR_OFFSET[m[1]]
    s, e = _month(y, int(m[2]))
    return s, e, "month"


def _h_year_month(m, today, prefer):
    s, e = _month(int(m[1]), int(m[2]))
    return s, e, "month"


def _h_year4(m, today, prefer):
    y = int(m[1])
    return date(y, 1, 1), date(y, 12, 31), "year"


def _h_month(m, today, prefer):
    mo = int(m[1])
    s, e = _month(_year_for(today, mo, None, prefer), mo)
    return s, e, "month"


def _h_yearword(m, today, prefer):
    y = today.year + YEAR_OFFSET[m[1]]
    return date(y, 1, 1), date(y, 12, 31), "year"


def _h_relmonth(m, today, prefer):
    base = _add_months(today, WEEK_OFFSET[m[1]])
    s, e = _month(base.year, base.month)
    return s, e, "month"


def _h_week_weekday(m, today, prefer):
    s, _ = _week(today + timedelta(weeks=WEEK_OFFSET[m[1]]))
    x = s + timedelta(days=WEEKDAYS[m[2]])
    return x, x, "day"


def _h_weekend(m, today, prefer):
    s, _ = _week(today + timedelta(weeks=WEEK_OFFSET[m[1]]))
    return s + timedelta(days=5), s + timedelta(days=6), "range"


def _h_week(m, today, prefer):
    s, e = _week(today + timedelta(weeks=WEEK_OFFSET[m[1]]))
    return s, e, "week"


def _ago(n: int, unit: str, today: date):
    if unit == "일":
        x = today - timedelta(days=n)
        return x, x, "day"
    if unit in ("주", "주일"):
        s, e = _week(today - timedelta(weeks=n))
        return s, e, "week"
    if unit in ("개월", "달"):
        b = _add_months(today, -n)
        s, e = _month(b.year, b.month)
        return s, e, "month"
    return date(today.year - n, 1, 1), date(today.year - n, 12, 31), "year"


def _h_ago(m, today, prefer):
    return _ago(int(m[1]), m[2], today)


def _h_ago_word(m, today, prefer):
    n, unit = AGO_WORDS[re.sub(r"\s+", "", m[1])]
    return _ago(n, unit, today)


def _h_recent_n(m, today, prefer):
    return _shift(today, int(m[1]), m[2]), today, "range"


def _h_recent(m, today, prefer):
    return today - timedelta(days=30), today, "range"


def _h_dayword(m, today, prefer):
    x = today + timedelta(days=DAY_WORDS[m[1]])
    return x, x, "day"


def _h_weekday(m, today, prefer):
    wd = WEEKDAYS[m[1]]
    if prefer == "future":
        x = today + timedelta(days=(wd - today.weekday()) % 7 or 7)
    else:
        x = today - timedelta(days=(today.weekday() - wd) % 7 or 7)
    return x, x, "day"


def _h_weekend_alone(m, today, prefer):
    wd = today.weekday()
    if prefer == "future":
        sat = today + timedelta(days=5 - wd) if wd <= 5 else today - timedelta(days=1)
    else:
        sat = today - timedelta(days=1) if wd == 6 else today - timedelta(days=(wd + 2) % 7 if wd != 5 else 0)
    return sat, sat + timedelta(days=1), "range"


_UNIT = r"(일|주일|주|개월|달|년)"
_WK = r"(이번|지난|저번|다음)"

# 위에 있을수록 먼저 찾고, 찾은 부분은 지워서 아래 규칙이 다시 잡지 못하게 한다.
RULES = [
    (re.compile(r"(?<!\d)(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"), _h_full),
    (re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일"), _h_md),
    (re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(첫째|둘째|셋째|넷째|다섯째|마지막)\s*주"), _h_month_week),
    (re.compile(r"(재작년|작년|올해|내년)\s*(\d{1,2})\s*월"), _h_yearword_month),
    (re.compile(r"(?<!\d)(\d{4})\s*년\s*(\d{1,2})\s*월"), _h_year_month),
    (re.compile(r"(?<!\d)(\d{1,2})\s*월"), _h_month),
    (re.compile(r"(?<!\d)(\d{4})\s*년"), _h_year4),
    (re.compile(r"(재작년|작년|올해|내년)"), _h_yearword),
    (re.compile(_WK + r"\s*달"), _h_relmonth),
    (re.compile(_WK + r"\s*주\s*(월|화|수|목|금|토|일)요일"), _h_week_weekday),
    (re.compile(_WK + r"\s*주말"), _h_weekend),
    (re.compile(_WK + r"\s*주(?=$|[^가-힣]|에|는|은|도|부터|까지|동안|내|를|가|의|중|쯤)"), _h_week),
    (re.compile(r"(하루|이틀|사흘|나흘|일주일|이주일|한\s*주|두\s*주|한\s*달|두\s*달|세\s*달|석\s*달|한\s*해)\s*전"), _h_ago_word),
    (re.compile(r"(?<!\d)(\d+)\s*" + _UNIT + r"\s*전"), _h_ago),
    (re.compile(r"최근\s*(\d+)\s*" + _UNIT), _h_recent_n),
    (re.compile(r"최근|요즘|요새"), _h_recent),
    (re.compile(r"(그저께|엊그제|그제|어제|오늘|내일|모레)"), _h_dayword),
    (re.compile(r"(월|화|수|목|금|토|일)요일"), _h_weekday),
    (re.compile(r"주말"), _h_weekend_alone),
]


def find_all(text: str, today: date, prefer: str = "auto") -> list[Span]:
    """문장 안의 시간 표현을 모두 찾아 등장 순서대로 돌려준다."""
    work, found = text, []
    for rx, fn in RULES:
        for m in list(rx.finditer(work)):
            try:
                res = fn(m, today, prefer)
            except ValueError:      # 2월 30일처럼 존재하지 않는 날짜
                res = None
            if res is not None:
                found.append((m.start(), Span(text[m.start():m.end()], *res)))
            # 잘못된 날짜도 지워서, 아래 규칙이 '2월'만 따로 잡는 일을 막는다
            work = work[:m.start()] + " " * (m.end() - m.start()) + work[m.end():]
    return [s for _, s in sorted(found, key=lambda x: x[0])]


def event_span(text: str, written_at: date) -> Span:
    """일기의 사건 날짜. 본문에 이미 지난 시간 표현이 있으면 그것, 없으면 작성일.

    '내일', '다음 주', '이번 주 안에'처럼 아직 끝나지 않은 표현은 계획이므로 사건 날짜로 쓰지 않는다.
    """
    for s in find_all(text, written_at):
        if s.end <= written_at:
            return s
    return Span("", written_at, written_at, "day")


def query_range(question: str, today: date) -> Span | None:
    """질문의 시간 조건. 질문은 과거를 묻는 경우가 많아 과거 쪽으로 해석한다. 없으면 None."""
    spans = find_all(question, today, prefer="past")
    return spans[0] if spans else None


# ---------- 내장 테스트 ----------
def _selftest() -> None:
    T = date(2026, 10, 10)  # 토요일
    assert T.weekday() == 5
    D = date

    def one(text, today=T, prefer="auto"):
        r = find_all(text, today, prefer)
        assert len(r) == 1, (text, r)
        return r[0].start, r[0].end

    cases = [
        ("오늘", (D(2026, 10, 10), D(2026, 10, 10))),
        ("어제 팀원들과 회의를 했다", (D(2026, 10, 9), D(2026, 10, 9))),
        ("그저께", (D(2026, 10, 8), D(2026, 10, 8))),
        ("내일 오전 10시에 면담", (D(2026, 10, 11), D(2026, 10, 11))),
        ("지난주 화요일", (D(2026, 9, 29), D(2026, 9, 29))),
        ("이번 주말에 본가에 내려가기로 했다", (D(2026, 10, 10), D(2026, 10, 11))),
        ("지난 주말", (D(2026, 10, 3), D(2026, 10, 4))),
        ("지난주", (D(2026, 9, 28), D(2026, 10, 4))),
        ("다음 주에도 같이 풀기로 했다", (D(2026, 10, 12), D(2026, 10, 18))),
        ("이번 주 안에 공약을 정리해야 한다", (D(2026, 10, 5), D(2026, 10, 11))),
        ("지난달", (D(2026, 9, 1), D(2026, 9, 30))),
        ("이번 달", (D(2026, 10, 1), D(2026, 10, 31))),
        ("작년에 이직을 고민했던 이유", (D(2025, 1, 1), D(2025, 12, 31))),
        ("작년 3월", (D(2025, 3, 1), D(2025, 3, 31))),
        ("올해 9월", (D(2026, 9, 1), D(2026, 9, 30))),
        ("11월 둘째 주에 가기로 했고", (D(2026, 11, 8), D(2026, 11, 14))),
        ("3월에 시험을 봤다", (D(2026, 3, 1), D(2026, 3, 31))),
        ("12월 25일", (D(2026, 12, 25), D(2026, 12, 25))),
        ("2025년 9월 10일", (D(2025, 9, 10), D(2025, 9, 10))),
        ("3일 전", (D(2026, 10, 7), D(2026, 10, 7))),
        ("2주 전", (D(2026, 9, 21), D(2026, 9, 27))),
        ("한 달 전", (D(2026, 9, 1), D(2026, 9, 30))),
        ("1년 전", (D(2025, 1, 1), D(2025, 12, 31))),
        ("최근에 걱정했던 일", (D(2026, 9, 10), D(2026, 10, 10))),
        ("최근 3일", (D(2026, 10, 7), D(2026, 10, 10))),
        ("화요일에 시험을 봤다", (D(2026, 10, 6), D(2026, 10, 6))),
        ("토요일", (D(2026, 10, 3), D(2026, 10, 3))),
        ("주말에 가족과 할머니 댁에 다녀왔다", (D(2026, 10, 10), D(2026, 10, 11))),
    ]
    for text, want in cases:
        got = one(text)
        assert got == want, f"{text!r}: {got} != {want}"

    # 시간 표현이 아닌 문장은 잡지 않는다
    for text in ["다음 주제를 정했다", "다음 학기에 시험을 보기로 했다", "오랜만에 친구를 만났다", "학식을 먹었다"]:
        assert find_all(text, T) == [], text

    # 월요일 기준: 주말은 지난 주말, 일요일 기준: 이번 주말
    assert one("주말에", D(2026, 10, 12)) == (D(2026, 10, 10), D(2026, 10, 11))
    assert one("주말에", D(2026, 10, 11)) == (D(2026, 10, 10), D(2026, 10, 11))
    # 질문은 과거로 해석
    assert one("11월에 뭐 했지", T, "past") == (D(2025, 11, 1), D(2025, 11, 30))
    # 존재하지 않는 날짜는 무시
    assert find_all("2월 30일", T) == []

    # 여러 표현은 등장 순서대로
    r = find_all("어제 회의를 했고 다음 주에 결정하기로 했다", T)
    assert [s.text for s in r] == ["어제", "다음 주"], r

    # 일기 사건 날짜: 지난 표현은 사건 날짜, 계획 표현만 있으면 작성일
    assert event_span("어제 팀원들과 회의를 했다. 다음 주에 결정하기로 했다.", T).start == D(2026, 10, 9)
    assert event_span("내일 오전 10시에 면담이 있다.", T).start == T
    assert event_span("이번 주 안에 공약을 정리해야 한다.", T).start == T
    assert event_span("오늘 학식을 먹었다.", T).start == T
    assert event_span("지난주에 친구랑 싸웠는데 오늘 화해했다.", T).start == D(2026, 9, 28)

    # 질문 시간 조건
    q = query_range("작년에 내가 이직을 고민했던 이유가 뭐였지?", T)
    assert q and q.iso() == ("2025-01-01", "2025-12-31")
    assert query_range("민수랑 프로젝트하면서 문제가 있었나?", T) is None

    print(f"테스트 통과: 표현 {len(cases)}개 + 예외 규칙")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        _selftest()
    else:
        today = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
        spans = find_all(sys.argv[1], today)
        print(f"기준일 {today} ({'월화수목금토일'[today.weekday()]}요일)")
        for s in spans or []:
            print(f"  '{s.text}' -> {s.start} ~ {s.end} ({s.kind})")
        if not spans:
            print("  시간 표현 없음")