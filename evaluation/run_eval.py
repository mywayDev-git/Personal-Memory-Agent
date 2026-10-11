
#!/usr/bin/env python3

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 프로젝트 루트를 Python 모듈 검색 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from config.settings import settings
from scripts.memory_agent.extractor import extract_memories
from scripts.memory_agent.postprocess import build_final_result
from scripts.memory_agent.validator import (
    validate_extraction,
    validate_final_result,
)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """JSONL 파일을 읽어 레코드 목록으로 반환한다."""
    records: list[dict[str, Any]] = []

    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSONL 파싱 오류: {path}:{line_number}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"각 JSONL 레코드는 객체여야 한다: "
                    f"{path}:{line_number}"
                )

            records.append(record)

    return records


def read_json(path: str | Path) -> dict[str, Any]:
    """JSON 스키마 파일을 읽는다."""
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"스키마는 JSON 객체여야 한다: {path}")

    return data


def get_source_text(record: dict[str, Any]) -> str:
    """입력 데이터에서 원문을 가져온다."""
    input_data = record.get("input", {})

    if isinstance(input_data, dict):
        text = input_data.get("text", "")
    else:
        text = ""

    if not isinstance(text, str):
        raise ValueError(
            f"원문 input.text는 문자열이어야 한다: "
            f"{record.get('case_id', record.get('id', 'unknown'))}"
        )

    if not text.strip():
        raise ValueError(
            f"원문이 비어 있다: "
            f"{record.get('case_id', record.get('id', 'unknown'))}"
        )

    return text


def get_source_context(
    record: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """입력 데이터에서 출처 메타데이터를 가져온다."""
    input_data = record.get("input", {})

    if not isinstance(input_data, dict):
        input_data = {}

    source_id = (
        input_data.get("source_id")
        or record.get("source_id")
        or record.get("case_id")
        or record.get("id")
        or f"eval-{index:04d}"
    )

    return {
        "source_id": str(source_id),
        "reference_time": input_data.get("reference_time"),
        "language": input_data.get("language", "ko"),
    }


def load_prompt(path: str | Path) -> str:
    """프롬프트 파일을 읽는다."""
    return Path(path).read_text(encoding="utf-8")


def extract_token_usage(metadata: dict) -> dict:
    usage = metadata.get("usage")

    # llm_client.py가 토큰 정보를 개별 필드로 반환하는 경우도 지원
    if not isinstance(usage, dict):
        usage = metadata

    prompt_tokens = usage.get(
        "prompt_tokens",
        usage.get("input_tokens"),
    )
    completion_tokens = usage.get(
        "completion_tokens",
        usage.get("output_tokens"),
    )
    total_tokens = usage.get("total_tokens")

    # 전체 토큰 수가 없을 때만 입력·출력 토큰 수로 계산
    if (
        total_tokens is None
        and isinstance(prompt_tokens, int)
        and isinstance(completion_tokens, int)
    ):
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }



