"""Legacy probe results never masquerade as semantic answer grades."""

import json
from pathlib import Path

from .schema import Case, Dataset, Result, content_hash


def load_dataset(path):
    path = Path(path)
    value = json.loads(path.read_text("utf-8"))
    if isinstance(value, dict):
        return Dataset.model_validate(value)
    if not isinstance(value, list):
        raise ValueError("Expected a dataset object or legacy case list")
    digest = content_hash(value)
    cases = []
    for row in value:
        question = row.get("question")
        if question is None:
            questions = row.get("questions", [])
            question = questions[-1]["text"] if questions else None
        if not question:
            raise ValueError("Legacy case has no question")
        behavior = (
            "clarify"
            if row.get("expected_clarification")
            else "abstain"
            if row.get("expected_status") == "insufficient_evidence"
            else "answer"
        )
        cases.append(
            Case(
                id=row.get("case_id", row.get("id")),
                question=question,
                expected_answer=row.get("expected")
                or " / ".join(row.get("expected_facts", []))
                or None,
                question_type=row.get("category", "legacy"),
                expected_behavior=behavior,
                metadata={
                    "legacy_source_hash": digest,
                    "legacy_import_only": True,
                    "variable_ids": row.get("variable_ids", []),
                },
            )
        )
    return Dataset(
        id=path.stem + "-" + digest[:12], name=path.stem, version=digest[:12], cases=cases
    )


def adapt(row):
    if "verdict" in row:
        return Result.model_validate(row)
    status = row.get("status")
    error = row.get("error") or status == "BLOCKED"
    return Result(
        case_id=str(row.get("case_id", row.get("id", ""))),
        verdict="error"
        if error
        else "not_applicable"
        if status == "UNASSESSED"
        else "pending_review",
        actual_answer="\n".join(row["actual_claims"]) if row.get("actual_claims") else None,
        latency_ms=row["latency_seconds"] * 1000
        if row.get("latency_seconds") is not None
        else None,
        error_type="unknown" if error else None,
        evaluation={
            "grading_method": "legacy_import",
            "grading_version": "legacy-ungraded-v1",
            "legacy_status": status,
            "answer_correct": None,
            "scope": "legacy probe; semantic answer not graded",
        },
    )
