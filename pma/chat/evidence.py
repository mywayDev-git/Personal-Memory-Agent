"""Pin accepted claim citations to the exact frozen source revision and span."""

import re
from copy import deepcopy


def causal_claims_supported(question, response, evidence):
    """Conservative extra guard against turning a repeated event into its own cause."""
    if not re.search(r"왜|이유|원인", question):
        return True
    sources = {row["id"]: row["source_text"] for row in evidence}
    causal = r"때문|덕분|탓|느라|므로|어서|아서|여서|와서|워서|해서|라서|니까|위해"
    for item in response["items"]:
        if re.search(causal, item["text"]) and not any(
            re.search(causal, sources[cid]) for cid in item["citations"]
        ):
            return False
    return True


def reviewed_citations(response, review, evidence):
    result = deepcopy(response)
    sources = {row["id"]: row for row in evidence}
    details = []
    for checked in review["items"]:
        index = checked["index"]
        refs = checked["evidence"]
        allowed = {ref["id"] for ref in refs}
        result["items"][index]["citations"] = [
            cid for cid in result["items"][index]["citations"] if cid in allowed
        ]
        for ref in refs:
            row = sources[ref["id"]]
            start = row["source_text"].find(ref["quote"])
            if start < 0:
                raise ValueError("INVALID_SOURCE_SPAN")
            details.append(
                {
                    "item_index": index,
                    "memory_id": row["id"],
                    "record_id": row["record_id"],
                    "revision_id": row["revision_id"],
                    "quote": ref["quote"],
                    "start": start,
                    "end": start + len(ref["quote"]),
                }
            )
    result["citation_details"] = details
    return result
