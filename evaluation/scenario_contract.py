"""Mechanical checks cannot certify semantic gold or independent human review."""

import json
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1] / "data"
    return tuple(
        json.loads((root / name).read_text(encoding="utf-8"))
        for name in ("scenario_variables.json", "scenario_cases.json")
    )


def validate(variables, cases):
    errors = []
    expected = {
        f"{p}{i:02}"
        for p, n in [("R", 68), ("S", 62), ("L", 80), ("D", 25)]
        for i in range(1, n + 1)
    }
    ids = [v["id"] for v in variables]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        errors.append("GOLD_SPEC_INVALID: registry IDs")
    cids = [c["case_id"] for c in cases]
    if len(cids) != len(set(cids)) or not {f"T{i:02}" for i in range(1, 49)} <= set(cids):
        errors.append("GOLD_SPEC_INVALID: case IDs")
    sources, events = {}, {}
    required = {
        "case_id",
        "variable_ids",
        "category",
        "priority",
        "split",
        "records",
        "question",
        "expected_status",
        "expected_facts",
        "forbidden_claims",
        "gold_evidence_spans",
        "required_relation_types",
        "expected_clarification",
        "expected_exclusions",
        "review_status",
        "failure_stage",
        "implementation_status",
    }
    for c in cases:
        cid = c["case_id"]
        if not required <= c.keys():
            errors.append(f"{cid}: missing fields")
        if not set(c["variable_ids"]) <= expected:
            errors.append(f"{cid}: unknown variable")
        if set(c["expected_facts"]) & set(c["forbidden_claims"]):
            errors.append(f"{cid}: contradictory gold")
        if c["split"] not in {"development", "holdout"}:
            errors.append(f"{cid}: invalid split")
        for r in c["records"]:
            for table, key in [(sources, r["text"]), (events, r["event_id"])]:
                if key in table and table[key] != c["split"]:
                    errors.append(f"{cid}: split leakage")
                table[key] = c["split"]
        for span in c["gold_evidence_spans"]:
            try:
                i = span["record"]
                if not isinstance(i, int) or i < 0:
                    raise ValueError("record index")
                text = c["records"][i]["text"]
                if span.get("version", 1) != 1:
                    if span["version"] != 2:
                        raise ValueError("version")
                    text = next(
                        m["text"]
                        for m in c.get("lifecycle", [])
                        if m["operation"] == "update" and m["record"] == i
                    )
                a, b = span["start"], span["end"]
                if not (0 <= a < b <= len(text)) or text[a:b] != span["quote"]:
                    raise ValueError("span")
            except KeyError, IndexError, TypeError, ValueError, StopIteration:
                errors.append(f"{cid}: EVIDENCE_SPAN_INVALID")
    for v in variables:
        linked = {c["case_id"] for c in cases if v["id"] in c["variable_ids"]}
        if set(v["case_ids"]) != linked or not v["variants"]:
            errors.append(f"{v['id']}: invalid links or variants")
        if v["current_support"] == "verified":
            errors.append(f"{v['id']}: execution evidence required before verified")
    return errors


if __name__ == "__main__":
    errors = validate(*load())
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
    raise SystemExit(bool(errors))
