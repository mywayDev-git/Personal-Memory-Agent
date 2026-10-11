
"""Client for OpenAI-compatible chat completion APIs."""

import json
import time
from typing import Any

import requests


def call_llm(
    session: requests.Session,
    endpoint: str,
    model: str | None,
    prompt: str,
    source_text: str,
    source_context: dict[str, Any],
    timeout: float,
    max_tokens: int,
    temperature: float,
    seed: int,
    top_p: float,
    output_schema: dict | None = None,
) -> tuple[str, dict[str, Any], float]:
    """Call an OpenAI-compatible /chat/completions endpoint.

    Returns:
        A tuple containing:
        - The generated text.
        - Response metadata.
        - Request latency in seconds.

    Raises:
        requests.RequestException: If the HTTP request fails.
        ValueError: If the API response is invalid or content is empty.
    """
    user_payload = (
        "다음은 기억 추출 대상 원문과 신뢰할 수 있는 메타데이터다.\n"
        "메타데이터를 원문에 없는 사실을 추론하는 근거로 사용하지 마라.\n"
        "reference_time은 상대 시간 표현의 해석에만 사용한다.\n"
        "reference_time이 null이면 상대 시간을 임의의 날짜나 시각으로 "
        "변환하지 마라.\n"
        "시간을 명확하게 정규화할 수 없으면 time.start와 time.end를 "
        "null로 출력하라.\n"
        "메타데이터는 출력 JSON에 포함하지 마라.\n\n"
        "[source_context]\n"
        f"{json.dumps(source_context, ensure_ascii=False, sort_keys=True)}\n\n"
        f"[source_text]\n{source_text}"
    )

    body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_payload},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
        "top_p": top_p,
        "stream": False,
    }

    if model:
        body["model"] = model

    if output_schema is not None:
        body["json_schema"] = output_schema

    started = time.perf_counter()

    response = session.post(
        endpoint,
        json=body,
        timeout=timeout,
    )

    latency = time.perf_counter() - started

    if not response.ok:
        try:
            error_body = response.json()
            error_detail = json.dumps(
                error_body,
                ensure_ascii=False,
            )
        except ValueError:
            error_detail = response.text

        raise requests.HTTPError(
            f"LLM API request failed: "
            f"status={response.status_code}, "
            f"response={error_detail[:2000]}",
            response=response,
        )



    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("LLM API returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("LLM API response must be a JSON object.")

    try:
        choice = payload["choices"][0]
        message = choice["message"]
        content = message.get("content")
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(
            f"Unexpected API response structure: {payload}"
        ) from exc

    if not isinstance(message, dict):
        raise ValueError("LLM API message must be an object.")

    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "LLM returned empty content. "
            f"finish_reason={choice.get('finish_reason')!r}, "
            f"message_keys={list(message.keys())}, "
            f"reasoning_content_present="
            f"{bool(message.get('reasoning_content'))}, "
            f"response_id={payload.get('id')!r}"
        )

    usage = payload.get("usage") or {}
    print("[DEBUG] usage:", payload.get("usage"))   
    metadata = {
        "http_status": response.status_code,
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "model": payload.get("model", model),
    }

    return content.strip(), metadata, latency
