#!/usr/bin/env python3
"""평가 결과 JSONL을 분석하여 Markdown 보고서를 생성한다."""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.metrics import calculate_metrics as base_metrics


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
                raise ValueError(f"JSONL 파싱 실패: {path}, {line_number}번째 줄: {exc}") from exc

            if not isinstance(record, dict):
                raise ValueError(f"JSONL 각 행은 객체여야 합니다: {path}, {line_number}번째 줄")

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
    base = base_metrics(records)
    model_names = sorted({str(r["model"]) for r in records if r.get("model")})
    datasets = sorted({str(r["dataset"]) for r in records if r.get("dataset")})
    return {
        **base,
        "total_count": base["total"],
        "requested_samples": base["total"],
        "model": ", ".join(model_names) or "N/A",
        "dataset": ", ".join(datasets) or dataset_name,
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
        f"| 구조·근거 검사 통과율 (의미 정확도 아님) | {format_rate(metrics['valid_rate'])} |",
        (f"| 구조·근거 PASS | {metrics['valid_count']} / {metrics['total_count']} |"),
        f"| 최종 FAIL | {metrics['invalid_count']} |",
        (f"| 최종 스키마 유효률 | {format_rate(metrics['schema_valid_rate'])} |"),
        (f"| 최종 스키마 유효 개수 | {metrics['schema_valid_count']} |"),
        (f"| Evidence 유효률 | {format_rate(metrics['evidence_valid_rate'])} |"),
        (f"| Evidence 유효 개수 | {metrics['evidence_valid_count']} |"),
        (f"| 평균 지연 시간 | {format_seconds(metrics['avg_latency_seconds'])} |"),
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

    lines.extend(
        [
            "",
            "## 4. 오류 유형",
            "",
            "| 오류 유형 | 개수 |",
            "|---|---:|",
        ]
    )

    if metrics["error_types"]:
        for error_type, count in sorted(metrics["error_types"].items()):
            lines.append(f"| {markdown_cell(error_type)} | {count} |")
    else:
        lines.append("| 기록된 오류 없음 | 0 |")

    lines.extend(
        [
            "",
            "## 5. 개별 테스트 결과",
            "",
            "| 테스트 ID | 분류 | 최종 결과 | 스키마 | Evidence "
            "| 지연 시간 | 메모리 수 | Source ID | 오류 단계 |",
            "|---|---|---|---|---|---:|---:|---|---|",
        ]
    )

    for record in records:
        case_id = record.get(
            "case_id",
            record.get("index", "-"),
        )

        category = record.get("category", "N/A")

        status = "PASS" if record.get("valid") is True else "FAIL"

        schema_status = "PASS" if get_schema_valid(record) else "FAIL"

        evidence_status = "PASS" if record.get("evidence_valid") is True else "FAIL"

        latency = format_seconds(record.get("latency_seconds"))
        memory_count = record.get("memory_count", "N/A")
        source_id = get_source_id(record)
        failure_stage = record.get("failure_stage") or record.get("error") or "-"

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
    parser = argparse.ArgumentParser(description="평가 결과 JSONL을 Markdown 보고서로 변환합니다.")

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
        help="재계산한 지표 JSON 출력 경로",
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

        metadata = {}

        metrics = calculate_metrics(
            records=records,
            metadata=metadata,
            dataset_name=args.dataset_name,
        )

        report = build_report(metrics, records)

        args.metrics.parent.mkdir(parents=True, exist_ok=True)
        args.metrics.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")

        print(f"보고서 생성 완료: {args.output}")
        print(f"전체 테스트: {metrics['total_count']}")
        print(f"최종 PASS: {metrics['valid_count']} ({format_rate(metrics['valid_rate'])})")
        print(
            f"스키마 PASS: {metrics['schema_valid_count']} "
            f"({format_rate(metrics['schema_valid_rate'])})"
        )
        print(
            f"Evidence PASS: {metrics['evidence_valid_count']} "
            f"({format_rate(metrics['evidence_valid_rate'])})"
        )
        print(f"평균 지연 시간: {format_seconds(metrics['avg_latency_seconds'])}")

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"보고서 생성 실패: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
