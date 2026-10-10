#!/usr/bin/env python3
import argparse, json, time
from pathlib import Path
import requests
from jsonschema import Draft202012Validator, FormatChecker

def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dataset",default="../datasets/test_v1.jsonl")
    ap.add_argument("--schema",default="../schema/memory_extraction_v1.schema.json")
    ap.add_argument("--prompt",default="../prompts/extraction_v1.txt")
    ap.add_argument("--endpoint",default="http://127.0.0.1:8081/v1/chat/completions")
    ap.add_argument("--model-name",default="local-gguf")
    ap.add_argument("--out",default="../results/raw_results.jsonl")
    ap.add_argument("--limit",type=int,default=0)
    a=ap.parse_args(); here=Path(__file__).resolve().parent
    def p(x):
        x=Path(x); return x if x.is_absolute() else (here/x).resolve()
    data=read_jsonl(p(a.dataset)); data=data[:a.limit] if a.limit else data
    schema=json.loads(p(a.schema).read_text(encoding="utf-8"))
    prompt=p(a.prompt).read_text(encoding="utf-8")
    validator=Draft202012Validator(schema,format_checker=FormatChecker())
    out=p(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf-8") as f:
        for c in data:
            user_payload={"source_id":c["input"]["source_id"],"reference_time":c["input"]["reference_time"],"language":"ko","text":c["input"]["text"],"existing_entities":c["input"]["existing_entities"]}
            body = {
                "model": a.model_name,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False)
                    }
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "memory_extraction",
                        "schema": schema
                    }
                },
                "max_tokens": 4069
            }
            
            t = time.perf_counter()
            raw = None
            request_error = None
            parse_error = None
            parsed = None
            errors = []

            http_status = None
            finish_reason = None
            usage = None
            response_body_excerpt = None
            request_status = "request_failed"

            try:
                r = requests.post(
                    a.endpoint,
                    json=body,
                    timeout=300
                )

                http_status = r.status_code
                response_body_excerpt = r.text[:1000]
                r.raise_for_status()

                response_json = r.json()
                choices = response_json.get("choices", [])

                if not choices:
                    request_status = "missing_choices"
                    raise ValueError(
                        "Response contains no choices"
                    )

                choice = choices[0]
                message = choice.get("message") or {}

                raw = message.get("content")
                finish_reason = choice.get("finish_reason")
                usage = response_json.get("usage")
                request_status = "response_received"
                
                print("finish_reason:", finish_reason)
                print("usage:", usage)
                print("message keys:", list(message.keys()))
                print("content length:", len(raw))
                print("reasoning_content length:",
                    len(message.get("reasoning_content") or ""))
            except requests.exceptions.Timeout as e:
                request_status = "timeout"
                request_error = f"{type(e).__name__}: {e}"

            except requests.exceptions.RequestException as e:
                request_status = "http_or_network_error"
                request_error = f"{type(e).__name__}: {e}"

            except (ValueError, KeyError, TypeError) as e:
                if request_status != "missing_choices":
                    request_status = "invalid_response"
                request_error = f"{type(e).__name__}: {e}"

            except Exception as e:
                request_status = "unexpected_error"
                request_error = f"{type(e).__name__}: {e}"

            elapsed = time.perf_counter() - t

            if raw is None:
                request_status = (
                    "empty_content_none"
                    if request_error is None
                    else request_status
                )
                parse_error = "Model content is None"

            elif not isinstance(raw, str):
                request_status = "unexpected_content_type"
                parse_error = (
                    f"Expected string, got {type(raw).__name__}"
                )

            elif not raw.strip():
                request_status = "empty_content"
                parse_error = "Model content is empty"

            else:
                try:
                    parsed = json.loads(raw)
                    errors = [
                        e.message
                        for e in validator.iter_errors(parsed)
                    ]
                except json.JSONDecodeError as e:
                    parse_error = (
                        f"{type(e).__name__}: {e}"
                    )
                except Exception as e:
                    parse_error = (
                        f"{type(e).__name__}: {e}"
                    )

            rec = {
                "case_id": c["case_id"],
                "category": c["category"],
                "model_name": a.model_name,
                "elapsed_seconds": round(elapsed, 4),
                "request_status": request_status,
                "request_error": request_error,
                "http_status": http_status,
                "finish_reason": finish_reason,
                "usage": usage,
                "content_type": (
                    type(raw).__name__ if raw is not None else None
                ),
                "raw_output": raw,
                "parsed_output": parsed,
                "parse_error": parse_error,
                "schema_valid": bool(
                    parsed is not None and not errors
                ),
                "schema_errors": errors,
                "response_body_excerpt": (
                    response_body_excerpt
                    if request_error is not None
                    else None
                ),
            }

            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()

            print(
                f'{c["case_id"]}: '
                f'status={request_status} '
                f'valid={rec["schema_valid"]} '
                f'latency={elapsed:.2f}s'
            )
    print(f"Saved {len(data)} outputs to {out}")
if __name__=="__main__": main()
