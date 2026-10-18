"""Opt-in, human-readable console view; no file logging or model payload dumps."""

import threading
from datetime import datetime


def readable(value, limit=500):
    text = " ".join(str(value or "").split())
    text = "".join(c for c in text if c.isprintable())
    return text if len(text) <= limit else text[:limit] + "… (이하 생략)"


class ConsoleTrace:
    def __init__(self):
        self.lock = threading.Lock()

    def write(self, title, lines):
        with self.lock:
            print(f"\n[{datetime.now():%H:%M:%S}] {title}", flush=True)
            for line in lines:
                print("  " + line, flush=True)

    def intro(self, path):
        self.write("저장·검색 과정 보기 — TEST 모드", [
            "브라우저에서 기록을 저장하거나 질문하면 이 창에 실제 처리 과정이 표시됩니다.",
            "이 모드는 실제 DB를 사용하며 기록·질문·답변의 처리 과정을 표시합니다.",
            "입력한 기록·질문·답변이 이 창에 표시됩니다. 별도 로그 파일은 만들지 않습니다.",
            f"저장 위치: {path}",
            "저장: 원문·버전 저장 → AI 기억 추출·원문 검증 → 의미 벡터 생성 → 검색 가능",
            "검색: 질문 해석 → 날짜·인물·행동 조건 → 의미+키워드 순위 결합 → 근거 선택 → 답변",
            "예시 질문: ‘지난주에 누구를 만났지?’, ‘지연이가 받고 싶다고 한 선물은?’",
            "기존 단일 질문은 저장하지 않습니다. AI 대화 탭의 이력과 근거는 로컬 DB에 저장합니다.",
            "검색 점수는 정확도 확률이 아닙니다.",
        ])

    def __call__(self, event):
        stage = event["stage"]
        lines = []
        title = "검색"
        if stage == "record_saved":
            title = "원문 저장 완료 · 기억 처리 대기"
            lines = [readable(event["text"]), "원문과 버전을 DB에 저장했습니다."]
        elif stage == "processing_start":
            title = "기록 처리 · 기억 추출 및 검증 중"
            lines = [f"기록: {readable(event['record_id'])}", readable(event["text"])]
        elif stage == "embedding_start":
            title = "기억 추출·검증 완료 · 의미 벡터 생성 중"
            lines = [f"추출된 기억 {len(event['memories'])}개"]
            lines += [f"- {readable(m['content'])}" for m in event["memories"]]
        elif stage == "processing_done":
            title = "기록 처리 완료"
            lines = [f"기록: {readable(event['record_id'])}",
                     f"기억·근거·검색 벡터 저장 완료: {event['count']}개",
                     "검색할 수 있습니다." if event['count'] else "추출된 기억이 없어 검색 대상은 없습니다."]
        elif stage in {"processing_failed", "worker_failed"}:
            title = "기록 처리 실패" if stage == "processing_failed" else "백그라운드 작업 실패"
            lines = [f"단계: {event['phase']}", f"원인: {event['reason']}",
                     f"해결 방법: {event['remedy']}",
                     f"오류 코드: {event['code']} / 종류: {event['exception_type']}"]
            if stage == "processing_failed":
                lines += [f"기록: {readable(event['record_id'])}",
                          "원문은 보관되어 있습니다. 문제 해결 후 앱에서 재시도하세요."]
            else:
                lines.append("백그라운드 작업은 자동으로 다시 시도합니다.")
        elif stage == "question":
            title = "질문 접수 · 검색 조건 해석"
            lines = [readable(event['question'])]
        elif stage == "understand_fallback":
            lines = ["AI 질문 해석에 실패하여 기본 해석으로 검색을 계속합니다."]
        elif stage == "search_scope":
            filters = event['filters']
            lines = [f"검색 기간: {filters.get('date_from') or '시작 제한 없음'} ~ "
                     f"{filters.get('date_to') or '종료 제한 없음'}",
                     f"검색 가능한 기억 {event['total']}개 → 조건 통과 {event['count']}개",
                     "인물·행동·장소·시간 등 질문에 해당하는 조건을 적용했습니다."]
        elif stage == "excluded":
            reasons = {
                "facts_pending": "검색 자료 구축 대기",
                "relation_state_or_quantity": "행동·상태·수량 조건 불일치",
                "requested_object": "질문 대상 불일치",
                "preference_change": "선호 변화 조건 불일치",
                "activity_state": "활동 상태 불일치",
                "location": "장소 불일치",
                "explicit_named_person": "지정한 인물 불일치",
                "unknown_filtered_date": "기간 검색에서 날짜가 불명확함",
                "date_range": "검색 기간 밖의 기억",
            }
            reason = reasons.get(event['reason'], "질문 조건 불일치")
            lines = [f"기억 {readable(event['id'])}: 제외 — {reason}"]
        elif stage == "search_methods":
            title = "의미 검색 + 키워드 검색"
            lines = ["키워드: " + ", ".join(readable(t) for t in event['terms']),
                     f"의미 후보 {event['vectors']}개 / 키워드 후보 {event['keywords']}개",
                     "두 검색의 순위와 구조 조건을 결합합니다. 같은 기억은 중복될 수 있습니다."]
        elif stage == "selection":
            lines = [f"AI 근거 선택: {len(event['selected_ids'])}개 유지, "
                     f"{len(event['excluded_ids'])}개 제외"]
        elif stage == "generation_start":
            lines = ["선택한 기억을 바탕으로 답변 작성 및 근거 검증 중…"]
        elif stage == "chat_verification":
            title = "AI 대화 · 근거 검증"
            lines = ["검증 통과" if event["supported"] else "검증 미통과 · 수정 또는 답변 보류"]
        elif stage == "chat_result":
            title = "AI 대화 · 답변 완료"
            response = event["response"]
            lines = ["질문: " + readable(event["question"])]
            lines += [readable(item["text"], 1000) for item in response.get("items", [])]
            if response.get("clarification"):
                lines.append(readable(response["clarification"]))
            if response["status"] == "insufficient_evidence":
                lines.append("선택된 기록에서 충분한 근거를 확인하지 못했습니다.")
        elif stage == "result":
            title = "검색 결과"
            response = event['response']
            results = response.get('results', [])
            lines = [f"최종 근거 {len(results)}개 (최대 8개)"]
            for i, result in enumerate(results, 1):
                lines += [f"{i}. {readable(result['content'])}",
                          f"   원문: {readable(result.get('source_text'))}"]
            for item in response.get('items', []):
                lines.append("답변: " + readable(item.get('text'), 1000))
            if response.get('status') == 'insufficient_evidence':
                lines.append("답변할 근거가 충분하지 않습니다.")
            elif response.get('status') == 'unsupported_intent':
                lines.append("현재 지원하지 않는 질문 유형입니다.")
            if response.get('clarification'):
                lines.append(readable(response['clarification']))
            if response.get('facts_pending'):
                lines.append("검색 자료 재구축 중이므로 일부 기억이 빠질 수 있습니다.")
        if lines:
            self.write(title, lines)
