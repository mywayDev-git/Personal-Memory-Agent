"""Public synthetic NAT fixtures. No personal database is required."""

STUDY = "2026-10-10 Python Part 1을 완료했다."
ONGOING = "2026-10-10 Python Part 1을 공부했다. 완료 여부는 기록하지 않았다."
COURSE = "Python 커리큘럼은 Part 1 다음 Part 2, 그다음 Part 3이다."

# ID, current message, records, required concepts (alternatives separated by |), forbidden assertions.
ROWS = [
    (
        "NAT-T01",
        "Python 다시 공부하려고",
        [STUDY, COURSE],
        ["Part 1", "완료"],
        [r"Part\s*2를?\s*완료(?:했|하셨|한\s*상태|한\s*기록)"],
    ),
    ("NAT-T02", "Python 어디까지 했지?", [ONGOING], ["확인|불명|기록|모르"], ["Part 1을 완료했"]),
    (
        "NAT-T03",
        "Python 마지막 진도 알려줘",
        [STUDY, "2026-10-15 Python Part 2를 완료했다."],
        ["Part 2"],
        ["현재 Part 1까지"],
    ),
    (
        "NAT-T04",
        "Python 어디까지 했더라?",
        [STUDY, "2026-10-10 Python Part 1은 완료하지 않았다."],
        ["충돌|상반|다른|확정|확인"],
        [],
    ),
    (
        "NAT-T05",
        "Python 다시 공부할까?",
        [STUDY],
        ["Part 1"],
        ["다음 과정은 Part 2입니다", "Part 2부터 해야"],
    ),
    (
        "NAT-T06",
        "PMA 프로젝트 계속하자",
        ["2026-10-15 PMA API 설계는 완료했다. 통합 테스트는 진행 중이다."],
        ["API|테스트"],
        ["통합 테스트를 완료했"],
    ),
    (
        "NAT-T07",
        "PMA 검색 방식 마지막 결정 알려줘",
        [
            "2026-10-10 PMA 검색은 A를 선택했다.",
            "2026-10-15 PMA 검색은 A에서 B로 변경하기로 결정했다.",
        ],
        ["B"],
        [],
    ),
    ("NAT-T08", "안녕", [STUDY], [], ["Python", "Part 1"]),
    (
        "NAT-T09",
        "내 기록 말고 일반적으로 Python 공부 방법 알려줘",
        [STUDY],
        [],
        ["Part 1을 완료", "기록을 보니"],
    ),
    (
        "NAT-T10",
        "PMA 프로젝트 진도 알려줘",
        ["PMA API 설계는 진행 중이다.", "YOLO API 설계는 완료했다."],
        ["진행"],
        ["PMA API 설계는 완료"],
    ),
    (
        "NAT-T11",
        "또 캐시 오류야",
        ["이전 Linux 환경의 캐시 오류는 갱신 로직을 수정해 해결했다."],
        ["확인|환경|같은|이전"],
        ["이번에도 원인은 동일"],
    ),
    (
        "NAT-T12",
        "지난번 캐시 오류는 어떻게 해결했지?",
        ["캐시 오류는 갱신 로직을 수정해 해결했다."],
        ["갱신"],
        [],
    ),
    (
        "NAT-T13",
        "PMA 또 메모리 부족이야",
        ["PMA에서 배치 크기를 32로 줄여도 메모리 부족 해결에 실패했다."],
        ["실패|해결되지|부족"],
        ["32로 줄이면 해결됩니다"],
    ),
    ("NAT-T14", "Python 이어서 공부하자", [STUDY, COURSE], ["Part 1"], []),
    (
        "NAT-T15",
        "Python 지난 기록 자연스럽게 설명해줘",
        [ONGOING],
        ["공부|학습"],
        ["Part 1을 완료했"],
    ),
    (
        "NAT-T16",
        "PMA 다음 단계 계획 세워줘",
        ["PMA API 설계는 완료했다. 다음 작업 순서는 정하지 않았다."],
        ["API"],
        ["반드시 통합 테스트가 다음"],
    ),
    ("NAT-T17", "고마워", [STUDY], [], ["Python", "Part 1"]),
    ("NAT-T18", "그럼 예제로 설명해줘", [], [], ["지난 기록에 따르면"]),
    (
        "NAT-T19",
        "PMA 진도를 정정하고 싶어",
        ["PMA API 설계는 진행 중이다."],
        [],
        ["수정했습니다", "완료로 저장했습니다"],
    ),
    ("NAT-T20", "오랜만에 Python 다시 공부하려고", [STUDY, COURSE], ["Part 1"], []),
    (
        "NAT-T21",
        "또 캐시 오류야. 이번에는 Windows야",
        ["Linux에서 캐시 경로를 바꿔 오류를 해결했다."],
        ["환경|Windows|Linux|확인"],
        ["동일한 원인입니다"],
    ),
    (
        "NAT-T22",
        "PMA 다음 단계 뭐부터 하지?",
        ["PMA에서 전체 재색인을 추천받았지만 실패했다. 같은 방법은 원하지 않는다."],
        ["실패|원하지|대안"],
        [],
    ),
    (
        "NAT-T23",
        "PMA 마지막 진행 상황 알려줘",
        ["2024-01-01 PMA API 설계는 진행 중이었다."],
        ["2024|마지막|기록"],
        ["지금도 진행 중입니다"],
    ),
    ("NAT-T24", "오늘 날씨 좋네", [STUDY], [], ["Part 1", "Python 공부"]),
    (
        "NAT-T25",
        "PMA와 Python 중 뭐부터 할까?",
        ["PMA API 테스트는 미완료다.", STUDY],
        ["PMA", "Python|Part"],
        [],
    ),
    (
        "NAT-T26",
        "이번에는 PMA 검색 방식을 B로 바꿀까?",
        ["PMA 검색은 유지보수가 쉬워 A로 결정했다."],
        ["A|유지보수"],
        ["B로 변경했습니다"],
    ),
    ("NAT-T27", "추천은 싫어. 지금은 그냥 쉬고 싶어", [STUDY], [], ["Part 2부터 시작하세요"]),
    ("NAT-T28", "안녕", ["민감한 건강 상담 내용을 기록했다."], [], ["건강", "상담"]),
    (
        "NAT-T29",
        "오랜만에 PMA 프로젝트 계속하자",
        ["2026-10-15 PMA API 설계는 완료했다."],
        ["API"],
        ["통합 테스트도 완료"],
    ),
    (
        "NAT-T30",
        "Python Part 2 완료했었나?",
        ["이전 AI는 Python Part 2 완료라고 잘못 답했다. 실제로는 Python Part 1만 공부했다."],
        ["Part 1|잘못|완료 여부|확인"],
        ["Part 2를 완료했습니다"],
    ),
]


