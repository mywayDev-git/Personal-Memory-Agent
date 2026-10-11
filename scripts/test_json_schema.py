#!/usr/bin/env python3

import argparse
import copy
import json
from pathlib import Path

import requests
from jsonschema import Draft202012Validator


DEFAULT_URL = "http://127.0.0.1:8081/v1/chat/completions"
DEFAULT_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "schema"
    / "memory_extraction_output_v4.schema.json"
)
SOURCE_TEXT = """
이번 학기에 데이터베이스를 공부한다.
"""


def load_schema(path):
    with open(path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    Draft202012Validator.check_schema(schema)
    return schema


def minimal_schema():
    return {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string"
            },
            "count": {
                "type": "integer"
            }
        },
        "required": ["answer", "count"],
        "additionalProperties": False
    }


def simplified_memory_schema(original):
    """
    원본 memory의 필드와 enum은 유지하되,
    $ref와 조건부 스키마를 제거한 진단용 스키마를 만든다.

    이 스키마는 호환성 테스트 전용이며,
    원본 스키마를 대체하는 용도가 아니다.
    """
    defs = original.get("$defs", {})
    memory = defs.get("memory", {})

    properties = memory.get("properties", {})
    required = memory.get("required", [])

    simple_properties = {}

    for name, prop in properties.items():
        if name == "subject" or name == "object":
            simple_properties[name] = {
                "type": "object",
                "properties": {
                    "kind": {
                        "enum": [
                            "self", "entity", "literal", "unknown"
                        ]
                    },
                    "value": {
                        "type": ["string", "number", "boolean", "null"]
                    },
                    "value_type": {
                        "enum": [
                            "string", "number", "boolean",
                            "date", "datetime", "none"
                        ]
                    },
                },
                "required": ["kind", "value", "value_type"],
                "additionalProperties": False,
            }

        elif name == "target":
            simple_properties[name] = {
                "type": ["object", "null"]
            }

        elif name == "time":
            simple_properties[name] = {
                "type": "object",
                "properties": {
                    "raw": {"type": ["string", "null"]},
                    "start": {"type": ["string", "null"]},
                    "end": {"type": ["string", "null"]},
                    "precision": {
                        "enum": [
                            "exact", "day", "month", "year",
                            "range", "relative", "unknown"
                        ]
                    },
                    "certainty": {
                        "enum": ["explicit", "inferred", "uncertain"]
                    },
                },
                "required": [
                    "raw", "start", "end", "precision", "certainty"
                ],
                "additionalProperties": False,
            }

        elif name == "evidence":
            simple_properties[name] = {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "quote": {
                            "type": "string",
                            "minLength": 1
                        }
                    },
                    "required": ["quote"],
                    "additionalProperties": False,
                },
            }

        else:
            simple_properties[name] = copy.deepcopy(prop)

    return {
        "type": "object",
        "properties": {
            "memories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": simple_properties,
                    "required": required,
                    "additionalProperties": False,
                },
            }
        },
        "required": ["memories"],
        "additionalProperties": False,
    }


def time_target_schema(original):
    """
    3단계 진단용 스키마.

    기존 핵심 필드:
      memory_type, content, subject, predicate, object, evidence

    이번 단계에서 추가할 필드:
      time, target

    원본 스키마의 복잡한 $ref, allOf, if/then, oneOf는
    이번 테스트에서 사용하지 않는다.
    """

    defs = original.get("$defs", {})
    memory = defs.get("memory", {})
    props = memory.get("properties", {})

    # subject와 object에 사용할 단순화된 값 참조 스키마
    value_ref_schema = {
        "type": "object",
        "properties": {
            "kind": {
                "enum": ["self", "entity", "literal", "unknown"]
            },
            "value": {
                "type": ["string", "number", "boolean", "null"]
            },
            "value_type": {
                "enum": [
                    "string", "number", "boolean",
                    "date", "datetime", "none"
                ]
            },
        },
        "required": ["kind", "value", "value_type"],
        "additionalProperties": False,
    }

    # 이번 단계에서 시험할 time 필드
    time_schema = {
        "type": "object",
        "properties": {
            "raw": {"type": ["string", "null"]},
            "start": {"type": ["string", "null"]},
            "end": {"type": ["string", "null"]},
            "precision": {
                "enum": [
                    "exact", "day", "month", "year",
                    "range", "relative", "unknown"
                ]
            },
            "certainty": {
                "enum": ["explicit", "inferred", "uncertain"]
            },
        },
        "required": [
            "raw", "start", "end", "precision", "certainty"
        ],
        "additionalProperties": False,
    }

    # 이번 단계에서는 target의 내부 구조를 제한하지 않고
    # object 또는 null인지부터 검사한다.
    target_schema = {
        "type": ["object", "null"]
    }

    # evidence의 quote가 원문 문자열인지 검사한다.
    evidence_schema = {
        "type": "array",
        "minItems": 1,
        "items": {
            "type": "object",
            "properties": {
                "quote": {
                    "type": "string",
                    "minLength": 1,
                }
            },
            "required": ["quote"],
            "additionalProperties": False,
        },
    }

    # enum은 원본 스키마의 허용값을 그대로 가져온다.
    simple_properties = {
        "memory_type": copy.deepcopy(props["memory_type"]),
        "content": copy.deepcopy(props["content"]),
        "subject": value_ref_schema,
        "predicate": copy.deepcopy(props["predicate"]),
        "object": copy.deepcopy(value_ref_schema),
        "time": time_schema,
        "target": target_schema,
        "evidence": evidence_schema,
    }

    return {
        "type": "object",
        "properties": {
            "memories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": simple_properties,
                    "required": list(simple_properties.keys()),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["memories"],
        "additionalProperties": False,
    }

def make_payload(schema, source, max_tokens):
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    """
Extract memories from the supplied Korean text.
Return exactly one JSON object that conforms to the JSON Schema supplied
in the API request. Follow the schema's field names, types, required fields,
enumerated values, and additional-property restrictions exactly.
Do not invent facts that are not supported by the source text.
For each memory, include evidence quotes copied verbatim from the source
when the schema requires evidence.
                    """
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract memories from this text:\n"
                    f"{source}"
                ),
            },
        ],
        # C 방식: 스키마를 최상위 json_schema 필드로 전달한다.
        # response_format은 함께 보내지 않는다.
        "json_schema": schema,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }


