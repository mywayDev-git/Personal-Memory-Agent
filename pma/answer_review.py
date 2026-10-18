"""Internal answer review contract; never changes stored extraction or search."""

from scripts.memory_agent.validator import schema_errors

from .diagnostics import Reason, Stage
from .validation_diagnostics import check, observed_validation, retry

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items", "fulfillment", "abstention", "reason"],
    "properties": {
        "fulfillment": {"enum": ["direct", "limited", "missing"]},
        "abstention": {"enum": ["appropriate", "excessive", "not_applicable"]},
        "reason": {"type": "string", "maxLength": 240},
        "items": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["index", "support", "relevant", "issue", "answer_quote", "evidence"],
                "properties": {
                    "index": {"type": "integer", "minimum": 0},
                    "support": {"enum": ["supported", "unsupported", "uncertain"]},
                    "relevant": {"type": "boolean"},
                    "issue": {
                        "enum": [
                            "none",
                            "person",
                            "time",
                            "negation",
                            "execution",
                            "quotation",
                            "cause",
                            "other",
                        ]
                    },
                    "answer_quote": {"type": "string", "maxLength": 2000},
                    "evidence": {
                        "type": "array",
                        "maxItems": 8,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["id", "quote"],
                            "properties": {
                                "id": {"type": "string"},
                                "quote": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
            },
        },
    },
}


@observed_validation(Stage.REVIEW_CHECK)
def validate_review(review, response, evidence):
    if schema_errors(review, REVIEW_SCHEMA):
        raise ValueError("INVALID_REVIEW_SCHEMA")
    items = response["items"]
    if sorted(r["index"] for r in review["items"]) != list(range(len(items))):
        raise ValueError("INVALID_REVIEW_COVERAGE")
    sources = {r["id"]: r for r in evidence}
    for row in review["items"]:
        item = items[row["index"]]
        if not row["answer_quote"] or row["answer_quote"] not in item["text"]:
            raise ValueError("INVALID_REVIEW_ANSWER_QUOTE")
        if row["support"] == "supported" and not row["evidence"]:
            raise ValueError("MISSING_REVIEW_EVIDENCE")
        for ref in row["evidence"]:
            if ref["id"] not in item["citations"] or ref["id"] not in sources:
                raise ValueError("INVALID_REVIEW_CITATION")
            source = sources[ref["id"]]
            texts = [source.get("source_text", "")] + [
                e["quote"] for e in source.get("evidence", [])
            ]
            if not any(ref["quote"] in text for text in texts):
                raise ValueError("INVALID_REVIEW_SOURCE_QUOTE")
    if items and review["abstention"] != "not_applicable":
        raise ValueError("INVALID_REVIEW_STATE")
    if not items and review["abstention"] == "not_applicable":
        raise ValueError("INVALID_REVIEW_STATE")
    return review


def accepted(review, response):
    if response["status"] == "insufficient_evidence":
        return review["abstention"] == "appropriate"
    return review["fulfillment"] in {"direct", "limited"} and all(
        r["support"] == "supported" and r["relevant"] and r["issue"] == "none"
        for r in review["items"]
    )


@observed_validation(Stage.ANSWER_POLICY)
def answer_found(models, question, found, trace, *, repair=True):
    """Bounded generation/review, also used by fixed-evidence experiments."""
    import requests

    from .errors import AppError
    from .grounding import claims_supported, grounded_response
    from .models import ANSWER_SCHEMA

    evidence = found["results"]
    if not evidence:
        return {"status": "insufficient_evidence", "items": []}
    response = grounded_response(found, semantic_current=True)
    structured = response is not None
    phase = "answer_generation"
    try:
        if response is None:
            response = models.answer(question, evidence)
        for attempt in range(2 if repair else 1):
            retry(attempt)
            trace(
                "answer" if not attempt else "answer_repair",
                structured=structured,
                response=response,
            )
            phase = "answer_validation"
            if schema_errors(response, ANSWER_SCHEMA):
                raise ValueError("INVALID_ANSWER")
            if (response["status"] == "answered") != bool(response["items"]):
                raise ValueError("INVALID_ANSWER_STATE")
            ids = {r["id"] for r in evidence}
            if any(c not in ids for item in response["items"] for c in item["citations"]):
                raise ValueError("INVALID_CITATION")
            attributes = claims_supported(response["items"], evidence, found["query_plan"])
            if structured and attributes:
                return {**response, "validation": "structured"}
            phase = "verification"
            review = validate_review(
                models.review(question, evidence, response), response, evidence
            )
            passed = attributes and accepted(review, response)
            check(
                "llm",
                passed,
                reason=Reason.CONDITION_MATCHED
                if passed
                else Reason.INCOMPLETE_ANSWER
                if review["fulfillment"] == "missing"
                else Reason.EXCESSIVE_ABSTENTION
                if review["abstention"] == "excessive"
                else Reason.VERIFICATION_REJECTED,
                stage=Stage.REVIEW_CHECK,
            )
            trace(
                "verification",
                attempt=attempt,
                supported=passed,
                attributes_supported=attributes,
                review=review,
            )
            if passed:
                return {**response, "validation": "model_checked"}
            if not repair or attempt:
                break
            phase = "repair_generation"
            trace("repair_start", attempt=1)
            response = models.answer(
                question,
                evidence,
                feedback={
                    "previous_answer": response,
                    "review": review,
                    "attributes_supported": attributes,
                },
            )
            structured = False
    except (ValueError, requests.RequestException, AppError) as exc:
        trace(
            "verification_error" if phase == "verification" else "answer_error",
            phase=phase,
            error=type(exc).__name__,
            code=getattr(exc, "code", None),
        )
        return {"status": "insufficient_evidence", "items": [], "validation": "rejected"}
    return {"status": "insufficient_evidence", "items": [], "validation": "rejected"}
