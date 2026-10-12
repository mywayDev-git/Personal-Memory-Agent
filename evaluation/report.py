
#!/usr/bin/env python3
"""평가 결과 JSONL을 분석하여 Markdown 보고서를 생성한다."""

import argparse
import json
from collections import Counter
from pathlib import Path


def read_json(path: Path) -> dict:
    """JSON 파일을 읽는다."""
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"JSON 최상위 값은 객체여야 합니다: {path}")

    return data


def read_jsonl(path: Path) -> list[dict]:
    """JSONL 파일을 읽는다."""
    records = []

    with path.open("r", encoding="utf-8-sig") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSONL 파싱 실패: {path}, "
                    f"{line_number}번째 줄: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"JSONL 각 행은 객체여야 합니다: "
                    f"{path}, {line_number}번째 줄"
                )

            records.append(record)

    return records


def format_seconds(value) -> str:
    """초 단위 숫자를 보고서에 표시할 문자열로 변환한다."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "N/A"

    return f"{value:.2f}s"


def format_rate(value) -> str:
    """비율을 백분율로 변환한다."""
    if not isinstance(value, (int, float)):
        return "N/A"

    return f"{value * 100:.2f}%"


def markdown_cell(value) -> str:
    """Markdown 표에서 문제가 되는 문자를 정리한다."""
    if value is None:
        return "N/A"

    return str(value).replace("|", r"\|").replace("\n", " ")


def get_schema_valid(record: dict) -> bool:
    """
    최종 스키마 검증 결과를 가져온다.

    실제 평가 결과의 final_schema_valid를 우선 사용하고,
    구버전 결과의 schema_valid도 지원한다.
    """
    value = record.get(
        "final_schema_valid",
        record.get("schema_valid", False),
    )
    return value is True


def get_source_id(record: dict) -> str:
    """중첩된 source_context에서 source_id를 가져온다."""
    result = record.get("result")

    if isinstance(result, dict):
        source_context = result.get("source_context")

        if isinstance(source_context, dict):
            source_id = source_context.get("source_id")
            if source_id is not None:
                return str(source_id)

    return str(record.get("source_id", "N/A"))


def calculate_metrics(
    records: list[dict],
    metadata: dict,
    dataset_name: str,
) -> dict:
    """평가 결과 레코드에서 지표를 자동 계산한다."""
    total = len(records)

    valid_count = sum(
        record.get("valid") is True
        for record in records
    )

    schema_valid_count = sum(
        get_schema_valid(record)
        for record in records
    )

    evidence_valid_count = sum(
        record.get("evidence_valid") is True
        for record in records
    )

    latencies = [
        record["latency_seconds"]
        for record in records
        if (
            isinstance(record.get("latency_seconds"), (int, float))
            and not isinstance(record.get("latency_seconds"), bool)
            and record["latency_seconds"] >= 0
        )
    ]

    finish_reasons = Counter(
        str(record["finish_reason"])
        for record in records
        if record.get("finish_reason")
    )

    error_types = Counter(
        str(record.get("failure_stage") or record.get("error"))
        for record in records
        if record.get("failure_stage") or record.get("error")
    )

    models = Counter(
        str(record["model"])
        for record in records
        if record.get("model")
    )

    model_name = metadata.get("model")
    if not model_name:
        model_name = (
            models.most_common(1)[0][0]
            if models
            else "N/A"
        )

    return {
        "dataset": metadata.get("dataset", dataset_name),
        "model": model_name,
        "requested_samples": metadata.get("requested_samples", total),
        "total_count": total,
        "valid_count": valid_count,
        "invalid_count": total - valid_count,
        "valid_rate": valid_count / total if total else 0.0,
        "schema_valid_count": schema_valid_count,
        "schema_valid_rate": (
            schema_valid_count / total if total else 0.0
        ),
        "evidence_valid_count": evidence_valid_count,
        "evidence_valid_rate": (
            evidence_valid_count / total if total else 0.0
        ),
        "avg_latency_seconds": (
            sum(latencies) / len(latencies)
            if latencies
            else 0.0
        ),
        "finish_reasons": dict(finish_reasons),
        "error_types": dict(error_types),
    }


def build_report(metrics: dict, records: list[dict]) -> str:
    """계산된 지표와 개별 결과로 Markdown 보고서를 만든다."""
    lines = [
        "# Evaluation Report",
        "",
        "## 1. 실행 정보",
        "",
        f"- 데이터셋: `{markdown_cell(metrics['dataset'])}`",
        f"- 모델: `{markdown_cell(metrics['model'])}`",
        f"- 요청 샘플 수: {metrics['requested_samples']}",
        f"- 실제 결과 수: {metrics['total_count']}",
        "",
        "## 2. 전체 평가 결과",
        "",
        "| 지표 | 결과 |",
        "|---|---:|",
        f"| 최종 유효률 | {format_rate(metrics['valid_rate'])} |",
        (
            f"| 최종 PASS | {metrics['valid_count']} "
            f"/ {metrics['total_count']} |"
        ),
        f"| 최종 FAIL | {metrics['invalid_count']} |",
        (
            f"| 최종 스키마 유효률 | "
            f"{format_rate(metrics['schema_valid_rate'])} |"
        ),
        (
            f"| 최종 스키마 유효 개수 | "
            f"{metrics['schema_valid_count']} |"
        ),
        (
            f"| Evidence 유효률 | "
            f"{format_rate(metrics['evidence_valid_rate'])} |"
        ),
        (
            f"| Evidence 유효 개수 | "
            f"{metrics['evidence_valid_count']} |"
        ),
        (
            f"| 평균 지연 시간 | "
            f"{format_seconds(metrics['avg_latency_seconds'])} |"
        ),
        "",
        "## 3. 종료 사유",
        "",
        "| 종료 사유 | 개수 |",
        "|---|---:|",
    ]

    if metrics["finish_reasons"]:
        for reason, count in sorted(metrics["finish_reasons"].items()):
            lines.append(f"| {markdown_cell(reason)} | {count} |")
    else:
        lines.append("| 기록 없음 | 0 |")

    lines.extend([
        "",
        "## 4. 오류 유형",
        "",
        "| 오류 유형 | 개수 |",
        "|---|---:|",
    ])

    if metrics["error_types"]:
        for error_type, count in sorted(metrics["error_types"].items()):
            lines.append(
                f"| {markdown_cell(error_type)} | {count} |"
            )
    else:
        lines.append("| 기록된 오류 없음 | 0 |")

    lines.extend([
        "",
        "## 5. 개별 테스트 결과",
        "",
        "| 테스트 ID | 분류 | 최종 결과 | 스키마 | Evidence "
        "| 지연 시간 | 메모리 수 | Source ID | 오류 단계 |",
        "|---|---|---|---|---|---:|---:|---|---|",
    ])

    for record in records:
        case_id = record.get(
            "case_id",
            record.get("index", "-"),
        )

        category = record.get("category", "N/A")

        status = (
            "PASS"
            if record.get("valid") is True
            else "FAIL"
        )

        schema_status = (
            "PASS"
            if get_schema_valid(record)
            else "FAIL"
        )

        evidence_status = (
            "PASS"
            if record.get("evidence_valid") is True
            else "FAIL"
        )

        latency = format_seconds(record.get("latency_seconds"))
        memory_count = record.get("memory_count", "N/A")
        source_id = get_source_id(record)
        failure_stage = (
            record.get("failure_stage")
            or record.get("error")
            or "-"
        )

        lines.append(
            f"| {markdown_cell(case_id)} "
            f"| {markdown_cell(category)} "
            f"| {status} "
            f"| {schema_status} "
            f"| {evidence_status} "
            f"| {latency} "
            f"| {memory_count} "
            f"| {markdown_cell(source_id)} "
            f"| {markdown_cell(failure_stage)} |"
        )

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="평가 결과 JSONL을 Markdown 보고서로 변환합니다."
    )

    parser.add_argument(
        "--results",
        type=Path,
        default=Path("results/eval_results.jsonl"),
        help="평가 결과 JSONL 경로",
    )

    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("results/evaluation_metrics.json"),
        help="선택적 메타데이터 JSON 경로",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/evaluation_report.md"),
        help="생성할 Markdown 보고서 경로",
    )

    parser.add_argument(
        "--dataset-name",
        default="datasets/test.jsonl",
        help="메타데이터 파일이 없을 때 보고서에 표시할 데이터셋 이름",
    )

    args = parser.parse_args()

    try:
        # 평가 결과는 필수다.
        records = read_jsonl(args.results)

        # 메타데이터 파일은 선택 사항이다.
        # 파일이 없으면 결과 JSONL에서 지표를 계산한다.
        if args.metrics.is_file():
            metadata = read_json(args.metrics)
        else:
            metadata = {}

        metrics = calculate_metrics(
            records=records,
            metadata=metadata,
            dataset_name=args.dataset_name,
        )

        report = build_report(metrics, records)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")

        print(f"보고서 생성 완료: {args.output}")
        print(f"전체 테스트: {metrics['total_count']}")
        print(
            f"최종 PASS: {metrics['valid_count']} "
            f"({format_rate(metrics['valid_rate'])})"
        )
        print(
            f"스키마 PASS: {metrics['schema_valid_count']} "
            f"({format_rate(metrics['schema_valid_rate'])})"
        )
        print(
            f"Evidence PASS: {metrics['evidence_valid_count']} "
            f"({format_rate(metrics['evidence_valid_rate'])})"
        )
        print(
            "평균 지연 시간: "
            f"{format_seconds(metrics['avg_latency_seconds'])}"
        )

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"보고서 생성 실패: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
