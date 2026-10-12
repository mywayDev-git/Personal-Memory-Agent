import time
from pydantic import BaseModel
from ollama import chat

MODEL = "qwen3:4b-instruct"


class Memory(BaseModel):
    title: str
    people: list[str]
    topic: str
    emotion: str
    problem: str
    decision: str
    next_action: str
    result: str


SYSTEM = """너는 일기에서 기억 정보를 추출하는 도구다. JSON으로만 답한다.
출력 키: title, people, topic, emotion, problem, decision, next_action, result (people만 배열, 나머지는 문자열).
규칙:
- 일기에 적힌 내용만 쓴다. 없는 정보는 빈 문자열로 둔다(people은 빈 배열). 추측하지 않는다.
- title은 항상 짧게 채운다.
- people: 일기에 나온 사람 모두. '팀원들', '엄마', '교수님' 같은 호칭도 포함한다.
- topic: 무엇에 대한 일인지 짧은 명사구.
- emotion: 일기에 직접 드러난 감정만.
- problem: 일기에 적힌 어려움이나 문제.
- decision: 이미 내려진 결정이나 방침. 아직 결정하지 않은 것, 피드백을 받은 것, 문제가 해결된 결과는 넣지 않는다.
- next_action: 앞으로 하기로 한 일이나 예정된 일. decision과 같은 내용을 중복해서 쓰지 않는다.
- result: 이미 일어난 일의 결과나 해결, 마무리. 아직 일어나지 않은 일은 넣지 않는다.
- problem, decision, next_action, result는 일기에 그런 내용이 분명히 적힌 경우에만 쓴다. 식사, 이동, 만남, 사진 촬영 같은 단순한 일상 사실은 넣지 않는다. 확신이 없으면 빈 문자열로 둔다.
- 이미 끝난 행동(~했다, ~물어봤다)은 next_action에 넣지 않는다.
- 각 필드는 한국어로 짧게(한 문장 이하) 쓴다."""

EXAMPLES = [
    (
        "오늘 민수랑 점심을 먹었다. 요즘 취업 준비 때문에 불안하다는 이야기를 들어줬는데 나까지 마음이 무거워졌다. 같이 스터디를 해 보기로 했다.",
        Memory(
            title="민수와 점심",
            people=["민수"],
            topic="취업 준비",
            emotion="마음이 무거움",
            problem="민수가 취업 준비로 불안해함",
            decision="같이 스터디를 하기로 함",
            next_action="",
            result="",
        ),
    ),
    (
        "오늘 동아리 사람들과 MT 장소를 이야기했다. 후보를 두 곳으로 줄였고, 금요일에 투표로 정하기로 했다.",
        Memory(
            title="동아리 MT 장소 논의",
            people=["동아리 사람들"],
            topic="MT 장소 선정",
            emotion="",
            problem="",
            decision="후보를 두 곳으로 줄임",
            next_action="금요일에 투표로 장소를 정함",
            result="",
        ),
    ),
    (
        "오늘 팀 프로젝트 발표 주제를 두고 의견이 갈렸다. 결론을 못 내서 내일 다시 모여 정하기로 했다. 답답하다.",
        Memory(
            title="발표 주제 논의",
            people=[],
            topic="발표 주제 선정",
            emotion="답답함",
            problem="의견이 갈려 결론을 못 냄",
            decision="",
            next_action="내일 다시 모여 주제를 정함",
            result="",
        ),
    ),
    (
        "오늘 자전거 바퀴가 터져서 수리점에 맡겼다. 타이어 펑크였고 만 원에 고쳤다. 별일 아니라 다행이다.",
        Memory(
            title="자전거 수리",
            people=[],
            topic="자전거 수리",
            emotion="다행스러움",
            problem="자전거 타이어 펑크",
            decision="",
            next_action="",
            result="수리점에서 만 원에 고침",
        ),
    ),
    (
        "오늘 점심에 혼자 라면을 끓여 먹고 빨래를 했다. 저녁에는 동네를 한 바퀴 걸었다.",
        Memory(
            title="평범한 하루",
            people=[],
            topic="일상",
            emotion="",
            problem="",
            decision="",
            next_action="",
            result="",
        ),
    ),
]


def build_messages(diary: str, written_at: str) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM}]
    for d, m in EXAMPLES:
        msgs.append({"role": "user", "content": f"작성일: 2026-09-01\n일기: {d}"})
        msgs.append({"role": "assistant", "content": m.model_dump_json()})
    msgs.append({"role": "user", "content": f"작성일: {written_at}\n일기: {diary}"})
    return msgs


def looks_broken(m: Memory) -> bool:
    if not m.title.strip():
        return True
    values = [m.title, m.topic, m.emotion, m.problem, m.decision, m.next_action, m.result, *m.people]
    bad = ("',", "':", "{", "}")
    return any(b in v for v in values for b in bad)


def clean(m: Memory) -> Memory:
    norm = lambda s: "".join(s.split())
    d, n = norm(m.decision), norm(m.next_action)
    if d and n and (d in n or n in d):
        m.decision = ""
    return m


def extract(diary: str, written_at: str, retries: int = 2):
    for attempt in range(retries + 1):
        r = chat(
            model=MODEL,
            messages=build_messages(diary, written_at),
            format="json",
            options={"temperature": 0 if attempt == 0 else 0.3},
            **({} if "instruct" in MODEL else {"think": False}),
        )
        try:
            m = Memory.model_validate_json(r.message.content)
            if not looks_broken(m):
                return clean(m), attempt
        except Exception:
            pass
    return None, retries

TEST_DIARIES = [
    "오늘 팀원들과 캡스톤 회의를 했다. 회의에서 프로젝트 방향에 대해 의견을 나누었고, 다음주에 모델에 대한 결정을 내리기로 했다.",
    "오늘 DB 과제를 하다가 쿼리가 계속 에러가 나서 세 시간을 날렸다. 너무 짜증났는데 지수가 인덱스 문제라고 알려줘서 겨우 해결했다.",
    "오늘은 특별한 일 없이 하루 종일 집에서 쉬었다.",
    "어제 엄마, 아빠랑 제주도 가족 여행 계획을 세웠다. 11월 둘째 주에 가기로 했고 숙소는 내가 알아보기로 했다.",
    "오늘 교수님께 캡스톤 진행 상황을 보고드렸다. 모델 선정 근거가 부족하다는 피드백을 받아서 걱정이 된다.",
    "오늘 아침에 늦잠을 자서 1교시에 지각했다. 교수님께 죄송하다고 말씀드렸다. 내일부터 알람을 두 개 맞추기로 했다.",
    "지난주에 친구 지현이랑 싸웠는데 오늘 먼저 연락해서 화해했다. 마음이 한결 가벼워졌다.",
    "오늘 학식을 먹고 도서관에서 공부했다.",
]

if __name__ == "__main__":
    for i, diary in enumerate(TEST_DIARIES, 1):
        t = time.time()
        m, retried = extract(diary, "2026-10-05")
        print(f"[{i}] 재시도 {retried}회, {time.time() - t:.1f}초")
        print(diary)
        print(m.model_dump_json() if m else "실패: 재시도 후에도 형식이 깨짐")
        print()