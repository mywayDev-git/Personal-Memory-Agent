
"""Memory extraction orchestration and LLM response parsing."""

import json
import re
from typing import Any

import requests

from .llm_client import call_llm
from .exceptions import ExtractionError
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_SCHEMA_PATH = (
    PROJECT_ROOT / "schema" / "memory_extraction_output.schema.json"
)

def load_output_schema() -> dict:
    with OUTPUT_SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)

def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object, including one wrapped in a Markdown code fence."""
    if not isinstance(text, str) or not text.strip():
        raise ExtractionError("LLM response is empty.")

    candidate = text.strip()

    # Remove a surrounding Markdown JSON code fence.
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        candidate,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced:
        candidate = fenced.group(1).strip()

    try:
        result = json.loads(candidate)
    except json.JSONDecodeError:
        # Allow explanatory text around a single JSON object.
        start = candidate.find("{")
        if start == -1:
            raise ExtractionError("No JSON object found in LLM response.")

        try:
            result, _ = json.JSONDecoder().raw_decode(candidate[start:])
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                f"Could not parse JSON response: {exc}"
            ) from exc

    if not isinstance(result, dict):
        raise ExtractionError("Extraction output must be a JSON object.")

    return result

def validate_extraction_shape(
    result: dict[str, Any],
) -> dict[str, Any]:
    """LLM 원본 출력의 기본 구조를 검증한다."""
    if not isinstance(result, dict):
        raise ExtractionError(
            "Invalid extraction output: expected a JSON object"
        )

    expected_keys = {"memories"}
    actual_keys = set(result.keys())

    if actual_keys != expected_keys:
        missing = expected_keys - actual_keys
        unexpected = actual_keys - expected_keys

        raise ExtractionError(
            "Invalid extraction output structure: "
            f"missing keys: {sorted(missing)}, "
            f"unexpected keys: {sorted(unexpected)}"
        )

    if not isinstance(result["memories"], list):
        raise ExtractionError(
            "Invalid extraction output: 'memories' must be a list"
        )

    return result


def extract_memories(
    session: requests.Session,
    endpoint: str,
    model: str | None,
    prompt: str,
    source_text: str,
    source_context: dict[str, Any],
    timeout: float = 180.0,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    seed: int = 42,
    top_p: float = 1.0,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    """Call the LLM and return parsed extraction data and request metadata."""
    output_schema = load_output_schema()

    content, metadata, latency = call_llm(
        session=session,
        endpoint=endpoint,
        model=model,
        prompt=prompt,
        source_text=source_text,
        source_context=source_context,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        output_schema=output_schema,
    )

    result = extract_json(content)
    result = validate_extraction_shape(result)

    return result, metadata, latency
