# Personal Memory Agent — LLM Evaluation v1

## Contents
- `schema/memory_extraction_v1.schema.json`: common JSON Schema
- `datasets/development_v1.jsonl`: 18-case prompt iteration subset
- `datasets/test_v1.jsonl`: 120 synthetic test cases, 20 per category
- `prompts/extraction_v1.txt`: common prompt
- `scripts/run_evaluation.py`: llama.cpp OpenAI-compatible endpoint runner
- `scripts/score_results.py`: structural validity and latency summary

## Environment (Windows PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install requests jsonschema
```

## Start llama.cpp server
```powershell
llama-server.exe -m "C:\models\your-model-Q4_K_M.gguf" --host 127.0.0.1 --port 8080 -c 4096
```
Use a build supporting the OpenAI-compatible `/v1/chat/completions` endpoint. JSON mode support varies by build; if `response_format` is unsupported, remove it or use the JSON Schema/grammar constrained-output feature available in your build.

## Run
From `scripts`:
```powershell
python run_evaluation.py --model-name "candidate-a" --out ../results/candidate-a.jsonl
python score_results.py --results ../results/candidate-a.jsonl --out ../results/candidate-a-summary.json
```
Use the exact same prompt, test data, sampling parameters, and context length across models. Record GGUF filename, quantization, llama.cpp build/commit, GPU offload layers, context length, and machine memory usage.

## Limitations to resolve before reporting results
1. The test set contains semantic assertions and expected behaviors, not full gold-standard annotation for every memory/entity/relation.
2. The scorer reports only schema validity and latency; it does not calculate semantic precision/recall/F1.
3. Human-review the synthetic cases and add gold annotations before claiming model accuracy.
4. Cross-reference integrity, candidate ID validity, quote grounding, temporal consistency, deduplication and DB update policy need application-level tests.
5. `object`/`subject`/`target` use a discriminated value reference. The Schema constrains field types, but backend code must enforce kind-specific consistency (e.g. entity requires ref, literal requires value).
