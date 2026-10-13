
"""JSON Schema and evidence validation for memory extraction."""

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def load_schema(path: str | Path) -> dict[str, Any]:
    """Load a JSON Schema file."""
    schema_path = Path(path)

    try:
        import json

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"Failed to load JSON Schema: {schema_path}"
        ) from exc

    if not isinstance(schema, dict):
        raise ValueError(f"JSON Schema must be an object: {schema_path}")

    Draft202012Validator.check_schema(schema)
    return schema


def schema_errors(
    data: Any,
    schema: dict[str, Any],
) -> list[str]:
    """Return human-readable validation errors."""
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )

    errors = sorted(
        validator.iter_errors(data),
        key=lambda error: (
            list(map(str, error.absolute_path)),
            error.message,
        ),
    )

    return [
        f"{format_path(error.absolute_path)}: {error.message}"
        for error in errors
    ]


def format_path(path: Any) -> str:
    """Format a JSON path for readable error messages."""
    parts = list(path)

    if not parts:
        return "$"

    formatted = "$"
    for part in parts:
        if isinstance(part, int):
            formatted += f"[{part}]"
        else:
            formatted += f".{part}"

    return formatted


def is_schema_valid(
    data: Any,
    schema: dict[str, Any],
) -> bool:
    """Return whether data satisfies the provided schema."""
    return not schema_errors(data, schema)


def evidence_checks(
    result: dict[str, Any],
    source_text: str,
) -> list[str]:
    """Check whether every evidence quote occurs in the source text."""
    errors: list[str] = []
    memories = result.get("memories")

    if not isinstance(memories, list):
        return ["$.memories: expected an array"]

    for index, memory in enumerate(memories):
        path = f"$.memories[{index}].evidence"

        if not isinstance(memory, dict):
            errors.append(f"$.memories[{index}]: expected an object")
            continue

        evidence = memory.get("evidence")

        if not isinstance(evidence, list):
            errors.append(f"{path}: expected an array")
            continue

        if not evidence:
            errors.append(f"{path}: expected at least one evidence item")
            continue

        for evidence_index, item in enumerate(evidence):
            item_path = f"{path}[{evidence_index}]"

            if not isinstance(item, dict):
                errors.append(f"{item_path}: expected an object")
                continue

            quote = item.get("quote")

            if not isinstance(quote, str) or not quote.strip():
                errors.append(
                    f"{item_path}.quote: expected a non-empty string"
                )
                continue

            if quote not in source_text:
                errors.append(
                    f"{item_path}.quote: quote does not occur verbatim "
                    "in the source text"
                )

    return errors


def validate_extraction(
    result: dict[str, Any],
    output_schema: dict[str, Any],
) -> list[str]:
    """Validate the raw LLM extraction output."""
    return schema_errors(result, output_schema)



def validate_final_result(
    result: dict[str, Any],
    final_schema: dict[str, Any],
    source_text: str,
    skip_evidence_check: bool = False,
) -> dict[str, Any]:
    """Validate the postprocessed result and its evidence.

    Returns a report containing schema and evidence errors.
    """
    final_errors = schema_errors(result, final_schema)

    evidence_errors = (
        []
        if skip_evidence_check
        else evidence_checks(result, source_text)
    )

    return {
        "valid": not final_errors and not evidence_errors,
        "schema_valid": not final_errors,
        "evidence_valid": not evidence_errors,
        "schema_errors": final_errors,
        "evidence_errors": evidence_errors,
    }
