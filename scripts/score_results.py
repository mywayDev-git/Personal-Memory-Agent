#!/usr/bin/env python3
"""Summarize structural validity and latency; not semantic accuracy/F1."""
import argparse,json,statistics
from pathlib import Path
from collections import defaultdict
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--results",default="../results/raw_results.jsonl")
    ap.add_argument("--out",default="../results/summary.json")
    a=ap.parse_args(); here=Path(__file__).resolve().parent
    def p(x):
        x=Path(x); return x if x.is_absolute() else (here/x).resolve()
    rows=[json.loads(x) for x in p(a.results).read_text(encoding="utf-8").splitlines() if x.strip()]
    n=len(rows); lat=[x["elapsed_seconds"] for x in rows if isinstance(x.get("elapsed_seconds"),(int,float))]
    cats=defaultdict(list)
    for r in rows: cats[r["category"]].append(r)
    summary={"cases_run":n,"schema_valid_count":sum(bool(r.get("schema_valid")) for r in rows),"schema_valid_rate":sum(bool(r.get("schema_valid")) for r in rows)/n if n else None,
      "mean_latency_seconds":statistics.mean(lat) if lat else None,"median_latency_seconds":statistics.median(lat) if lat else None,
      "p95_latency_seconds":sorted(lat)[max(0,int(.95*len(lat))-1)] if lat else None,
      "by_category":{k:{"cases":len(v),"schema_valid_rate":sum(bool(x.get("schema_valid")) for x in v)/len(v),"mean_latency_seconds":statistics.mean(x["elapsed_seconds"] for x in v)} for k,v in sorted(cats.items())},
      "warning":"This is structural/latency reporting only. It is not semantic accuracy, precision, recall, or F1."}
    out=p(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2)); print("Saved",out)
if __name__=="__main__": main()