def cases():
    return [
        {
            "id": key,
            "message": message,
            "records": [{"id": f"{key}-r{i}", "text": text} for i, text in enumerate(records)],
            "previous_context": [],
            "required_concepts": required,
            "forbidden_claims": forbidden,
            "expected_search": key
            not in {"NAT-T08", "NAT-T09", "NAT-T17", "NAT-T18", "NAT-T24", "NAT-T27", "NAT-T28"},
            "expected_interpretation": "원문·상태·시점을 보존하며 현재 요청에 필요한 사실만 사용",
            "expected_response_type": {
                "NAT-T01": "RESUME_ACTIVITY",
                "NAT-T02": "PROGRESS_REVIEW",
                "NAT-T04": "CONFLICT",
                "NAT-T06": "RESUME_ACTIVITY",
                "NAT-T08": "GENERAL",
                "NAT-T09": "MEMORY_SUPPRESSED",
                "NAT-T11": "PAST_EXPERIENCE",
                "NAT-T16": "NEXT_STEP_SUGGESTION",
            }.get(key),
            "expected_buttons": [],
            "required_sources": [],
            "failure_code": None,
            "evaluation_boundary": "실제 모델 평가는 의미·출처 검사, 계약 테스트는 개별 정책·액션 경계 검사",
        }
        for key, message, records, required, forbidden in ROWS
    ]
