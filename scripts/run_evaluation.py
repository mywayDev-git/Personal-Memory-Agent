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
    ap.add_argument("--endpoint",default="http://127.0.0.1:8080/v1/chat/completions")
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
                "max_tokens": 2500
            }
            t=time.perf_counter(); raw=None; request_error=None
            try:
                r=requests.post(a.endpoint,json=body,timeout=300); r.raise_for_status()
                raw=r.json()["choices"][0]["message"]["content"]
            except Exception as e: request_error=f"{type(e).__name__}: {e}"
            elapsed=time.perf_counter()-t; parsed=None; parse_error=None; errors=[]
            if raw:
                try:
                    parsed=json.loads(raw); errors=[e.message for e in validator.iter_errors(parsed)]
                except Exception as e: parse_error=f"{type(e).__name__}: {e}"
            rec={"case_id":c["case_id"],"category":c["category"],"model_name":a.model_name,"elapsed_seconds":round(elapsed,4),"request_error":request_error,"raw_output":raw,"parsed_output":parsed,"parse_error":parse_error,"schema_valid":bool(parsed is not None and not errors),"schema_errors":errors}
            f.write(json.dumps(rec,ensure_ascii=False)+"\n")
            print(f'{c["case_id"]}: valid={rec["schema_valid"]} latency={elapsed:.2f}s')
    print(f"Saved {len(data)} outputs to {out}")
if __name__=="__main__": main()