def run_test(name, schema, url, source, max_tokens):
    print(f"\n{'=' * 65}")
    print(f"TEST: {name}")
    print("=" * 65)

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        print(f"[FAIL] Invalid test schema: {exc}")
        return False

    payload = make_payload(schema, source, max_tokens)

    print("Root required:", schema.get("required"))
    print("Root properties:", list(schema.get("properties", {}).keys()))

    print("\n=== ACTUAL REQUEST SCHEMA ===")
    print(
        json.dumps(
            payload["json_schema"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n=== ACTUAL SYSTEM PROMPT ===")
    print(payload["messages"][0]["content"])

    print("\n=== ACTUAL USER PROMPT ===")
    print(payload["messages"][1]["content"])

    print("\n=== REQUEST BODY SUMMARY ===")
    print("schema transport: top-level json_schema")
    print("response_format present:", "response_format" in payload)
    print("temperature:", payload["temperature"])
    print("max_tokens:", payload["max_tokens"])
    
    try:
        response = requests.post(
            url,
            json=payload,
            timeout=180,
        )
    except requests.RequestException as exc:
        print(f"[ERROR] HTTP request failed: {exc}")
        return False

    print("HTTP status:", response.status_code)

    if not response.ok:
        print(response.text[:3000])
        return False

    try:
        body = response.json()
        choice = body["choices"][0]
        content = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        print(f"[ERROR] Unexpected API response: {exc}")
        print(response.text[:3000])
        return False

    print("Finish reason:", choice.get("finish_reason"))
    print("Usage:", json.dumps(body.get("usage", {}), ensure_ascii=False))
    print("\nGenerated content:")
    print(content)

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        print(f"[FAIL] Invalid JSON: {exc}")
        return False

    if not isinstance(result, dict):
        print("[FAIL] JSON root is not an object.")
        return False

    errors = sorted(
        Draft202012Validator(schema).iter_errors(result),
        key=lambda e: (list(map(str, e.absolute_path)), e.message),
    )

    if errors:
        print("\n[FAIL] Schema validation failed:")
        for error in errors[:30]:
            path = "$"
            for part in error.absolute_path:
                path += f"[{part}]" if isinstance(part, int) else f".{part}"
            print(f"- {path}: {error.message}")
        if len(errors) > 30:
            print(f"... and {len(errors) - 30} more errors")
        return False

    print("\n[PASS] JSON Schema validation succeeded.")

    memories = result.get("memories", [])
    quote_errors = []

    for i, memory in enumerate(memories):
        for j, evidence in enumerate(memory.get("evidence", [])):
            quote = evidence.get("quote", "")
            if quote not in source:
                quote_errors.append(
                    f"memories[{i}].evidence[{j}]: {quote!r}"
                )

    if quote_errors:
        print("[WARN] Evidence quotes not found verbatim in source:")
        for error in quote_errors:
            print("-", error)
    else:
        print("[PASS] Evidence quotes occur verbatim in the source.")

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--source", default=SOURCE_TEXT)
    args = parser.parse_args()

    try:
        original = load_schema(Path(args.schema))
    except Exception as exc:
        print(f"[ERROR] Could not load original schema: {exc}")
        return 2

    tests = [
        ("01_minimal", minimal_schema()),
        (
            "02_simplified_memory_fields",
            simplified_memory_schema(original),
        ),
        (
            "03_time_target_fields",
            time_target_schema(original),
        ),
        ("04_original_full_schema", original),
    ]

    results = []

    for name, schema in tests:
        passed = run_test(
            name=name,
            schema=schema,
            url=args.url,
            source=args.source,
            max_tokens=args.max_tokens,
        )
        results.append((name, passed))

    print(f"\n{'=' * 65}")
    print("FINAL SUMMARY")
    print("=" * 65)

    for name, passed in results:
        print(f"{name}: {'PASS' if passed else 'FAIL'}")

    print(
        "\n주의: 이 테스트는 복잡한 스키마 전체를 자동으로 "
        "한 키워드씩 분해하지는 않습니다. "
        "실패한 단계에서 추가 분리 테스트가 필요할 수 있습니다."
    )

    return 0 if all(passed for _, passed in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())