def evaluate_one(
    record: dict[str, Any],
    index: int,
    prompt: str,
    raw_schema: dict[str, Any],
    final_schema: dict[str, Any],
) -> dict[str, Any]:
    """데이터 한 건을 추출하고 검증한 뒤 평가 결과를 반환한다."""
    started_clock = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()

    case_id = str(
        record.get("case_id")
        or record.get("id")
        or f"EVAL-{index:04d}"
    )

    result_record: dict[str, Any] = {
        # 실행 및 데이터 식별 정보
        "case_id": case_id,
        "category": record.get("category"),
        "severity": record.get("severity"),
        "started_at": started_at,

        # 입력 및 출력 길이
        "input_chars": None,
        "prompt_chars": len(prompt),
        "output_chars": None,

        # 모델 실행 정보
        "model": None,
        "latency_seconds": None,
        "elapsed_seconds": None,
        "finish_reason": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,

        # 검증 결과
        "valid": False,
        "raw_schema_valid": False,
        "final_schema_valid": False,
        "evidence_valid": False,
        "raw_schema_errors": [],
        "final_schema_errors": [],
        "evidence_errors": [],

        # 추출 결과
        "memory_count": 0,
        "memory_type_counts": {},
        "result": None,

        # 오류 정보
        "failure_stage": "input",
        "error": None,
        "status": "fail",
    }

    try:
        source_text = get_source_text(record)
        source_context = get_source_context(record, index)

        result_record["input_chars"] = len(source_text)

        # 1. LLM 호출 및 기억 추출
        result_record["failure_stage"] = "llm_request"

        with requests.Session() as session:
            llm_output, metadata, latency = extract_memories(
                session=session,
                endpoint=settings.endpoint,
                model=settings.model,
                prompt=prompt,
                source_text=source_text,
                source_context=source_context,
                timeout=settings.timeout,
                max_tokens=settings.max_tokens,
                temperature=settings.temperature,
                seed=settings.seed,
                top_p=settings.top_p,
            )

        if not isinstance(metadata, dict):
            metadata = {}

        result_record["latency_seconds"] = latency
        result_record["model"] = metadata.get("model")
        result_record["finish_reason"] = metadata.get("finish_reason")

        # 원본 JSON을 기준으로 출력 길이를 기록한다.
        result_record["output_chars"] = len(
            json.dumps(llm_output, ensure_ascii=False)
        )

        # 2. 토큰 사용량 기록
        result_record.update(extract_token_usage(metadata))

        # 3. LLM 원본 출력 스키마 검증
        result_record["failure_stage"] = "raw_schema_validation"

        raw_errors = validate_extraction(
            llm_output,
            raw_schema,
        )

        if not isinstance(raw_errors, list):
            raw_errors = list(raw_errors)

        raw_schema_valid = len(raw_errors) == 0

        # 4. 최종 결과 생성
        result_record["failure_stage"] = "postprocessing"

        final_result = build_final_result(
            llm_output,
            source_context,
        )

        # 5. 최종 스키마 및 evidence 검증
        result_record["failure_stage"] = "final_validation"

        final_validation = validate_final_result(
            final_result,
            final_schema,
            source_text,
        )

        final_schema_valid = bool(
            final_validation["schema_valid"]
        )
        evidence_valid = bool(
            final_validation["evidence_valid"]
        )

        finish_reason = metadata.get("finish_reason")

        valid = (
            raw_schema_valid
            and final_schema_valid
            and evidence_valid
            and finish_reason != "length"
        )

        final_schema_errors = final_validation.get(
            "schema_errors",
            [],
        )
        evidence_errors = final_validation.get(
            "evidence_errors",
            [],
        )

        memories = final_result.get("memories", [])

        # 기억 유형별 개수 집계
        memory_type_counts: dict[str, int] = {}

        for memory in memories:
            if not isinstance(memory, dict):
                memory_type = "unknown"
            else:
                memory_type = memory.get(
                    "memory_type",
                    "unknown",
                )

            memory_type_counts[memory_type] = (
                memory_type_counts.get(memory_type, 0) + 1
            )

        result_record.update({
            "valid": valid,
            "raw_schema_valid": raw_schema_valid,
            "final_schema_valid": final_schema_valid,
            "evidence_valid": evidence_valid,
            "raw_schema_errors": raw_errors,
            "final_schema_errors": final_schema_errors,
            "evidence_errors": evidence_errors,
            "memory_count": len(memories),
            "memory_type_counts": memory_type_counts,
            "result": final_result,
            "failure_stage": None,
            "status": "pass" if valid else "fail",
        })

        # 검증 실패도 단계별로 추적할 수 있도록 구분한다.
        if not raw_schema_valid:
            result_record["failure_stage"] = (
                "raw_schema_validation"
            )
        elif not final_schema_valid:
            result_record["failure_stage"] = (
                "final_schema_validation"
            )
        elif not evidence_valid:
            result_record["failure_stage"] = (
                "evidence_validation"
            )
        elif finish_reason == "length":
            result_record["failure_stage"] = (
                "generation_truncated"
            )

    except requests.HTTPError as exc:
        response = exc.response

        if response is not None:
            try:
                error_body = json.dumps(
                    response.json(),
                    ensure_ascii=False,
                )
            except ValueError:
                error_body = response.text

            result_record["error"] = (
                f"HTTPError: status={response.status_code}, "
                f"response={error_body[:2000]}"
            )
        else:
            result_record["error"] = (
                f"{type(exc).__name__}: {exc}"
            )

        result_record["status"] = "error"

    except Exception as exc:
        result_record["error"] = (
            f"{type(exc).__name__}: {exc}"
        )
        result_record["status"] = "error"

    finally:
        result_record["elapsed_seconds"] = round(
            time.perf_counter() - started_clock,
            4,
        )

    return result_record


