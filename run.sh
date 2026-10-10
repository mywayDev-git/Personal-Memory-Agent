#!/usr/bin/env bash
set -euo pipefail

# Run from the directory containing this script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Adjust these paths if your project structure differs

DATASET="$SCRIPT_DIR/datasets/test_v1.jsonl"
TEMP_DATASET="$SCRIPT_DIR/datasets/split_001.jsonl"
PROMPT="$SCRIPT_DIR/prompts/extraction_v2.txt"
SCHEMA="$SCRIPT_DIR/schema/memory_extraction_v1.schema.json"
OUTPUT="$SCRIPT_DIR/results/split_001_v1.jsonl"
ENDPOINT="http://127.0.0.1:8081/v1/chat/completions"

# Check required files

for file in "$DATASET" "$PROMPT" "$SCHEMA"; do
if [[ ! -f "$file" ]]; then
echo "ERROR: File not found: $file" >&2
exit 1
fi
done

# Extract only SPLIT-001

python - "$DATASET" "$TEMP_DATASET" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])

matches = []

for line in source.read_text(encoding="utf-8-sig").splitlines():
    if not line.strip():
        continue

    item = json.loads(line)

    if item.get("case_id") == "SPLIT-001":
        matches.append(item)

if len(matches) != 1:
    raise SystemExit(
        f"ERROR: Expected exactly one SPLIT-001, found {len(matches)}"
    )

target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(
    json.dumps(matches[0], ensure_ascii=False) + "\n",
    encoding="utf-8"
)

print(f"Prepared dataset: {target}")
PY

mkdir -p "$SCRIPT_DIR/results"

# Run evaluation using prompt v1

python "$SCRIPT_DIR/scripts/run_evaluation.py" 
--dataset "$TEMP_DATASET" 
--schema "$SCHEMA" 
--prompt "$PROMPT" 
--endpoint "$ENDPOINT" 
--out "$OUTPUT"

echo
echo "Evaluation complete: $OUTPUT"
