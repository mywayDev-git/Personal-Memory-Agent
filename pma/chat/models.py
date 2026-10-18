"""Use the existing generation/review contract with complete frozen source text."""

from ..models import LocalModels


class ChatLocalModels(LocalModels):
    def structured(self, prompt, data, schema, max_tokens=None):
        if "proposed_answer" in data or ("question" in data and "feedback" in data):
            prompt = (
                "[고정 근거 대화 필수 정책] 질문에 직접 답하는 사실만 원문에서 확인한다. "
                "왜/이유 질문에서 변경 사실을 반복한 '변경했기 때문에 변경했다'는 원인 설명이 아니다. "
                "원문에 동기·원인이 없으면 이유는 확인 불가이며 추정하거나 순환 설명하지 않는다. "
                "상충 기록의 입력 순서·ID·저장일은 사건 순서나 우선순위가 아니다. "
                "원문에 변경 순서나 사건 날짜가 없으면 어느 쪽이 최종인지 확정하지 않는다. "
                "질문이 호텔 예약을 묻는데 여행 계획만 답하면 무관한 답이다. 사용자의 가정은 기록이 아니다. "
                "회사/동아리처럼 구별하는 말이 질문에 있으면 같은 이름이라도 그 역할의 원문을 사용한다. "
                "알 수 없는 사항은 확인된 사실과 분리해 한계를 명시한다. "
                "검토에서는 순환 원인 설명·근거 없는 최종 판단은 unsupported, "
                "묻지 않은 관련 사실만 나열한 답변은 relevant=false, fulfillment=missing으로 판정한다. "
                + prompt
            )
        return super().structured(prompt, data, schema, max_tokens)

    @staticmethod
    def compact_evidence(evidence):
        rows = LocalModels.compact_evidence(evidence)
        for row, source in zip(rows, evidence, strict=True):
            row["source_context"] = source["source_text"]
        return rows
