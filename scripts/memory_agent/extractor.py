
"""Memory extraction orchestration and LLM response parsing."""

import json
import re
import copy
from typing import Any

import requests

from .llm_client import call_llm
from .exceptions import ExtractionError
from .validator import schema_errors
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_SCHEMA_PATH = (
    PROJECT_ROOT / "schema" / "memory_extraction_output.schema.json"
)


def sentence_units(text):
    """Keep verbatim sentences; punctuation inside dates/numbers is not a boundary."""
    return [match.group().strip() for match in
            re.finditer(r'[^\n]+?(?:[.!?](?=\s|$)|(?=\n|$))', text)
            if match.group().strip()]


def grounded_schema(schema, units):
    schema = copy.deepcopy(schema)
    schema['$defs']['evidence_item'] = {
        'type': 'object', 'additionalProperties': False,
        'required': ['sentence_id'],
        'properties': {'sentence_id': {'enum': [f's{i}' for i in range(len(units))]}}}
    time_schema = schema['$defs']['time']
    time_schema['properties']['start'] = {'type': 'null'}
    time_schema['properties']['end'] = {'type': 'null'}
    time_schema['properties']['precision'] = {'enum': ['relative', 'unknown']}
    time_schema['properties']['certainty'] = {'const': 'uncertain'}
    return schema


def restore_evidence(result, units):
    result = copy.deepcopy(result)
    lookup = {f's{i}': quote for i, quote in enumerate(units)}
    for memory in result['memories']:
        evidence = []
        for item in memory['evidence']:
            key = item.get('sentence_id')
            if key not in lookup:
                raise ExtractionError(f'Invalid evidence sentence_id: {key!r}')
            quote = {'quote': lookup[key]}
            if quote not in evidence:
                evidence.append(quote)
        memory['evidence'] = evidence
    return result

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
    units = sentence_units(source_text)
    output_schema = grounded_schema(load_output_schema(), units)
    prompt += '''\n이번 호출의 evidence는 quote 대신 sentence_id를 출력한다.
입력은 문장 ID와 원문 배열이다. 기억을 직접 뒷받침하는 문장 ID만 선택한다.
인접 문장의 날짜나 주체를 다른 사건에 옮기지 않는다. ID는 내용에 포함하지 않는다.
time.start/end는 반드시 null, certainty는 uncertain이다. raw는 선택한 근거 속 시간 표현이다.
'''

    content, metadata, latency = call_llm(
        session=session,
        endpoint=endpoint,
        model=model,
        prompt=prompt,
        source_text=json.dumps([{'sentence_id': f's{i}', 'text': quote}
                               for i, quote in enumerate(units)], ensure_ascii=False),
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
    errors = schema_errors(result, output_schema)
    if errors:
        raise ExtractionError('Invalid grounded extraction: ' + '; '.join(errors))
    return restore_evidence(result, units), metadata, latency
