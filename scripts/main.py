
"""Command-line entry point for the Personal Memory Agent."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

from config.settings import paths, settings
from .exceptions import (
    ExtractionError,
    MemoryAgentError,
    SchemaValidationError,
)
from .extractor import extract_memories
from .postprocess import build_final_result, make_source_context
from .validator import (
    load_schema,
    validate_extraction,
    validate_final_result,
)


def read_prompt(path: Path) -> str:
    """Read the extraction prompt."""
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise MemoryAgentError(
            f"Could not read prompt file: {path}"
        ) from exc

    if not prompt:
        raise MemoryAgentError(f"Prompt file is empty: {path}")

    return prompt


def read_json_input(path: Path) -> dict[str, Any]:
    """Read one JSON object from a file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MemoryAgentError(
            f"Could not read input file: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise MemoryAgentError(
            f"Input file is not valid JSON: {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise MemoryAgentError("Input JSON must be an object.")

    return data


def extract_source_text(data: dict[str, Any]) -> str:
    """Get source text from supported input formats."""
    input_data = data.get("input")

    if isinstance(input_data, dict):
        text = input_data.get("text")
        if isinstance(text, str):
            return text

    for key in ("text", "content", "source_text", "document"):
        value = data.get(key)
        if isinstance(value, str):
            return value

    raise MemoryAgentError(
        "No source text found. Provide input.text or a top-level "
        "text, content, source_text, or document field."
    )


def process_text(
    source_text: str,
    source_context: dict[str, Any],
    *,
    prompt: str,
    output_schema: dict[str, Any],
    final_schema: dict[str, Any],
    session: requests.Session,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract and validate memories from a single source."""
    if not isinstance(source_text, str) or not source_text.strip():
        raise MemoryAgentError("Source text must not be empty.")

    extraction, llm_metadata, latency = extract_memories(
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

    output_errors = validate_extraction(extraction, output_schema)
    if output_errors:
        raise SchemaValidationError(
            "LLM output failed schema validation:\n"
            + "\n".join(output_errors)
        )

    final_result = build_final_result(extraction, source_context)

    report = validate_final_result(
        result=final_result,
        final_schema=final_schema,
        source_text=source_text,
    )

    if not report["valid"]:
        raise SchemaValidationError(
            "Final result validation failed:\n"
            + json.dumps(report, ensure_ascii=False, indent=2)
        )

    metadata = {
        **llm_metadata,
        "latency_seconds": round(latency, 4),
        "memory_count": len(final_result["memories"]),
        "output_schema_valid": True,
        "final_schema_valid": report["schema_valid"],
        "evidence_valid": report["evidence_valid"],
    }

    return final_result, metadata


def build_parser() -> argparse.ArgumentParser:
    """Configure command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract structured memories from personal records."
    )

    parser.add_argument(
        "--input",
        type=Path,
        help="Path to a JSON file containing source text and metadata.",
    )
    parser.add_argument(
        "--text",
        help="Source text to process directly.",
    )
    parser.add_argument(
        "--source-id",
        default="source-001",
        help="Identifier for the source record.",
    )
    parser.add_argument(
        "--reference-time",
        default=None,
        help="Reference date/time, if known.",
    )
    parser.add_argument(
        "--language",
        default=settings.language,
        help="Source language.",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=paths.prompt,
    )
    parser.add_argument(
        "--output-schema",
        type=Path,
        default=paths.output_schema,
    )
    parser.add_argument(
        "--final-schema",
        type=Path,
        default=paths.final_schema,
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output JSON file. Defaults to stdout.",
    )

    return parser


def main() -> int:
    """Run the single-record extraction pipeline."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.input is not None and args.text is not None:
            parser.error("Use either --input or --text, not both.")

        if args.input is None and args.text is None:
            parser.error("Provide --input or --text.")

        if args.input is not None:
            input_data = read_json_input(args.input)
            source_text = extract_source_text(input_data)

            nested_input = input_data.get("input")
            input_metadata = (
                nested_input if isinstance(nested_input, dict)
                else input_data
            )

            source_id = input_metadata.get(
                "source_id",
                input_data.get("case_id", args.source_id),
            )
            reference_time = input_metadata.get(
                "reference_time",
                args.reference_time,
            )
            language = input_metadata.get("language", args.language)
        else:
            source_text = args.text
            source_id = args.source_id
            reference_time = args.reference_time
            language = args.language

        source_context = make_source_context(
            source_id=str(source_id),
            reference_time=reference_time,
            language=language,
        )

        prompt = read_prompt(args.prompt)
        output_schema = load_schema(args.output_schema)
        final_schema = load_schema(args.final_schema)

        with requests.Session() as session:
            result, metadata = process_text(
                source_text=source_text,
                source_context=source_context,
                prompt=prompt,
                output_schema=output_schema,
                final_schema=final_schema,
                session=session,
            )

        output = {
            "result": result,
            "metadata": metadata,
        }
        serialized = json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        )

        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized + "\n", encoding="utf-8")
            print(f"Saved result to {args.output}", file=sys.stderr)
        else:
            print(serialized)

        return 0

    except (
        MemoryAgentError,
        ExtractionError,
        SchemaValidationError,
        requests.RequestException,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
