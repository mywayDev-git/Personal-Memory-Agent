"""Question groups for viewing; execution fixtures remain independent conditions."""

from .deduplication import question_key


def question_groups(cases):
    groups = {}
    for case in cases:
        key = question_key(case["question"])
        if key not in groups:
            groups[key] = {"id": case["id"], "question": case["question"], "priority": case.get("priority"),
                           "variables": [], "splits": [], "expected_answers": [], "conditions": []}
        group = groups[key]
        for vid in case.get("variables", []):
            if vid not in group["variables"]:
                group["variables"].append(vid)
        if case["split"] not in group["splits"]:
            group["splits"].append(case["split"])
        if case.get("expected_answer") not in group["expected_answers"]:
            group["expected_answers"].append(case.get("expected_answer"))
        if case.get("priority"):
            group["priority"] = min(group["priority"] or case["priority"], case["priority"])
        group["conditions"].append(case)
    return list(groups.values())
