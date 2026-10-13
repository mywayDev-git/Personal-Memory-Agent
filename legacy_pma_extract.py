"""Memory Unit 생성 (보고서 F-02 기억 추출, F-03 Memory Unit, F-08 시간 처리).

기존 extract_memory.py(baseline 평가용)는 그대로 두고, 이 파일이 실제 파이프라인용이다.

역할 분담
- LLM(Qwen): 제목, 요약, 사람, 장소, 주제, 감정, 문제, 결정, 할 일, 결과
- 코드(timeparse.py): 사건 날짜. "어제", "지난주 화요일" 같은 표현을 작성일 기준으로 계산

필요한 파일: 같은 폴더의 timeparse.py
실행:  python pma_extract.py
"""
from __future__ import annotations

import time
from datetime import date

from ollama import chat
from pydantic import BaseModel

import timeparse

MODEL = "qwen3:4b-instruct"
NUM_CTX = 4096          # 모든 호출에서 같은 값으로 고정 (바뀌면 모델이 다시 올라가 느려짐)
KEEP_ALIVE = "30m"      # 모델을 메모리에 붙잡아 두어 앞부분 재사용(캐시)을 유지


class Extracted(BaseModel):
    """LLM이 채우는 칸."""
    title: str
    summary: str
    people: list[str]
    place: str
    topic: str
    emotion: str
    problem: str
    decision: str
    next_action: str
    result: str


class MemoryUnit(Extracted):
    """DB에 넘기는 최종 기억 단위. 아래 날짜 칸은 코드가 채운다."""
    written_at: str        # 작성일 (YYYY-MM-DD)
    event_start: str       # 사건 날짜 범위의 시작
    event_end: str         # 사건 날짜 범위의 끝 (하루면 시작과 같음)
    event_precision: str   # day | week | month | year | range
    event_expr: str        # 날짜를 정한 근거 표현("어제"). 없으면 "" (작성일 사용)


SYSTEM = """너는 일기에서 기억 정보를 추출하는 도구다. JSON으로만 답한다.
출력 키: title, summary, people, place, topic, emotion, problem, decision, next_action, result (people만 배열, 나머지는 문자열).
규칙:
- 일기에 적힌 내용만 쓴다. 없는 정보는 빈 문자열로 둔다(people은 빈 배열). 추측하지 않는다.
- title과 summary는 항상 채운다.
- title: 사건을 나타내는 짧은 명사구.
- summary: 일기 전체를 한 문장(60자 이내)으로 요약한다. 누가 무엇을 했는지와 중요한 결과나 결정을 담고, 일기에 없는 내용은 넣지 않는다.
- people: 일기에 나온 사람 모두. '팀원들', '엄마', '교수님' 같은 호칭도 포함한다.
- place: 일기에 장소가 직접 나온 경우만(예: 도서관, 할머니 댁). 없으면 빈 문자열.
- topic: 무엇에 대한 일인지 짧은 명사구.
- emotion: 일기에 직접 드러난 감정만.
- problem, decision, next_action, result는 일기에 그런 내용이 분명히 적힌 경우에만 쓴다. 식사, 이동, 만남, 사진 촬영 같은 단순한 일상 사실은 넣지 않는다. 확신이 없으면 빈 문자열로 둔다.
- problem: 일기에 적힌 어려움이나 문제.
- decision: 이미 내려진 결정이나 방침. 아직 결정하지 않은 것, 피드백을 받은 것, 문제가 해결된 결과는 넣지 않는다.
- next_action: 앞으로 하기로 한 일이나 예정된 일. 이미 끝난 행동(~했다, ~물어봤다)은 넣지 않는다. decision과 같은 내용을 중복해서 쓰지 않는다.
- result: 이미 일어난 일의 결과나 해결, 마무리. 아직 일어나지 않은 일은 넣지 않는다.
- 각 필드는 한국어로 짧게(한 문장 이하) 쓴다."""

EXAMPLES = [
    (
        "오늘 민수랑 점심을 먹었다. 요즘 취업 준비 때문에 불안하다는 이야기를 들어줬는데 나까지 마음이 무거워졌다. 같이 스터디를 해 보기로 했다.",
        Extracted(
            title="민수와 점심", summary="민수와 점심을 먹으며 취업 불안 이야기를 듣고 같이 스터디하기로 함",
            people=["민수"], place="", topic="취업 준비", emotion="마음이 무거움",
            problem="민수가 취업 준비로 불안해함", decision="같이 스터디를 하기로 함", next_action="", result="",
        ),
    ),
    (
        "오늘 동아리 사람들과 MT 장소를 이야기했다. 후보를 두 곳으로 줄였고, 금요일에 투표로 정하기로 했다.",
        Extracted(
            title="동아리 MT 장소 논의", summary="동아리 MT 장소 후보를 두 곳으로 줄이고 금요일 투표로 정하기로 함",
            people=["동아리 사람들"], place="", topic="MT 장소 선정", emotion="",
            problem="", decision="후보를 두 곳으로 줄임", next_action="금요일에 투표로 장소를 정함", result="",
        ),
    ),
    (
        "오늘 팀 프로젝트 발표 주제를 두고 의견이 갈렸다. 결론을 못 내서 내일 다시 모여 정하기로 했다. 답답하다.",
        Extracted(
            title="발표 주제 논의", summary="발표 주제로 의견이 갈려 내일 다시 모여 정하기로 함",
            people=[], place="", topic="발표 주제 선정", emotion="답답함",
            problem="의견이 갈려 결론을 못 냄", decision="", next_action="내일 다시 모여 주제를 정함", result="",
        ),
    ),
    (
        "오늘 자전거 바퀴가 터져서 수리점에 맡겼다. 타이어 펑크였고 만 원에 고쳤다. 별일 아니라 다행이다.",
        Extracted(
            title="자전거 수리", summary="자전거 타이어 펑크를 수리점에서 만 원에 고침",
            people=[], place="수리점", topic="자전거 수리", emotion="다행스러움",
            problem="자전거 타이어 펑크", decision="", next_action="", result="수리점에서 만 원에 고침",
        ),
    ),
    (
        "오늘 점심에 혼자 라면을 끓여 먹고 빨래를 했다. 저녁에는 동네를 한 바퀴 걸었다.",
        Extracted(
            title="평범한 하루", summary="라면을 먹고 빨래와 산책을 한 평범한 하루",
            people=[], place="", topic="일상", emotion="",
            problem="", decision="", next_action="", result="",
        ),
    ),
]


