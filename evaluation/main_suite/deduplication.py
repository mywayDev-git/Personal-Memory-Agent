"""Consolidate equivalent executable fixtures while preserving variable coverage."""

import copy
import json
import unicodedata


def question_key(value):
    # Ignore display whitespace only. Keep identifiers, punctuation and negation intact.
    return " ".join(unicodedata.normalize("NFC", value).split())


def execution_key(case):
    metadata = {"id", "family", "evaluation_family", "variables", "priority", "variant",
                "review_checklist", "coverage_gaps", "automated_from_review", "source_case_ids",
                "related_families", "variable_variants", "behavior_case_ids"}
    payload = {key: value for key, value in case.items() if key not in metadata}
    payload["question"] = question_key(case["question"])
    # Step inputs and records remain byte-for-byte significant; different conditions never merge.
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def consolidate(cases, variables):
    grouped, aliases = {}, {}
    for original in cases:
        key = execution_key(original)
        if key not in grouped:
            case = copy.deepcopy(original)
            case.update(source_case_ids=[], related_families=[], variable_variants={})
            grouped[key] = case
        case = grouped[key]
        aliases[original["id"]] = case["id"]
        case["source_case_ids"].append(original["id"])
        if original["family"] not in case["related_families"]:
            case["related_families"].append(original["family"])
        for vid in original["variables"]:
            variants = case["variable_variants"].setdefault(vid, [])
            if original["variant"] not in variants:
                variants.append(original["variant"])
            if vid not in case["variables"]:
                case["variables"].append(vid)
        for field in ("coverage_gaps", "review_checklist", "behavior_case_ids"):
            for value in original.get(field, []):
                if value not in case.setdefault(field, []):
                    case[field].append(value)
        case["priority"] = min(case["priority"], original["priority"])
        if original["variant"] == "normal":
            case["variant"] = "normal"
    for variable in variables:
        variable["cases"] = list(dict.fromkeys(aliases[cid] for cid in variable["cases"]))
    return list(grouped.values())
