"""Catalog builder. Registration never implies tested support."""

import json
import re
from pathlib import Path

from evaluation.scenario_cases import build

VARIANTS = {
    "R": """텍스트,음성전사,가져오기;한 문장,여러 문단;단일 사건,복수 사건;완결문,문장 파편;서술,질문,명령,인용;표준어,구어체,혼합언어;평문,목록,표;시간순,역순;단일 사실,고밀도 복합;없음,문장 반복;정상,오타,전사 오류;본인,전언,외부 문서;일기,계획,교정;독립,동일 사건 분산;성공,부분 성공,실패;본인,타인;실명,별명;한 명,동명이인;명시,생략;나에서 타인,타인에서 나;행위자,수신자,관찰자;한 명,여러 명;가족,동료,미상;이름,대명사,별명;직접 행동,전언;발화자 나,작성자 나;사건시각,기록시각,발언시각;절대,상대;어제,오늘,내일;확정,추정,미상;이전,이후,동시;단일 시점,범위;과거,현재,변경;일치,상충;계획,희망,확정 일정;작성일,발언일;일,월,연도,미상;매일,매주,불규칙;사실,가정,미상;긍정,부정;희망,계획,결정,시도,실행,완료,취소,실패;계획만,실행만,연결 확인;확정,추정,불확실;긍정,부정,혼합;사람,사건,대상 미상;사실,의견;좋아함,싫어함,변화;성공,실패,미기록;결정,미결정,철회;충족,불충족,미확인;가능,불가능,미상;행동 부정,결정 부정;명시 원인,동시 발생;유지,변경;활성,삭제,복원;원문 수정,정정 메모;현재,과거;성공,실패,부분;일치,불일치;문장,부분구간,다중구간;직접,전언,상충;완전 중복,부분 중복;해결,미해결;유효,원문 불일치;검색 중 변경,답변 중 변경;보존,유실;본인,제삼자;정정 수용,상충 교정""",
    "S": """직접 사실,미기록;실명,동명이인;단일 사건,복수 사건;명시 장소,미상;날짜,기간;실행,계획;명시 부정,정보 부재;전체 목록,부분 목록;단일,반복;합계,평균;최초,최후;최근 사건,최근 기록;동일 사건,다른 사건;선호 변화,상태 변화;명시 원인,미확인;확인 결과,미기록;같은 문제,유사 해결;직접 연결,추정 연결;단일 사건,다중 사건;근거 충분,불충분;일치,모순;유효 인용,무효 인용;짧음,복합 장문;정상,오타,문장 파편;동일 단어,동의어;기본형,활용형;실명,약칭;해결 가능,미해결;단일 지칭,복수 지칭;명시,생략;명시,생략;명시,생략;단일 정답,상이한 정답;맥락 있음,없음;사실 전제,거짓 전제;명시,생략;전체,주제 한정;단일 요구,다중 요구;양립,모순;일치 후보,후보 없음;행위자,참석자;행위자,수신자;동일 사건,다른 사건;동일 장소,다른 장소;날짜,범위,미상;계획,실행,취소;긍정,부정;동일 주제,다른 주제;색상,소유;km,m;AND,OR;동일 사건,교차 사건;완전 일치,일부 일치;8개 이하,24개 초과;상위,후순위;단일 근거,분산 근거;일치,상충;조건 적용,누락;정상 포함,오제외;직접 출처,전언;없음,명시 부정;정상,시간 초과,잘못된 출력""",
    "D": """있음,없음;관련,무관;충분,일부;일치,불일치;직접 답변,질문 이탈;동일,역방향;계획,실행,부정;사건시각,작성시각;현재 버전,폐기 버전;동일 사건,상이 사건;정확 구간,과도한 인용;단일,다중;단일,분산;직접,추론;없음,하나,복수;정보 부재,모순;명시,추정;단위 일치,변환,불일치;명시 부정,무기록;일치,과장;정상,환각,형식 오류;정상,오승인,오거부;변경 없음,수정,삭제;직답,필요 확인,불필요 확인;정상,누락 필드,무효 인용""",
}


def build_registry(prompt, cases):
    section = prompt.split("기록 변수 R01–R68:")[1].split("각 변수에는")[0]
    entries = re.findall(r"\b([RSLD]\d{2}) ([^;\r\n]+)", section)
    names = {key: value.rstrip(".") for key, value in entries}
    expected = {
        f"{prefix}{i:02}"
        for prefix, count in [("R", 68), ("S", 62), ("L", 80), ("D", 25)]
        for i in range(1, count + 1)
    }
    if set(names) != expected:
        raise ValueError("Catalog IDs differ from specification")
    variants = {
        prefix: [v.split(",") for v in rows.split(";")] for prefix, rows in VARIANTS.items()
    }
    owners = {
        "R": ["pma/store.py", "pma/facts.py"],
        "S": ["pma/models.py", "pma/service.py"],
        "L": ["pma/facts.py", "pma/store.py"],
        "D": ["pma/grounding.py", "pma/answer_review.py"],
    }
    result = []
    for key, name in names.items():
        prefix, index = key[0], int(key[1:])
        linked = [c for c in cases if key in c["variable_ids"]]
        values = (
            variants[prefix][index - 1]
            if prefix != "L"
            else [
                f"{name}의 명시적 근거 있음",
                f"{name}은 추정만 가능",
                f"{name}의 반례 또는 근거 없음",
            ]
        )
        result.append(
            dict(
                id=key,
                domain={"R": "record", "S": "search", "L": "relation", "D": "answer"}[prefix],
                name=name,
                definition=f"{name}의 값에 따라 검색·관계·답변의 근거가 달라지는지 검증한다.",
                variants=values,
                risk_level="P0"
                if any(c["priority"] == "P0" for c in linked)
                else "P1"
                if linked
                else "P2",
                owner_modules=owners[prefix],
                current_support="unassessed",
                case_ids=[c["case_id"] for c in linked],
                acceptance_rules=[
                    "원문 구간과 버전이 일치해야 한다.",
                    "명세 등록만으로 검증 완료를 표시하지 않는다.",
                    "변수 값별 실행과 의미 검토가 완료된 범위만 verified로 표시한다.",
                ],
                review_status="fixture_author_reviewed_not_independent",
            )
        )
    return result


def write_catalog(prompt_path):
    cases = build()
    variables = build_registry(Path(prompt_path).read_text(encoding="utf-8"), cases)
    for filename, value in [("scenario_variables.json", variables), ("scenario_cases.json", cases)]:
        Path("data", filename).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("prompt")
    write_catalog(parser.parse_args().prompt)