def write_jsonl(
    path: str | Path,
    records: list[dict[str, Any]],
) -> None:
    """평가 결과를 JSONL 파일로 저장한다."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def print_summary(records: list[dict[str, Any]]) -> None:
    """평가 결과의 핵심 통계를 출력한다."""
    total = len(records)

    valid_count = sum(
        bool(record.get("valid"))
        for record in records
    )

    raw_schema_valid_count = sum(
        bool(record.get("raw_schema_valid"))
        for record in records
    )

    final_schema_valid_count = sum(
        bool(record.get("final_schema_valid"))
        for record in records
    )

    evidence_valid_count = sum(
        bool(record.get("evidence_valid"))
        for record in records
    )

    error_count = sum(
        record.get("status") == "error"
        for record in records
    )

    latencies = [
        record["latency_seconds"]
        for record in records
        if isinstance(
            record.get("latency_seconds"),
            (int, float),
        )
    ]

    prompt_tokens = [
        record["prompt_tokens"]
        for record in records
        if isinstance(
            record.get("prompt_tokens"),
            (int, float),
        )
    ]

    completion_tokens = [
        record["completion_tokens"]
        for record in records
        if isinstance(
            record.get("completion_tokens"),
            (int, float),
        )
    ]

    print("\n========== Evaluation Summary ==========")
    print(f"Total cases:         {total}")
    print(f"Valid:               {valid_count}/{total}")
    print(
        f"Raw schema valid:    "
        f"{raw_schema_valid_count}/{total}"
    )
    print(
        f"Final schema valid:  "
        f"{final_schema_valid_count}/{total}"
    )
    print(
        f"Evidence valid:      "
        f"{evidence_valid_count}/{total}"
    )
    print(f"Errors:              {error_count}/{total}")

    if total:
        print(
            f"Valid rate:           "
            f"{valid_count / total * 100:.2f}%"
        )

    if latencies:
        print(
            f"Average latency:      "
            f"{sum(latencies) / len(latencies):.3f}s"
        )

    if prompt_tokens:
        print(f"Prompt tokens:        {sum(prompt_tokens)}")

    if completion_tokens:
        print(
            f"Completion tokens:    "
            f"{sum(completion_tokens)}"
        )

    if not prompt_tokens and not completion_tokens:
        print("Token usage:          Not provided by model server")

    print("========================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Personal Memory Agent evaluation runner"
    )

    parser.add_argument(
        "--dataset",
        default="datasets/test_v1.jsonl",
        help="입력 데이터셋 JSONL 경로",
    )
    parser.add_argument(
        "--prompt",
        default="prompts/extraction_v4.txt",
        help="추출 프롬프트 경로",
    )
    parser.add_argument(
        "--raw-schema",
        default="schema/memory_extraction_output_v4.schema.json",
        help="LLM 원본 출력 스키마 경로",
    )
    parser.add_argument(
        "--final-schema",
        default="schema/memory_extraction_v4.schema.json",
        help="최종 결과 스키마 경로",
    )
    parser.add_argument(
        "--output",
        default="results/eval_results.jsonl",
        help="결과 JSONL 저장 경로",
    )

    args = parser.parse_args()

    # 실행 위치와 관계없이 프로젝트 루트를 기준으로 경로 처리
    def resolve_path(path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return PROJECT_ROOT / candidate

    dataset_path = resolve_path(args.dataset)
    prompt_path = resolve_path(args.prompt)
    raw_schema_path = resolve_path(args.raw_schema)
    final_schema_path = resolve_path(args.final_schema)
    output_path = resolve_path(args.output)

    dataset = read_jsonl(dataset_path)
    prompt = load_prompt(prompt_path)
    raw_schema = read_json(raw_schema_path)
    final_schema = read_json(final_schema_path)

    print(f"Dataset: {dataset_path}")
    print(f"Cases:   {len(dataset)}")
    print(f"Prompt:  {prompt_path}")
    print(f"Output:  {output_path}")

    results: list[dict[str, Any]] = []

    for index, record in enumerate(dataset, start=1):
        case_id = (
            record.get("case_id")
            or record.get("id")
            or f"EVAL-{index:04d}"
        )

        print(f"\n[{index}/{len(dataset)}] {case_id}")

        result = evaluate_one(
            record=record,
            index=index,
            prompt=prompt,
            raw_schema=raw_schema,
            final_schema=final_schema,
        )

        results.append(result)

        print(
            f'  Status={result["status"]} | '
            f'Valid={result["valid"]} | '
            f'Memories={result["memory_count"]} | '
            f'Latency={result["latency_seconds"]}s'
        )

        print(
            f'  Schema: raw={result["raw_schema_valid"]}, '
            f'final={result["final_schema_valid"]}, '
            f'evidence={result["evidence_valid"]}'
        )

        if result["failure_stage"]:
            print(
                f'  Failure stage: {result["failure_stage"]}'
            )

        if result["error"]:
            print(f'  Error: {result["error"]}')

        if result["raw_schema_errors"]:
            print(
                f'  Raw schema errors: '
                f'{result["raw_schema_errors"]}'
            )

        if result["final_schema_errors"]:
            print(
                f'  Final schema errors: '
                f'{result["final_schema_errors"]}'
            )

        if result["evidence_errors"]:
            print(
                f'  Evidence errors: '
                f'{result["evidence_errors"]}'
            )

        # 중간 결과를 저장해 중단 시에도 진행 상황을 보존한다.
        write_jsonl(output_path, results)

    write_jsonl(output_path, results)
    print_summary(results)

    print(f"Saved {len(results)} results to {output_path}")


if __name__ == "__main__":
    main()
