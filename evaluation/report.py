from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"잘못된 JSONL: {path}:{line_number}: {exc}"
                ) from exc

    return records


def format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "N/A"
    return f"{value:.2%}"


def format_seconds(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "N/A"
    return f"{value:.2f}s"


def build_report(
    metrics: dict[str, Any],
    records: list[dict[str, Any]],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Personal Memory Agent 평가 보고서",
        "",
        f"- 보고서 생성: {generated_at}",
        f"- 데이터셋: {metrics.get('dataset', 'N/A')}",
        f"- 모델: {metrics.get('model', 'N/A')}",
        f"- 평가 대상: {metrics.get('requested_samples', len(records))}",
        f"- 실제 평가: {len(records)}",
        "",
        "## 1. 주요 평가 지표",
        "",
        "| 지표 | 결과 |",
        "|---|---:|",
        f"| 최종 통과율 | {format_percent(metrics.get('valid_rate'))} |",
        f"| 스키마 통과율 | {format_percent(metrics.get('schema_valid_rate'))} |",
        f"| 근거 검사 통과율 | {format_percent(metrics.get('evidence_valid_rate'))} |",
        f"| 평균 처리 시간 | {format_seconds(metrics.get('avg_latency_seconds'))} |",
        f"| 통과 건수 | {metrics.get('valid_count', 0)} |",
        f"| 실패 건수 | {metrics.get('invalid_count', 0)} |",
        "",
        "## 2. 종료 사유",
        "",
    ]

    finish_reasons = metrics.get("finish_reasons", {})
    if finish_reasons:
        lines.extend(
            f"- `{reason}`: {count}건"
            for reason, count in sorted(finish_reasons.items())
        )
    else:
        lines.append("- 기록된 종료 사유 없음")

    lines.extend(["", "## 3. 오류 유형", ""])

    error_types = metrics.get("error_types", {})
    if error_types:
        lines.extend(
            f"- {error}: {count}건"
            for error, count in sorted(
                error_types.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )
    else:
        lines.append("- 기록된 실행 오류 없음")

    lines.extend([
        "",
        "## 4. 개별 평가 결과",
        "",
        "| 번호 | Source ID | 결과 | 스키마 | 근거 | 처리 시간 | 오류 |",
        "|---:|---|---|---|---|---:|---|",
    ])

    for record in records:
        status = "PASS" if record.get("valid") is True else "FAIL"
        schema_status = "PASS" if record.get("schema_valid") is True else "FAIL"
        evidence_status = "PASS" if record.get("evidence_valid") is True else "FAIL"
        latency = format_seconds(record.get("latency_seconds"))

        source_id = str(record.get("source_id", "N/A"))
        error = str(record.get("error") or "-")

        # Markdown 표의 구분자와 줄바꿈을 방지한다.
        source_id = source_id.replace("|", "\\|").replace("\n", " ")
        error = error.replace("|", "\\|").replace("\n", " ")

        lines.append(
            f"| {record.get('index', '-')} "
            f"| {source_id} "
            f"| {status} "
            f"| {schema_status} "
            f"| {evidence_status} "
            f"| {latency} "
            f"| {error} |"
        )

    lines.extend([
        "",
        "## 5. 해석 시 유의사항",
        "",
        "- 스키마 통과율은 출력 구조와 타입이 정의된 규칙을 만족하는지 나타낸다.",
        "- 근거 검사 통과율은 근거 문구가 원문에 포함되는지 검사한 결과다.",
        "- 근거 문구가 원문에 존재하더라도 의미적으로 주장을 뒷받침하는지는 별도 평가가 필요하다.",
        "- 최종 통과율만으로 기억 추출의 의미적 정확도 전체를 판단할 수는 없다.",
        "",
    ])

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="평가 결과를 Markdown 보고서로 변환"
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=Path("results/evaluation_v4_metrics.json"),
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("results/evaluation_v4.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/evaluation_report.md"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        metrics = read_json(args.metrics)
        records = read_jsonl(args.results)
        report = build_report(metrics, records)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")

        print(report)
        print(f"\n보고서 저장 완료: {args.output}")
        return 0

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"보고서 생성 실패: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())