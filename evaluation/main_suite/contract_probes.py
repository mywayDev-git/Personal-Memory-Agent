"""Real product input-contract checks, separate from generation-model accuracy."""

from pydantic import ValidationError

from pma.errors import AppError
from pma.imports import TextImporter


def execute_contract(store, contract):
    kind = contract["kind"]
    before = store.stats()
    code, actual = None, None
    try:
        if kind == "import":
            actual = TextImporter(store).preview(contract["filename"], contract["text"])
        elif kind in {"record_input", "query_input"}:
            from pma.web import QueryInput, RecordInput
            model = RecordInput if kind == "record_input" else QueryInput
            actual = model.model_validate(contract["input"]).model_dump()
        else:
            raise ValueError("UNKNOWN_INPUT_CONTRACT")
    except ValidationError:
        code = "VALIDATION_ERROR"
    except AppError as exc:
        code = exc.code
    preserved = (kind not in {"record_input", "query_input"} or code is not None or
                 all(actual.get(key) == value for key, value in contract["input"].items()))
    passed = code == contract["expected_error"] and store.stats() == before and preserved
    return {"probe": {"passed": passed, "model_accuracy_sample": False,
            "scope": "input_rejection_only" if contract["expected_error"] else "input_acceptance_only", "expected_error": contract["expected_error"],
            "actual_error": code, "actual_result": actual,
            "input_preserved": preserved,
            "no_records_created": store.stats() == before}}
