"""PMA v4 entry point: python pma_extract.py --help."""
import argparse
import json
from pathlib import Path

from scripts.memory_agent.pipeline import PipelineOptions, extract_document, embed_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--text')
    source.add_argument('--input', type=Path, help='UTF-8 plain text file')
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--reference-time', help='RFC3339 timestamp, e.g. 2026-10-10T12:00:00+09:00')
    parser.add_argument('--context-tokens', type=int, default=32768, help='Must match server context capacity')
    parser.add_argument('--chunk-bytes', type=int, default=6000)
    parser.add_argument('--overlap-chars', type=int, default=160)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        text = args.input.read_text(encoding='utf-8-sig') if args.input else args.text
        result, metadata = extract_document(text, source_id=args.source_id,
            reference_time=args.reference_time,
            options=PipelineOptions(context_tokens=args.context_tokens,
                                    chunk_bytes=args.chunk_bytes, overlap_chars=args.overlap_chars))
        serialized = json.dumps({'result': result, 'metadata': metadata}, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized + '\n', encoding='utf-8')
        else:
            print(serialized)
    except Exception as exc:
        parser.exit(1, f'Extraction failed: {exc}\n')


if __name__ == '__main__':
    main()
