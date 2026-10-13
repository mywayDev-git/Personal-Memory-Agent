"""Deterministic, authored synthetic fixtures. Does not call or learn from the model."""

import json
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ("direct", "colloquial", "indirect", "connection", "constraints", "ambiguity")
PEOPLE = [
    "지연",
    "민수",
    "수빈",
    "도윤",
    "서연",
    "준호",
    "유진",
    "하린",
    "태훈",
    "소희",
    "현우",
    "은지",
]


def render(template, values):
    """Resolve Korean particles; intentional colloquial spelling remains unchanged."""
    pairs = {
        "은": ("은", "는"),
        "는": ("은", "는"),
        "이": ("이", "가"),
        "가": ("이", "가"),
        "을": ("을", "를"),
        "를": ("을", "를"),
        "과": ("과", "와"),
        "와": ("과", "와"),
        "이랑": ("이랑", "랑"),
    }

    def replace(match):
        value = str(values[match[1]])
        final = ord(value[-1]) if value else 0
        consonant = 0xAC00 <= final <= 0xD7A3 and (final - 0xAC00) % 28 != 0
        return value + pairs[match[2]][0 if consonant else 1]

    return re.sub(r"\{(\w+)\}(이랑|은|는|이|가|을|를|과|와)(?![가-힣])", replace, template).format(
        **values
    )


AMBIGUOUS = {
    "gift": [
        "걔가 그때 원한 거 뭐더라?",
        "전에 갖고 싶다던 게 뭐였더라?",
        "그 사람 선물 얘기한 거 기억나?",
        "그때 사달라던 거 말이야, 뭐였지?",
        "아까 그 친구가 원했다던 거 찾아줘",
    ],
    "travel": [
        "거기서 그거 먹은 게 언제지?",
        "그 여행에서 어디 들렀더라?",
        "전에 갔던 거기 이름이 뭐야?",
        "걔랑 놀러간 데서 먹은 거 알려줘",
        "그때 취소한 데 다시 갔었나?",
    ],
    "exercise": [
        "그날 왜 덜 뛰었지?",
        "그때 일찍 멈춘 이유가 있나?",
        "걔는 왜 그만큼만 뛰었어?",
        "내가 거기서 더 안 달린 이유는?",
        "그날 운동이 짧았던 이유 알려줘",
    ],
    "appointment": [
        "우리 다음 약속 그때 맞지?",
        "걔랑 만날 날짜 그날로 정했어?",
        "그 모임 몇시더라?",
        "다음번에 보기로 한 장소 어디야?",
        "그때 약속은 그대로 하는 거야?",
    ],
    "school": [
        "그 과제 걔가 다 한 거지?",
        "그거 내 담당 맞나?",
        "걔가 맡은 부분 제출됐어?",
        "그 프로젝트 역할 바뀌었잖아, 내 건 뭐야?",
        "전에 고친 과제가 뭐였더라?",
    ],
    "food": [
        "걔 못먹는게 뭐였어?",
        "그 사람 피하는 음식이 뭐지?",
        "같이 밥 먹은 걔 알레르기 있어?",
        "그 메뉴 걔가 안 먹었던 거 맞아?",
        "거기서 대신 주문한 게 뭐야?",
    ],
    "purchase": [
        "그거 아직 갖고 있나?",
        "그때 산 거 환불했어?",
        "전에 주문한 물건 도착했나?",
        "내가 그 제품 얼마 주고 샀더라?",
        "걔랑 본 제품 내가 샀던가?",
    ],
    "social": [
        "걔랑 그 일 잘 풀렸나?",
        "그때 싸운 친구하고 화해했어?",
        "걔한테 연락은 했나?",
        "그 문제 누가 먼저 사과했어?",
        "전에 다툰 일 아직 해결 안 됐나?",
    ],
}

