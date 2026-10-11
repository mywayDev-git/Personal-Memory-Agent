import json
import requests

URL = "http://127.0.0.1:8081/v1/chat/completions"

schema = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quote": {"type": "string"}
                            },
                            "required": ["quote"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["content", "evidence"],
                "additionalProperties": False
            }
        }
    },
    "required": ["memories"],
    "additionalProperties": False
}

payload = {
    "messages": [
        {
            "role": "system",
            "content": (
                "Return only JSON matching the supplied schema. "
                "The root must contain a memories array. "
                "Each memory must contain content and evidence. "
                "Each evidence item must contain quote."
            )
        },
        {
            "role": "user",
            "content": "Extract a memory from this text: "
                       "이번 학기에 데이터베이스를 공부한다."
        }
    ],
    "response_format": {
        "type": "json_schema",
        "schema": schema
    },
    "temperature": 0,
    "max_tokens": 512,
    "stream": False
}

print("=== Schema ===")
print(json.dumps(schema, ensure_ascii=False, indent=2))

response = requests.post(URL, json=payload, timeout=180)

print("\nHTTP status:", response.status_code)
response.raise_for_status()

body = response.json()
print("Finish reason:", body["choices"][0].get("finish_reason"))

content = body["choices"][0]["message"]["content"]
print("\n=== Generated Content ===")
print(content)

try:
    result = json.loads(content)
except json.JSONDecodeError as exc:
    print("\n[FAIL] Invalid JSON:", exc)
    raise SystemExit(1)

from jsonschema import Draft202012Validator

errors = list(Draft202012Validator(schema).iter_errors(result))

if errors:
    print("\n[FAIL] Schema validation failed")
    for error in errors:
        print("-", error.message)
    raise SystemExit(1)

print("\n[PASS] JSON Schema validation succeeded")