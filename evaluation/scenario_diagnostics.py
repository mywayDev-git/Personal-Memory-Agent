"""Evidence-driven failure labels. Unknown stages stay unknown."""

STAGES = set(
    """INPUT_INVALID STORE_FAILURE EXTRACTION_MISSING EXTRACTION_INVALID
EVIDENCE_SPAN_INVALID FACT_PROJECTION_ERROR RELATION_LINK_MISSING RELATION_LINK_WRONG
QUERY_UNDERSTANDING_ERROR ENTITY_FILTER_ERROR ROLE_FILTER_ERROR TEMPORAL_FILTER_ERROR
STATE_FILTER_ERROR KEYWORD_RETRIEVAL_MISS VECTOR_RETRIEVAL_MISS FUSION_RANKING_MISS
TOPK_TRUNCATION CANDIDATE_SELECTION_ERROR AMBIGUITY_RESOLUTION_ERROR
EVIDENCE_VALIDATION_ERROR ANSWER_UNSUPPORTED_CLAIM ANSWER_INCORRECT ANSWER_OVER_ABSTENTION
CITATION_INVALID STALE_MEMORY_USED API_CONTEXT_ERROR RUNTIME_ERROR GOLD_SPEC_INVALID""".split()
)


def diagnose(observation):
    failures = []
    if observation.get("exception"):
        failures.append("RUNTIME_ERROR")
    if observation.get("projection_mismatch"):
        failures.append("FACT_PROJECTION_ERROR")
    if observation.get("forbidden_claim_found"):
        failures.append("ANSWER_UNSUPPORTED_CLAIM")
    if observation.get("status_mismatch"):
        failures.append(
            "ANSWER_OVER_ABSTENTION"
            if observation.get("actual_status") == "insufficient_evidence"
            else "ANSWER_INCORRECT"
        )
    if observation.get("missing_required_evidence"):
        # Do not invent an internal rank or role cause without trace evidence.
        failures.append("CANDIDATE_SELECTION_ERROR")
    return dict(
        primary_failure_stage=failures[0] if failures else None,
        secondary_failure_stages=failures[1:],
    )