def build_messages(diary: str, written_at: str) -> list[dict]:
    """고정 부분(규칙+예시)을 맨 앞에, 바뀌는 부분(작성일+일기)을 맨 뒤에 둔다 (앞부분 재사용용)."""
    msgs = [{"role": "system", "content": SYSTEM}]
    for d, m in EXAMPLES:
        msgs.append({"role": "user", "content": f"작성일: 2026-09-01\n일기: {d}"})
        msgs.append({"role": "assistant", "content": m.model_dump_json()})
    msgs.append({"role": "user", "content": f"작성일: {written_at}\n일기: {diary}"})
    return msgs


def looks_broken(m: Extracted) -> bool:
    if not m.title.strip() or not m.summary.strip() or len(m.summary) > 150:
        return True
    values = [m.title, m.summary, m.place, m.topic, m.emotion, m.problem, m.decision, m.next_action, m.result, *m.people]
    return any(b in v for v in values for b in ("',", "':", "{", "}"))


def clean(m: Extracted) -> Extracted:
    norm = lambda s: "".join(s.split())
    d, n = norm(m.decision), norm(m.next_action)
    if d and n and (d in n or n in d):
        m.decision = ""
    return m


def extract_unit(diary: str, written_at: str, retries: int = 2) -> tuple[MemoryUnit | None, int]:
    """일기 한 편 -> MemoryUnit. (결과, 재시도 횟수)를 돌려준다. 끝내 실패하면 결과가 None."""
    wa = date.fromisoformat(written_at)
    for attempt in range(retries + 1):
        r = chat(
            model=MODEL,
            messages=build_messages(diary, written_at),
            format="json",
            options={"temperature": 0 if attempt == 0 else 0.3, "num_ctx": NUM_CTX},
            keep_alive=KEEP_ALIVE,
        )
        try:
            ext = Extracted.model_validate_json(r.message.content)
        except Exception:
            continue
        if looks_broken(ext):
            continue
        ext = clean(ext)
        span = timeparse.event_span(diary, wa)
        unit = MemoryUnit(
            **ext.model_dump(),
            written_at=written_at,
            event_start=span.start.isoformat(),
            event_end=span.end.isoformat(),
            event_precision=span.kind,
            event_expr=span.text,
        )
        return unit, attempt
    return None, retries


def embed_text(u: MemoryUnit) -> str:
    """임베딩 모델에 넣을 텍스트. 날짜, 제목, 요약에 핵심 칸을 덧붙인 한 덩어리."""
    parts = [f"[{u.event_start}] {u.title}. {u.summary}"]
    if u.people:
        parts.append("사람: " + ", ".join(u.people))
    for label, v in (("장소", u.place), ("감정", u.emotion), ("문제", u.problem),
                     ("결정", u.decision), ("할 일", u.next_action), ("결과", u.result)):
        if v:
            parts.append(f"{label}: {v}")
    return " ".join(parts)


DEMO = [
    ("어제 팀원들과 캡스톤 회의를 했다. 일정이 빡빡해서 걱정됐고, 다음 주에 모델을 결정하기로 했다.", "2026-10-10"),
    ("지난주 화요일에 친구 지현이랑 카페에서 싸웠는데 오늘 먼저 연락해서 화해했다. 마음이 한결 가벼워졌다.", "2026-10-10"),
    ("오늘 학식을 먹고 도서관에서 공부했다.", "2026-10-10"),
    ("내일 오전 10시에 지도교수님과 면담이 있다. 질문 목록을 미리 정리해 두기로 했다.", "2026-10-10"),
    ("3월에 운영체제 중간고사를 봤는데 마지막 문제를 못 풀어서 아쉬웠다.", "2026-10-10"),
    ("11월 둘째 주에 부모님과 제주도에 가기로 했고 숙소는 내가 알아보기로 했다.", "2026-10-10"),
]

if __name__ == "__main__":
    for i, (diary, wa) in enumerate(DEMO, 1):
        t = time.time()
        unit, retried = extract_unit(diary, wa)
        print(f"[{i}] 재시도 {retried}회, {time.time() - t:.1f}초")
        print(diary)
        if unit is None:
            print("실패: 재시도 후에도 형식이 깨짐\n")
            continue
        print(f"  요약: {unit.summary}")
        print(f"  사건 날짜: {unit.event_start} ~ {unit.event_end} ({unit.event_precision}), 근거 표현: {unit.event_expr or '없음(작성일 사용)'}")
        print(f"  {unit.model_dump_json(exclude={'written_at','event_start','event_end','event_precision','event_expr'})}")
        print(f"  임베딩 텍스트: {embed_text(unit)}\n")