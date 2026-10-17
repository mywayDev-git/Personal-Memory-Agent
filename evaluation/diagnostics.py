"""Only observed evidence transitions may establish a failure stage."""


def diagnose(case, events, evaluation, response_behavior):
    def complete(ids):
        return all(set(ids).intersection(g) for g in case.gold_groups.values())

    unknown = dict(
        error_type="unknown", first_verified_failure_stage=None, confidence="unavailable"
    )
    if response_behavior == "clarify" and case.expected_behavior == "answer":
        return dict(error_type="unnecessary_clarification", confidence="observed")
    if response_behavior == "answer" and case.expected_behavior == "clarify":
        return dict(error_type="missing_clarification", confidence="observed")
    previous = None
    for event in events:
        stage = event["stage"]
        if stage not in {"retrieval_merge", "evidence"}:
            continue
        if stage == "retrieval_merge":
            previous = complete([c["id"] for c in event.get("candidates", [])])
        elif case.gold_groups and previous is True and not complete(event.get("ids", [])):
            return dict(
                error_type="evidence_selection_miss",
                first_verified_failure_stage="evidence",
                confidence="verified",
            )
    if (
        evaluation.get("answer_correct") is False
        and evaluation.get("final_evidence_complete") is True
    ):
        return dict(error_type="answer_generation_error", confidence="verified")
    if evaluation.get("claims_supported") is False:
        return dict(error_type="unsupported_claim", confidence="verified")
    return unknown
