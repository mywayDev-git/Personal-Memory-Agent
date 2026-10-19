"""Content-free observations of generation and review, never inferred model motives."""


def citation_ids(response):
    return sorted({cid for item in response.get("items", []) for cid in item.get("citations", [])})


def attach_answer_audit(metadata, audit):
    metadata["answer_audit"] = audit
    usage = {row["id"]: row for row in audit["usage"]}
    for search in metadata.get("searches", []):
        for candidate in search.get("audit", {}).get("candidates", []):
            # Old snapshots have no stage observations; do not invent them.
            if "stages" in candidate and candidate["id"] in usage:
                observed = usage[candidate["id"]]
                candidate["stages"]["answer"] = {
                    "status": observed["status"], "reason": observed["reason"]
                }


def review_attempt(response, review, attributes, passed):
    reasons = []
    if not attributes:
        reasons.append("attributes_unsupported")
    if review.get("error"):
        reasons.append("invalid_review")
        code = review.get("reason")
        if code in {"INVALID_REVIEW_SOURCE_QUOTE", "INVALID_REVIEW_CITATION", "INCONSISTENT_REVIEW"}:
            reasons.append(code.lower())
    else:
        if review.get("fulfillment") == "missing":
            reasons.append("answer_incomplete")
        if review.get("abstention") == "excessive":
            reasons.append("excessive_abstention")
        for item in review.get("items", []):
            if item["support"] != "supported":
                reasons.append("claim_unsupported")
            if not item["relevant"]:
                reasons.append("claim_irrelevant")
            if item["issue"] != "none":
                reasons.append("review_issue_" + item["issue"])
    return {
        "draft_citations": citation_ids(response),
        "status": "passed" if passed else "rejected",
        "reasons": sorted(set(reasons)) or ([] if passed else ["details_unavailable"]),
        "reviewed_citations": sorted({
            ref["id"] for item in review.get("items", []) for ref in item["evidence"]
        }) if passed else [],
    }


def answer_audit(evidence, attempts, response, reason=None):
    cited = set(citation_ids(response))
    last = attempts[-1] if attempts else None
    usage = []
    for row in evidence:
        cid = row["id"]
        if cid in cited:
            status, why = "used", "cited"
        elif response.get("validation") == "rejected":
            status, why = "unused", "answer_rejected"
        elif last and cid in last["draft_citations"] and cid not in last["reviewed_citations"]:
            status, why = "unused", "citation_removed"
        elif last:
            status, why = "unused", "draft_not_cited"
        else:
            status, why = "not_run", reason or "details_unavailable"
        usage.append({"id": cid, "status": status, "reason": why})
    return {"version": 1, "status": response.get("validation", reason or "not_run"),
            "reason": reason, "attempts": attempts, "usage": usage}
