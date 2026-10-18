"""Use the existing generation/review contract with complete frozen source text."""

from scripts.memory_agent.llm_client import model_phase

from ..models import LocalModels


class ChatLocalModels(LocalModels):
    def structured(self, prompt, data, schema, max_tokens=None):
        if "proposed_answer" in data and max_tokens is None:
            item_count = len(data["proposed_answer"].get("items", []))
            max_tokens = min(self.settings.llm.max_tokens, 1024 + 1024 * item_count)
        if "proposed_answer" in data or ("question" in data and "feedback" in data):
            prompt = (
                "[기억 대화 필수 정책] 질문에 직접 답하는 사실만 원문에서 확인한다. "
                "'아직 주지 않았다'는 명시적 부정 사실이다. 이를 '줬는지 모른다'로 약화하면 오답이다. "
                "'앞으로도 절대' 질문은 미래의 영구 결정을 묻는다. 과거 취소만 반복하지 말고 "
                "그런 미래 결정은 기록으로 확인할 수 없음을 직접 답한다. "
                "'누구야/어떤 관계'에는 신원·직업·사용자와의 관계를 답한다. 그 사람의 선물 사건만 "
                "나열하거나 '특정 사람'이라고 답하면 relevant=false, fulfillment=missing이다. "
                "일정 서술은 실행 증거가 아니다. '회의는 화요일이다'를 '화요일에 회의가 열렸다'로 "
                "바꾸면 unsupported, issue=execution이다. 원문의 시제와 실행 여부를 보존한다. "
                "왜/이유 질문에서 변경 사실을 반복한 '변경했기 때문에 변경했다'는 원인 설명이 아니다. "
                "원문에 동기·원인이 없으면 이유는 확인 불가이며 추정하거나 순환 설명하지 않는다. "
                "상충 기록의 입력 순서·ID·저장일은 사건 순서나 우선순위가 아니다. "
                "원문에 변경 순서나 사건 날짜가 없으면 어느 쪽이 최종인지 확정하지 않는다. "
                "질문이 호텔 예약을 묻는데 여행 계획만 답하면 무관한 답이다. 사용자의 가정은 기록이 아니다. "
                "회사/동아리처럼 구별하는 말이 질문에 있으면 같은 이름이라도 그 역할의 원문을 사용한다. "
                "'누구야' 질문에는 해당 인물의 기록된 직업이나 관계 설명이 직접 답변이다. "
                "직업만 기록되어 있어도 신원 설명으로 relevant=true, fulfillment=direct로 평가할 수 있다. "
                "다른 역할의 동명이인 직업을 선택한 사람에게 붙이면 unsupported이다. "
                "알 수 없는 사항은 확인된 사실과 분리해 한계를 명시한다. "
                "검토에서는 순환 원인 설명·근거 없는 최종 판단은 unsupported, "
                "묻지 않은 관련 사실만 나열한 답변은 relevant=false, fulfillment=missing으로 판정한다. "
                + prompt
            )
        if "proposed_answer" in data:
            phase = "review"
        elif "feedback" in data:
            phase = "generation"
        elif "history" in data or "current_question" in data:
            # The automatic orchestrator owns routing/general phase labels.
            return super().structured(prompt, data, schema, max_tokens)
        else:
            phase = "context_selection"
        with model_phase(phase):
            return super().structured(prompt, data, schema, max_tokens)

    @staticmethod
    def compact_evidence(evidence):
        rows = LocalModels.compact_evidence(evidence)
        for row, source in zip(rows, evidence, strict=True):
            row["source_context"] = source["source_text"]
        return rows