DIARY = (
    "\n오늘 기록은 짧게 끝내려다가 길어졌다. 아침에는 알람을 끄고 다시 누웠고, "
    "창문을 열었더니 생각보다 바람이 차가웠다. 식탁 위에 놓인 종이들을 정리했지만 "
    "지난주에 찾던 영수증은 못 찾았다. 가방에는 충전기와 손수건을 챙겼다. "
    "버스 창가에 앉아서 음악을 들었는데 곡 제목은 기억나지 않는다. 정류장을 "
    "지나칠까 봐 지도를 두 번 확인했다. 길에서 본 작은 강아지는 갈색이었다. "
    "누가 키우는 강아지인지는 모른다. 잠깐 비가 와서 건물 처마 아래에 서 있었다.\n"
    "집에 와서는 젖은 신발을 말렸다. 휴대전화 배터리가 꺼져서 충전한 뒤에야 "
    "기록을 마저 쓰고 있다. 오늘 있었던 일과 오래전에 떠올린 생각이 섞일까 봐 "
    "날짜를 확인했다. 작년에 쓰던 공책도 꺼냈지만 거기에 적힌 약속을 오늘 한 일로 "
    "옮기지는 않았다. 저녁에는 밀린 빨래를 개고 화분에 물을 줬다. 친구에게 "
    "연락할까 생각만 하다가 보내지는 않았다. 그 친구가 누구였는지는 지금 "
    "적지 않겠다. 잠들기 전에 내일 할 일을 생각했지만 구체적인 일정은 정하지 않았다."
)
# Every domain has five different events, not five renamed copies of one question.
DETAILS = {
    "gift": [
        ("서울숲", "머그컵", "파란색", "빨간색"),
        ("보라매공원", "목도리", "초록색", "노란색"),
        ("올림픽공원", "수첩", "보라색", "검은색"),
        ("월드컵공원", "텀블러", "흰색", "주황색"),
        ("어린이대공원", "우산", "남색", "분홍색"),
    ],
    "travel": [
        ("부산", "해운대", "자갈치시장", "회"),
        ("강릉", "경포대", "중앙시장", "감자전"),
        ("전주", "한옥마을", "남부시장", "비빔밥"),
        ("여수", "오동도", "수산시장", "게장"),
        ("제주", "성산일출봉", "동문시장", "고기국수"),
    ],
    "exercise": [
        ("한강공원", "4", "5", "3"),
        ("탄천", "6", "7", "2"),
        ("중랑천", "8", "9", "4"),
        ("안양천", "3", "4", "1"),
        ("양재천", "5", "6", "2"),
    ],
    "appointment": [
        ("혜화역", "독서 모임", "토요일", "일요일"),
        ("신촌역", "영화 모임", "월요일", "화요일"),
        ("사당역", "보드게임 모임", "수요일", "목요일"),
        ("건대입구역", "사진 모임", "금요일", "토요일"),
        ("합정역", "그림 모임", "화요일", "수요일"),
    ],
    "school": [
        ("공학관", "캡스톤", "백엔드", "발표 자료"),
        ("도서관", "데이터베이스 과제", "스키마", "보고서"),
        ("정보관", "네트워크 과제", "서버", "실험 기록"),
        ("학생회관", "동아리 전시", "포스터", "안내문"),
        ("강의동", "통계 과제", "분석 코드", "발표 슬라이드"),
    ],
    "food": [
        ("성수", "라멘", "우동", "새우"),
        ("망원", "파스타", "리조토", "땅콩"),
        ("연남", "카레", "오므라이스", "우유"),
        ("을지로", "냉면", "칼국수", "달걀"),
        ("종로", "덮밥", "국밥", "조개"),
    ],
    "purchase": [
        ("용산", "키보드", "무선", "유선"),
        ("잠실", "헤드폰", "검은색", "흰색"),
        ("왕십리", "가방", "작은", "큰"),
        ("구로", "모니터", "27인치", "24인치"),
        ("영등포", "의자", "회색", "갈색"),
    ],
    "social": [
        ("뚝섬", "약속 시간", "산책", "빵집"),
        ("대학로", "모임 장소", "영화", "문구점"),
        ("노량진", "빌린 책", "점심", "서점"),
        ("상수", "공동 비용", "전시", "편의점"),
        ("이촌", "단체 사진", "자전거", "꽃집"),
    ],
}

