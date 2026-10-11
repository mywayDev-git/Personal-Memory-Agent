
import json
import requests
from jsonschema import Draft202012Validator, ValidationError


# ============================================================
# 1. 서버 설정
# ============================================================

URL = "http://127.0.0.1:8081/v1/chat/completions"

TEMPERATURE = 0
MAX_TOKENS = 2048
TIMEOUT = 120


# ============================================================
# 2. 테스트용 JSON Schema
# ============================================================

schema = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string"
        },
        "count": {
            "type": "integer"
        }
    },
    "required": [
        "answer",
        "count"
    ],
    "additionalProperties": False
}

# 스키마 자체가 올바른지 사전 검사
Draft202012Validator.check_schema(schema)


# ============================================================
# 3. 테스트 입력 및 프롬프트
# ============================================================

source = "이번 학기에 데이터베이스를 공부한다."

system_prompt = """
주어진 문장에서 명시적으로 확인할 수 있는 정보를 추출하라.
JSON 객체 하나만 출력하라.
원문에 없는 사실을 추측하지 마라.
"""

user_prompt = f"""Extract memories from this text:

{source}
"""


# ============================================================
# 4. 요청 본문 생성
# ============================================================

def make_payload(response_format):
    """
    response_format 설정에 따라 API 요청 본문을 생성한다.

    response_format:
        dict : 해당 출력 형식을 요청에 포함한다.
        None : response_format 항목을 요청에서 생략한다.
    """

    payload = {
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "stream": False,
        "json_schema": schema   # 추가하니 3가지 테스트 결과가 달라짐
    }

    # None이면 response_format을 전송하지 않는다.
    if response_format is not None:
        payload["response_format"] = response_format

    return payload


# ============================================================
# 5. 결과 분석
# ============================================================

def analyze_result(content):
    """
    모델 응답을 JSON으로 파싱하고
    지정된 스키마를 준수하는지 검사한다.
    """

    # 1단계: JSON 파싱
    try:
        data = json.loads(content)
        print("\n[PASS] JSON parsing succeeded.")

    except json.JSONDecodeError as error:
        print("\n[FAIL] JSON parsing failed.")
        print("Error:", error)
        return

    # 2단계: JSON Schema 검증
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(data),
        key=lambda error: list(map(str, error.absolute_path))
    )

    if not errors:
        print("[PASS] JSON Schema validation succeeded.")
    else:
        print("[FAIL] JSON Schema validation failed.")

        for error in errors:
            path = "$"

            for part in error.absolute_path:
                if isinstance(part, int):
                    path += f"[{part}]"
                else:
                    path += f".{part}"

            print(f"- {path}: {error.message}")

    # 3단계: 실제 결과 구조 출력
    if isinstance(data, dict):
        print("\nOutput keys:", list(data.keys()))
    else:
        print("\nOutput type:", type(data).__name__)


# ============================================================
# 6. 테스트 실행
# ============================================================

def run_test(name, response_format):
    """
    하나의 출력 모드를 테스트하고 결과를 출력한다.
    """

    print("\n" + "=" * 65)
    print(f"TEST: {name}")
    print("=" * 65)

    payload = make_payload(response_format)

    # 실제 요청 설정 확인
    print("\n=== REQUEST SETTINGS ===")

    if response_format is None:
        print("response_format: omitted")
    else:
        print("response_format:")
        print(json.dumps(
            response_format,
            ensure_ascii=False,
            indent=2
        ))

    print("temperature:", payload["temperature"])
    print("max_tokens:", payload["max_tokens"])

    # 실제 전송 직전 요청 본문 확인
    print("\n=== REQUEST BODY ===")
    print(json.dumps(
        payload,
        ensure_ascii=False,
        indent=2
    ))

    # API 요청
    try:
        response = requests.post(
            URL,
            json=payload,
            timeout=TIMEOUT
        )

        print("\nHTTP status:", response.status_code)

        response.raise_for_status()

        body = response.json()

    except requests.RequestException as error:
        print("\n[ERROR] API request failed.")
        print(error)
        return

    except ValueError as error:
        print("\n[ERROR] Server response is not valid JSON.")
        print(error)
        return

    # API 응답 구조 확인
    choices = body.get("choices", [])

    if not choices:
        print("[ERROR] No choices in API response.")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return

    message = choices[0].get("message", {})
    content = message.get("content")

    print("Finish reason:", choices[0].get("finish_reason"))
    print("Usage:", body.get("usage"))

    if not isinstance(content, str):
        print("\n[ERROR] Message content is not a string.")
        print(json.dumps(message, ensure_ascii=False, indent=2))
        return

    # 원본 생성 결과 출력
    print("\n=== GENERATED CONTENT ===")
    print(content)

    # JSON 파싱 및 스키마 검증
    analyze_result(content)


# ============================================================
# 7. 세 가지 모드 비교
# ============================================================

def main():

    tests = [
        (
            "A_schema_enabled",
            {
                "type": "json_schema",
                "schema": schema
            }
        ),
        (
            "B_json_mode_only",
            {
                "type": "json_object"
            }
        ),
        (
            "C_no_response_format",
            None
        )
    ]

    for name, response_format in tests:
        run_test(name, response_format)


if __name__ == "__main__":
    main()