# Text, semantic relation, actor role, object, state. Date prefixes are added below.
RECORDS = {
    "gift": [
        (
            "{p}과 {l}에서 얘기했다. {p}은 생일 선물로 {b} {a}을 받고 싶다고 말했다.",
            "desire",
            "p",
            "{b} {a}",
            "desire",
        ),
        (
            "나는 {p}에게 줄 {b} {a}을 살 계획을 세웠다. 아직 구입하지 않았다.",
            "buy",
            "self",
            "{b} {a}",
            "planned",
        ),
        (
            "{b} {a} 대신 {c} {a}을 샀다. {p}의 취향이 바뀌었다는 얘기는 듣지 못했다.",
            "buy",
            "self",
            "{c} {a}",
            "observed",
        ),
        ("{l}에서 나는 {p}에게 {c} {a}을 생일선물로 줬다.", "give", "self", "{c} {a}", "observed"),
        (
            "{p}은 이제 {b}보다 {c} {a}이 더 좋다고 직접 말했다. 왜 바뀌었는지는 말하지 않았다.",
            "prefer",
            "p",
            "{c} {a}",
            "preference",
        ),
    ],
    "travel": [
        (
            "{p}과 {l} 여행을 가고 싶다고 얘기했다. 꼭 가기로 한 건 아니다.",
            "visit",
            "self",
            "{l}",
            "desire",
        ),
        (
            "{l} 숙소를 예약했다. {a}에 들를 계획인데 아직 여행은 안 갔다.",
            "reserve",
            "self",
            "{l} 숙소",
            "observed",
        ),
        (
            "{l} 여행 예약을 취소했다. 이때는 {l}에 가지 않았다.",
            "cancel",
            "self",
            "{l} 여행",
            "observed",
        ),
        (
            "계획을 다시 잡아 {p}과 {l}에 갔다. {a}에서 사진을 찍고 {b}에서 {c}을 먹었다.",
            "visit",
            "self",
            "{a}, {b}, {c}",
            "observed",
        ),
        (
            "{l} 여행 후 사진을 정리했다. {p}은 {a}보다 {b}이 기억에 남는다고 말했다.",
            "recall",
            "p",
            "{b}",
            "observed",
        ),
    ],
    "exercise": [
        (
            "{l}에서 {a}km를 달려보고 싶다. 아직 그 거리를 뛴 적은 없다.",
            "run",
            "self",
            "{a}km",
            "desire",
        ),
        (
            "{l}에서 나는 {a}km 달릴 계획을 세웠다. {p}과 같이 하기로 했다.",
            "run",
            "self",
            "{a}km",
            "planned",
        ),
        (
            "{l}에서 {p}은 {a}km를 달렸다. 나는 구경만 했고 달리지 않았다.",
            "run",
            "p",
            "{a}km",
            "observed",
        ),
        (
            "{l}에서 나는 {b}km를 달렸다. {a}km에서 멈추지 않고 더 뛰었다.",
            "run",
            "self",
            "{b}km",
            "observed",
        ),
        (
            "{l}에서 나는 {meters}m만 달렸다. 더 뛰지는 않았다.",
            "run",
            "self",
            "{meters}m",
            "observed",
        ),
    ],
    "appointment": [
        ("{p}과 {l} 근처에서 {a}을 하고 싶다고 얘기했다.", "meet", "self", "{a}", "desire"),
        (
            "{a} 약속을 {b} 오후 2시로 잡았다. 만날 장소는 {l}, 상대는 {p}이다.",
            "meet",
            "self",
            "{b} 오후 2시",
            "planned",
        ),
        (
            "{p}과 {a} 약속을 {c} 오후 3시로 변경했다. 이전 {b} 약속은 취소했다.",
            "reschedule",
            "self",
            "{c} 오후 3시",
            "planned",
        ),
        (
            "{l}에서 {p}을 만나 {a}을 했다. 약속 변경 이유는 서로 묻지 않았다.",
            "meet",
            "self",
            "{a}",
            "observed",
        ),
        (
            "{p}과 했던 {a} 후기를 적었다. 다음 달에도 만나자는 말은 했지만 날짜는 정하지 않았다.",
            "meet",
            "self",
            "다음 달",
            "uncertain",
        ),
    ],
    "school": [
        (
            "{l}에서 {p}과 {a} 역할을 의논했다. 나는 {b}을 맡고 싶다고 했다.",
            "role",
            "self",
            "{b}",
            "desire",
        ),
        ("{a} 분담 확정. 나는 {b}, {p}은 {c}을 맡기로 했다.", "role", "self", "{b}", "planned"),
        (
            "{a}에서 역할을 바꿨다. 이제 나는 {c}, {p}은 {b} 담당이다.",
            "role",
            "self",
            "{c}",
            "planned",
        ),
        (
            "{l}에서 {a}의 {c}을 제출했다. {p}이 {b} 작업을 끝냈는지는 아직 모른다.",
            "submit",
            "self",
            "{c}",
            "observed",
        ),
        (
            "{a} 회고. 제출한 {c}의 오타를 고쳤다. {p}의 결과물을 내가 만들었다는 말은 사실이 아니다.",
            "correct",
            "self",
            "{c}",
            "observed",
        ),
    ],
    "food": [
        (
            "{p}은 {l}에서 {a}을 먹고 싶다고 말했다. 나는 아직 메뉴를 정하지 않았다.",
            "eat",
            "p",
            "{a}",
            "desire",
        ),
        ("{p}과 {l} 식당을 예약했다. 나는 {a}을 먹을 생각이었다.", "eat", "self", "{a}", "planned"),
        ("{l} 식당에서 {a}은 품절이라 나는 {b}을 주문했다.", "order", "self", "{b}", "observed"),
        (
            "{l}에서 나는 {b}을 먹었다. {p}은 {a}을 먹지 않고 물만 마셨다.",
            "eat",
            "self",
            "{b}",
            "observed",
        ),
        (
            "{p}이 {c}을 피한다고 들었다. 알레르기인지 단순히 싫은 건지는 모르겠다.",
            "avoid",
            "p",
            "{c}",
            "uncertain",
        ),
    ],
    "purchase": [
        (
            "{p}과 {l} 매장에 갔다. 나는 {b} {a}을 사고 싶다고 했다.",
            "buy",
            "self",
            "{b} {a}",
            "desire",
        ),
        (
            "{b} {a}을 주문할 계획이다. 예산은 10만원이고 아직 결제하지 않았다.",
            "buy",
            "self",
            "{b} {a}",
            "planned",
        ),
        (
            "{l}에서 {c} {a}을 8만원에 샀다. {b} 제품은 사지 않았다.",
            "buy",
            "self",
            "{c} {a}",
            "observed",
        ),
        (
            "{l}에서 산 {c} {a}을 반품 접수했다. 환불은 아직 안 됐다.",
            "return",
            "self",
            "{c} {a}",
            "planned",
        ),
        ("{c} {a} 반품이 완료돼 80000원을 돌려받았다.", "refund", "self", "80000원", "observed"),
    ],
    "social": [
        (
            "{l}에서 {p}과 {a} 문제로 다퉜다. 누가 먼저 화냈는지는 적지 않겠다.",
            "conflict",
            "self",
            "{a}",
            "observed",
        ),
        ("{p}에게 사과하고 싶지만 아직 연락하지 않았다.", "apologize", "self", "{p}", "desire"),
        (
            "{p}에게 사과 메시지를 보냈다. 답장이 없어서 화해한 건지는 모르겠다.",
            "apologize",
            "self",
            "{p}",
            "observed",
        ),
        (
            "{l}에서 {p}을 만나 서로 사과하고 화해했다. 같이 {b}도 했다.",
            "reconcile",
            "self",
            "{p}",
            "observed",
        ),
        (
            "{p}과 {c}에 들렀다. 지난번 다툼 뒤 다시 만난 날이다. 다른 친구와 싸운 일은 없다.",
            "visit",
            "self",
            "{c}",
            "observed",
        ),
    ],
}

# Three genuinely different retrieval goals per category; rotate which two/three are used.
# A target is a source stage (zero based), not a model-generated golden answer.
QUESTIONS = {
    "gift": [
        [
            ("{p}이 원했던 생일 선물은?", [0]),
            ("내가 {p}에게 실제로 준 것은?", [3]),
            ("{p}이 나중에 더 좋다고 한 색은?", [4]),
        ],
        [
            ("{p} 갖고싶다던거 머더라", [0]),
            ("{p}한테 준거 색깔 뭐였음", [3]),
            ("{p} 선물 사긴 샀었나", [2]),
        ],
        [
            ("{l}에서 생일 얘기한 사람은 누굴까?", [0]),
            ("{b} {a}을 받고 싶다고 했던 사람 찾아줘", [0]),
            ("{l}에서 내가 건넨 물건이 뭐야?", [3]),
        ],
        [
            ("{p}이 원한 것과 내가 준 것을 비교해줘", [0, 3]),
            ("{p}의 {a} 취향이 어떻게 달라졌지?", [0, 4]),
            ("{p} 선물은 구매부터 전달까지 어떻게 이어졌어?", [2, 3]),
        ],
        [
            ("{d1} 당시 {p}에게 선물을 이미 줬나?", [1]),
            ("{p}에게 {a} 준 날짜는?", [3]),
            ("{d4} 기준 {p}이 더 좋아한다고 말한 건?", [4]),
        ],
        [
            ("{p}이 {c}을 좋아하게 된 이유가 뭐야?", []),
            ("걔가 그때 원한 거 뭐더라?", []),
            ("{p}에게 준 선물 때문에 취향이 바뀐 거야?", []),
        ],
    ],
    "travel": [
        [
            ("{l} 가서 뭐했지?", [3]),
            ("{l}에서 누구와 여행했어?", [3]),
            ("{p}은 {l} 여행에서 어디가 기억에 남았대?", [4]),
        ],
        [
            ("{l}가서 머먹었더라", [3]),
            ("{p}이랑 {l} 갔었나 취소만했나", [2, 3]),
            ("{l} 숙소 잡앗었어?", [1]),
        ],
        [
            ("{a}에서 사진 찍은 여행은 어디였지?", [3]),
            ("{c} 먹었던 시장 이름 기억나?", [3]),
            ("{a}보다 시장이 좋았다고 한 사람은?", [4]),
        ],
        [
            ("{l} 여행은 예약 취소 뒤 어떻게 됐어?", [1, 2, 3]),
            ("{l}에서 계획했던 곳과 실제 간 곳은?", [1, 3]),
            ("{p}과 {l}에 가고 싶다는 얘기 후 실제로 갔어?", [0, 3]),
        ],
        [
            ("{d2}까지 {l} 여행을 실행한 근거가 있어?", [2]),
            ("{l}에서 {c} 먹은 날짜는?", [3]),
            ("{d1}에는 {l} 숙소가 예약된 상태였나?", [1]),
        ],
        [
            ("{l} 예약 취소한 이유가 뭐야?", []),
            ("거기서 그거 먹은 게 언제지?", []),
            ("{p}이 {l} 여행을 싫어했지?", []),
        ],
    ],
    "exercise": [
        [
            ("{l}에서 내가 달린 거리는?", [3, 4]),
            ("{l}에서 {a}km를 달린 사람은?", [2]),
            ("{l}에서 처음 목표로 삼은 거리는?", [0]),
        ],
        [
            ("{l}서 나 {a}키로 뛴적 잇나", [2, 3, 4]),
            ("{p} 몇키로 뛰엇더라", [2]),
            ("{l} 달리기 짧게 뛴 날 얼마였지", [4]),
        ],
        [
            ("내가 구경만 하고 {p}이 달린 곳은?", [2]),
            ("{l}에서 {meters}m만 뛰었던 날 찾아줘", [4]),
            ("{b}km 완주한 {month}월 기록 있나?", [3]),
        ],
        [
            ("{l} 달리기 목표와 실제 거리는 어떻게 달라?", [1, 3, 4]),
            ("{l}에서 친구가 뛴 거리랑 내가 뛴 거리 비교해줘", [2, 3, 4]),
            ("{l}에서 마지막 두 번 운동량은 늘었어?", [3, 4]),
        ],
        [
            ("{l}에서 나는 {a}km 이상 달린 적 있어?", [3]),
            ("{l}에서 {a}km 미만 뛴 기록은?", [4]),
            ("{d2}에 {l}에서 달린 건 나야 {p}이야?", [2]),
        ],
        [
            ("{l}에서 내가 {a}km만 달렸다는 게 맞아?", [2, 3, 4]),
            ("그날 왜 덜 뛰었지?", []),
            ("{p}이 나보다 체력이 좋은 이유는?", []),
        ],
    ],
    "appointment": [
        [
            ("{a} 처음 약속한 시간은?", [1]),
            ("{a} 변경한 약속 시간은?", [2]),
            ("{l}에서 누구를 만났어?", [3]),
        ],
        [
            ("{a} 몇시로 바꼈더라", [2]),
            ("{p}이랑 {a} 하긴햇어?", [3]),
            ("{a} 담달 약속 날짜 잡힘?", [4]),
        ],
        [
            ("{l} 근처에서 하자던 모임이 뭐였지?", [0]),
            ("{month}월에 {c} 3시로 옮긴 약속은?", [2]),
            ("{a} 같이 하기로 한 사람 찾아줘", [1]),
        ],
        [
            ("{a}의 처음 약속과 변경 약속 비교해줘", [1, 2]),
            ("{a} 변경 뒤 실제 만난 기록까지 이어서 알려줘", [2, 3]),
            ("{a} 이번 만남과 다음 약속은 뭐가 확정됐어?", [3, 4]),
        ],
        [
            ("{d1} 기준 {a} 약속 시간 알려줘", [1]),
            ("{d2} 당시 {a} {b} 약속은 유효했어?", [2]),
            ("{a}을 실제로 한 날짜는?", [3]),
        ],
        [
            ("{p}이 {a} 시간을 바꾼 이유는?", []),
            ("우리 다음 약속 그때 맞지?", []),
            ("{a} 다음 달 날짜가 확정된 거야?", [4]),
        ],
    ],
    "school": [
        [
            ("{a}에서 처음 맡고 싶었던 역할은?", [0]),
            ("{a}에서 바뀐 내 담당은?", [2]),
            ("{a}에서 내가 제출한 것은?", [3]),
        ],
        [
            ("{a} 내꺼 뭐하기로햇지 첨에", [1]),
            ("{p} {a} 역할 머로 바뀜", [2]),
            ("{a} 제출은 햇었나", [3]),
        ],
        [
            ("{l}에서 역할 의논했던 과제는?", [0]),
            ("{month}월에 {c} 제출했던 장소 기억나?", [3]),
            ("{a}에서 {b} 맡게 된 사람은?", [2]),
        ],
        [
            ("{a} 역할 분담이 처음과 어떻게 달라졌어?", [1, 2]),
            ("{a}에서 맡기로 한 일과 제출한 일은 같아?", [2, 3]),
            ("{a} 제출 이후 고친 것은?", [3, 4]),
        ],
        [
            ("{d1} 당시 {a}에서 내 역할은?", [1]),
            ("{a} {c} 제출 날짜는?", [3]),
            ("{d3} 기준 {p}이 {a} 작업을 끝냈다고 확정할 수 있어?", [3]),
        ],
        [
            ("{a} 역할 바꾼 이유는?", []),
            ("그 과제 걔가 다 한 거지?", []),
            ("{a}에서 {p} 담당 작업도 내가 만든 거야?", [4]),
        ],
    ],
    "food": [
        [
            ("{p}이 {l}에서 먹고 싶다던 메뉴는?", [0]),
            ("{l}에서 실제로 내가 먹은 메뉴는?", [3]),
            ("{p}이 피한다고 들은 음식은?", [4]),
        ],
        [("{l}서 나 머먹엇지", [3]), ("{p} {a} 먹엇나", [3]), ("{l} 메뉴 왜 바꼇더라", [2])],
        [
            ("{a} 품절이라 다른 메뉴 주문했던 동네는?", [2]),
            ("{b} 먹을 때 물만 마신 사람은?", [3]),
            ("{c} 피한다고 들은 사람이 누구야?", [4]),
        ],
        [
            ("{l}에서 먹으려던 것과 먹은 것 비교해줘", [1, 3]),
            ("{p}은 {l}에서 원했던 메뉴를 먹었어?", [0, 3]),
            ("{l}에서 메뉴 바꾼 이유와 결과는?", [2, 3]),
        ],
        [
            ("{l}에서 {b} 먹은 날짜는?", [3]),
            ("{d1} 기준 {l} 식사는 실행된 상태였나?", [1]),
            ("{d3}에 {p}이 {a}을 먹었다는 기록이야?", [3]),
        ],
        [
            ("{p}은 {c} 알레르기가 확실해?", [4]),
            ("걔 못먹는게 뭐였어?", []),
            ("{p}이 {l}에서 물만 마신 이유는?", []),
        ],
    ],
    "purchase": [
        [
            ("처음 사고 싶었던 {a}은?", [0]),
            ("{l}에서 실제 산 {a}은?", [2]),
            ("{a} 환불로 얼마 돌려받았어?", [4]),
        ],
        [("{a} 머샀더라", [2]), ("{a} 반품 접수는햇나", [3]), ("{a} 돈 들어옴?", [4])],
        [
            ("{l} 매장에서 8만원 쓴 물건이 뭐였지?", [2]),
            ("{month}월에 {p}과 구경한 매장이 어디야?", [0]),
            ("80000원 환불받은 {c} 제품이 뭐였지?", [4]),
        ],
        [
            ("{a}은 원한 제품과 산 제품이 같아?", [0, 2]),
            ("{a} 구매부터 환불까지 정리해줘", [2, 3, 4]),
            ("{a} 예산과 실제 지출의 차이는?", [1, 2]),
        ],
        [
            ("{d3} 기준 {a} 환불이 완료됐나?", [3]),
            ("{a} 산 날짜는?", [2]),
            ("{a} 환불액 8만원과 80000원은 같은 금액이야?", [4]),
        ],
        [
            ("{a} 고장 나서 반품한 거지?", []),
            ("그거 아직 갖고 있나?", []),
            ("{p}에게 {a}을 선물한 게 맞아?", []),
        ],
    ],
    "social": [
        [
            ("{p}과 무엇 때문에 다퉜어?", [0]),
            ("{p}에게 사과 연락을 했어?", [2]),
            ("{p}과 화해하고 같이 한 활동은?", [3]),
        ],
        [
            ("{p}이랑 싸운게 언제더라", [0]),
            ("{p}한테 미안하다 보냇나", [2]),
            ("{p}이랑 풀엇어?", [3]),
        ],
        [
            ("{l}에서 {a} 문제로 다툰 상대는?", [0]),
            ("{month}월에 화해하고 {b} 한 사람은?", [3]),
            ("{c} 들르기 전에 다툰 일이 뭐야?", [0, 4]),
        ],
        [
            ("{p}과 다툼부터 화해까지 정리해줘", [0, 2, 3]),
            ("{p}에게 사과 메시지만 보냈을 때와 만난 뒤 상태는?", [2, 3]),
            ("{p}과 화해 뒤 다시 만난 근거 있어?", [3, 4]),
        ],
        [
            ("{d2} 기준 {p}과 화해가 확인됐어?", [2]),
            ("{p}과 실제로 화해한 날짜는?", [3]),
            ("{d1} 당시 {p}에게 이미 사과 연락했어?", [1]),
        ],
        [
            ("{p}과 싸울 때 누가 먼저 화냈어?", []),
            ("걔랑 그 일 잘 풀렸나?", []),
            ("{p}이 답장 안 한 이유는?", []),
        ],
    ],
}


def build():
    records, questions, events = [], [], []
    for domain_index, (domain, variants) in enumerate(DETAILS.items()):
        for variant, (location, a, b, c) in enumerate(variants):
            index = domain_index * 5 + variant
            eid = f"E{index + 1:02}"
            start = date(2026, 4, 1) + timedelta(days=index * 4)
            dates = [(start + timedelta(days=d)).isoformat() for d in (0, 1, 3, 6, 12)]
            v = dict(
                p=PEOPLE[index % 12],
                l=location,
                a=a,
                b=b,
                c=c,
                month=start.month,
                meters=int(c) * 1000 if domain == "exercise" else "",
            )
            v.update({f"d{i}": d for i, d in enumerate(dates)})
            split = (
                "holdout" if variant == 4 or (variant == 3 and domain_index < 2) else "development"
            )
            ids = []
            for stage, (template, relation, actor, obj, state) in enumerate(RECORDS[domain]):
                if domain == "travel" and variant == 3 and stage in (3, 4):
                    template = (
                        "{l} 여행은 취소한 뒤 다시 예약하지 않았다. {a}과 {b}에는 가지 않았다."
                        if stage == 3
                        else "{p}과 {l} 여행을 다시 의논했지만 날짜를 정하지 못했다. 여행 후기는 없다."
                    )
                    relation, actor, obj, state = (
                        "visit",
                        "self",
                        "{l}",
                        "negated" if stage == 3 else "uncertain",
                    )
                if domain == "school" and variant == 3 and stage in (3, 4):
                    template = "{a}의 {c}은 아직 제출하지 못했다. {p}의 {b}도 완료 여부를 모른다."
                    relation, actor, obj, state = "submit", "self", "{c}", "negated"
                if domain == "social" and variant == 2 and stage == 4:
                    template = "지난 {d3} 기록을 정정한다. {p}과 만나 {b}을 한 건 맞지만 화해했다고 쓴 것은 틀렸다. 서로 사과하지 않았고 아직 화해하지 않았다."
                    relation, actor, obj, state = "reconcile", "self", "{p}", "negated"
                rid = f"{eid}-R{stage + 1}"
                ids.append(rid)
                text = dates[stage] + " " + render(template, v)
                recorded = start + timedelta(days=(0, 1, 3, 6, 12)[stage])
                tags = ["explicit_date"]
                # Unknown dates and delayed writing are separate, so gold never invents a date.
                event_date = dates[stage]
                if variant == 2 and stage == 0:
                    text = "날짜는 기억 안 나는데 " + render(template, v)
                    event_date = None
                    tags = ["unknown_date"]
                if variant == 1 and stage == 3:
                    recorded += timedelta(days=15)
                    tags.append("late_recording")
                if variant == 1 and stage == 0:
                    text = "어제 " + render(template, v)
                    recorded += timedelta(days=1)
                    tags = ["relative_date"]
                if variant == 3 and stage == 1:
                    text = "메모: " + text + " 아직 실행한 건 아님ㅋㅋ"
                    tags.append("colloquial")
                if variant == 4 and stage == 4:
                    text += DIARY
                    tags.extend(["multiple_topics", "long_diary"])
                records.append(
                    dict(
                        id=rid,
                        event_id=eid,
                        split=split,
                        domain=domain,
                        text=text,
                        reference_time=recorded.isoformat() + "T20:00:00+09:00",
                        recorded_at=recorded.isoformat() + "T20:00:00+09:00",
                        event_time=event_date,
                        tags=tags,
                        gold_facts=[
                            dict(
                                subject=v[actor] if actor == "p" else "self",
                                relation=relation,
                                object=obj.format(**v),
                                state=state,
                                event_time=event_date,
                                source_id=rid,
                                quote=text,
                            )
                        ],
                    )
                )
            events.append(dict(id=eid, domain=domain, split=split, record_ids=ids))
            for cat_index, category in enumerate(CATEGORIES):
                count = 3 if (index + cat_index) % 2 == 0 else 2
                templates = QUESTIONS[domain][cat_index]
                selected = [(variant + j) % 3 for j in range(count)]
                for j in selected:
                    template, targets = templates[j]
                    if category == "ambiguity" and j == 1:
                        template = AMBIGUOUS[domain][variant]
                    qid = f"{eid}-{category}-{j + 1}"
                    if (
                        domain == "social"
                        and variant == 2
                        and category in {"direct", "colloquial", "connection"}
                        and 3 in targets
                    ):
                        targets = sorted(set(targets + [4]))
                    questions.append(
                        dict(
                            id=qid,
                            event_id=eid,
                            split=split,
                            category=category,
                            question=render(template, v),
                            relevant=[ids[t] for t in targets],
                            expected=dict(
                                mode="evidence" if targets else "abstain_or_clarify",
                                supporting_fact_ids=[ids[t] for t in targets],
                                requirement="질문에 해당하는 사실만 답하고 주체·상태·시각을 구분한다."
                                if targets
                                else "근거 없는 전제·원인·대상을 확정하지 않는다. 부족한 단서를 설명하거나 확인한다.",
                                forbidden_claims=[
                                    "계획이나 희망을 실행으로 간주",
                                    "기록 시각을 미상의 사건 시각으로 사용",
                                    "시간 순서만으로 인과관계 확정",
                                ],
                                semantic_review="pending",
                            ),
                            needs_conversation_context=(category == "ambiguity" and j == 1)
                            or not targets
                            and (
                                "걔" in template
                                or "그거" in template
                                or "그때" in template
                                or "그날" in template
                            ),
                            repeat_at_snapshots=index in {0, 4, 5, 9, 10, 15, 20, 25, 30, 35}
                            and j == selected[0],
                        )
                    )
    # 100 background records, including confusing lookalikes, uncertainty and corrections.
    backgrounds = [
        "{p}은 {place}에서 파란색 머그컵 사진을 봤다. 사고 싶다는 말은 하지 않았다.",
        "{p}이 4km를 달렸다는데 직접 본 건 아니다. 나는 오늘 달리지 않았다.",
        "{place} 여행 광고를 저장했다. 예약하거나 방문한 것은 아니다.",
        "{p} 책 아직 안돌려줌.",
        "{p}이 {place}에서 커피 마심. 나는 함께 가지 않았다. 누구와 마셨는지는 기억 안남.",
        "지연이라는 새 동료를 소개받았다. 기존 친구 지연과 다른 사람이다. 성은 모른다.",
        "{p}은 빨간색 컵을 선물했다. 받은 사람은 내가 아니라 그 사람 동생이다.",
        "{p}의 메모를 전해 들음: {place}에서 빵 삿다. 우유는 안삼. 버스 놓쳐서 걸어옴. 나는 그 자리에 없었다.",
        "{p}과 점심값으로 12000원 냈다. 내가 전부 낸 건지 각자 낸 건지는 적지 않았다.",
        "{p}이 {place} 모임에 왔다고 들었지만 참석 명단에는 없었다. 참석 여부 미확인.",
    ]
    for i in range(100):
        day = date(2026, 4, 1) + timedelta(days=i * 181 // 99)
        text = render(
            backgrounds[i % 10],
            dict(
                p=PEOPLE[(i * 7) % 12],
                place=["부산", "서울숲", "성수", "강릉", "한강공원"][(i // 10) % 5],
            ),
        )
        if i % 10 == 8:
            text += " 지난 메모에 15000원이라고 쓴 것은 잘못이었다. 12000원이 맞다."
        records.append(
            dict(
                id=f"B{i + 1:03}",
                event_id=None,
                split="background",
                domain="daily",
                text=day.isoformat() + " " + text,
                reference_time=day.isoformat() + "T21:00:00+09:00",
                recorded_at=day.isoformat() + "T21:00:00+09:00",
                event_time=day.isoformat(),
                tags=["distractor", "ambiguous", "correction" if i % 10 == 8 else "daily"],
                gold_facts=[],
            )
        )
    records.sort(key=lambda r: (r["recorded_at"], r["id"]))
    result = dict(
        schema_version=1,
        synthetic=True,
        today="2026-10-13",
        people=PEOPLE,
        period={"start": "2026-04-01", "end": "2026-09-30"},
        records=records,
        events=events,
        questions=questions,
        snapshots=[30, 100, 300],
        lifecycle_cases=[
            dict(
                event_id=e["id"],
                target=e["record_ids"][3],
                operations=["edit", "trash", "purge", "dismiss_relation"],
            )
            for e in events
        ],
        annotation_policy="Authored before execution; gold_facts are supporting evidence, not all fields required in every answer. Semantic review remains separate from automatic checks.",
    )
    validate(result)
    return result


def validate(data):
    assert data["synthetic"] is True
    assert len(data["records"]) == 300 and len(data["questions"]) == 600
    assert len(data["events"]) == 40 and len(set(data["people"])) == 12
    assert Counter(q["category"] for q in data["questions"]) == dict.fromkeys(CATEGORIES, 100)
    assert sum(q["repeat_at_snapshots"] for q in data["questions"]) == 60
    assert Counter(e["split"] for e in data["events"]) == {"development": 30, "holdout": 10}
    records = {r["id"]: r for r in data["records"]}
    assert len(records) == 300 and len({q["id"] for q in data["questions"]}) == 600
    assert sum(r["event_id"] is not None for r in records.values()) == 200
    for event in data["events"]:
        assert len(event["record_ids"]) == 5
        assert all(records[r]["split"] == event["split"] for r in event["record_ids"])
    for q in data["questions"]:
        assert all(r in records for r in q["relevant"])
        assert all(records[r]["event_id"] == q["event_id"] for r in q["relevant"])


def main():
    data = build()
    path = ROOT / "data/life_diagnostics.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(data['records'])} records, {len(data['questions'])} questions: {path}")


if __name__ == "__main__":
    main()
