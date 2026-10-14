"""Report observed answers and explicit adjudications; never equate answers with accuracy."""

import argparse
import csv
import hashlib
import html
import json
import math
import statistics
from collections import Counter
from pathlib import Path


def read_entries(path):
    return {
        e["case"]: e
        for p in path.glob("*.json")
        if isinstance(e := json.loads(p.read_text(encoding="utf-8")), dict) and "case" in e
    }


def text(response):
    return " | ".join(i["text"] for i in response.get("items", []))


def metrics(entries, reviews):
    rows = list(entries.values())
    calls = [c for e in rows for c in e.get("calls", [])]
    generation = [c for c in calls if c["endpoint"] == "completions"]
    seconds = sorted(e["seconds"] for e in rows)
    labels = Counter(
        reviews.get(e["case"], {}).get("judgment", "needs_review")
        for e in rows
        if e["case"] != "correction-2"
    )
    eligible = sum(labels.values())
    return dict(
        cases=len(rows),
        failures=sum(e["status"] != "complete" for e in rows),
        generation_calls=len(generation),
        embedding_calls=sum(c["endpoint"] == "embeddings" for c in calls),
        tokenizer_calls=sum(c["endpoint"] == "tokenize" for c in calls),
        failed_calls=sum(c["status"] != "ok" for c in calls),
        total_tokens=sum(c.get("total_tokens") or 0 for c in generation),
        calls_missing_token_usage=sum(c.get("total_tokens") is None for c in generation),
        median_seconds=round(statistics.median(seconds), 2) if seconds else None,
        p95_seconds=round(seconds[max(0, math.ceil(len(seconds) * 0.95) - 1)], 2)
        if seconds
        else None,
        judgments=dict(labels),
        eligible_cases=eligible,
        semantically_acceptable=sum(labels[k] for k in ("correct", "appropriate_abstention")),
        reviewed=sum(v for k, v in labels.items() if k != "needs_review"),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("output/downstream-final-report"))
    parser.add_argument("--before", type=Path, default=Path("output/downstream-before-v1"))
    parser.add_argument("--after", type=Path, default=Path("output/downstream-final-v8-frozen"))
    parser.add_argument("--live", type=Path, default=Path("output/downstream-final-v8-live"))
    parser.add_argument(
        "--distractors", type=Path, default=Path("output/downstream-final-v8-distractors")
    )
    parser.add_argument(
        "--diagnostic", type=Path, default=Path("output/downstream-final-v8-diagnostic")
    )
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True, parents=True)
    review_path = args.output / "review.json"
    reviews = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    dirs = {k: getattr(args, k) for k in ("before", "after", "live", "distractors")}
    entries = {k: read_entries(d) for k, d in dirs.items()}
    for arm, es in entries.items():
        for cid, entry in es.items():
            review = reviews.get(arm, {}).get(cid)
            if (
                review
                and review.get("response_sha256")
                != hashlib.sha256(
                    json.dumps(
                        entry.get("response", {}), ensure_ascii=False, sort_keys=True
                    ).encode()
                ).hexdigest()
            ):
                reviews[arm][cid] = {
                    "judgment": "needs_review",
                    "note": "출력이 달라져 기존 판정 무효",
                }
    cases = {
        c["id"]: c
        for d in dirs.values()
        if (d / "cases.json").exists()
        for c in json.loads((d / "cases.json").read_text(encoding="utf-8"))
    }
    summaries = {k: metrics(es, reviews.get(k, {})) for k, es in entries.items()}
    diagnostics = read_entries(args.diagnostic)
    diagnostic_comparison = []
    for cid, entry in diagnostics.items():
        review = reviews.get("diagnostic", {}).get(cid, {})
        for label, condition in entry.get("conditions", {}).items():
            adjudication = review.get("conditions", {}).get(label, {})
            fingerprint = hashlib.sha256(
                json.dumps(condition, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            if adjudication.get("response_sha256") != fingerprint:
                adjudication = {}
            diagnostic_comparison.append(
                dict(
                    case=cid,
                    condition=label,
                    answer=text(condition["response"]),
                    model_verified=condition["verified"],
                    raw_judgment=adjudication.get("raw_judgment", "needs_review"),
                    effective_judgment=adjudication.get("effective_judgment", "needs_review"),
                    note=review.get("note", ""),
                )
            )
    with (args.output / "information_loss.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(diagnostic_comparison[0]) if diagnostic_comparison else ["case"]
        )
        writer.writeheader()
        writer.writerows(diagnostic_comparison)
    summaries["diagnostic"] = metrics(diagnostics, reviews.get("diagnostic", {}))
    final_dirs = {d.resolve() for d in dirs.values()} | {
        args.diagnostic.resolve(),
        args.output.resolve(),
    }
    development = {
        f"{directory.name}/{cid}": entry
        for directory in Path("output").glob("downstream-*")
        if directory.is_dir() and directory.resolve() not in final_dirs
        for cid, entry in read_entries(directory).items()
    }
    summaries["development_saved_only"] = metrics(
        development,
        {e["case"]: {"judgment": "not_scored_development"} for e in development.values()},
    )
    (args.output / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = []
    for cid, case in cases.items():
        for arm, es in entries.items():
            if cid not in es:
                continue
            e = es[cid]
            r = reviews.get(arm, {}).get(cid, {})
            response = e.get("response", {})
            rows.append(
                dict(
                    case=cid,
                    arm=arm,
                    expected=case["expected"],
                    run_status=e["status"],
                    answer_status=response.get("status", "error"),
                    answer=text(response),
                    judgment=r.get("judgment", "needs_review"),
                    extraction_issue=r.get("extraction_issue", ""),
                    note=r.get("note", ""),
                    seconds=round(e["seconds"], 2),
                    evidence_ids="|".join(row["id"] for row in response.get("results", [])),
                )
            )
    with (args.output / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["case"])
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / "diagnostics.jsonl").open("w", encoding="utf-8") as f:
        for arm, es in entries.items():
            for cid, e in es.items():
                for event in e.get("diagnostics", []):
                    f.write(json.dumps(dict(arm=arm, case=cid, **event), ensure_ascii=False) + "\n")

    def esc(value):
        return html.escape(str(value))

    table = "".join(
        "<tr>"
        + "".join(
            f"<td>{esc(r[k])}</td>"
            for k in ("case", "arm", "expected", "answer", "judgment", "extraction_issue", "note")
        )
        + "</tr>"
        for r in rows
    )
    comparison = "".join(
        f"<tr><td>{esc(arm)}</td><td>{s['cases']}</td><td>{s['failures']}</td>"
        f"<td>{esc(s['judgments'])}</td><td>{s['generation_calls']}</td><td>{s['total_tokens']:,}</td>"
        f"<td>{s['median_seconds']}</td><td>{s['p95_seconds']}</td></tr>"
        for arm, s in summaries.items()
    )
    diagnostic_rows = "".join(
        "<tr>"
        + "".join(
            f"<td>{esc(r[k])}</td>"
            for k in (
                "case",
                "condition",
                "answer",
                "model_verified",
                "raw_judgment",
                "effective_judgment",
                "note",
            )
        )
        + "</tr>"
        for r in diagnostic_comparison
    )
    findings = reviews.get("findings", [])
    page = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><title>기억 후처리 수정 검증</title>
<style>body{{font-family:system-ui,sans-serif;line-height:1.65;max-width:1600px;margin:32px auto;padding:0 20px;color:#172838}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #cbd5df;padding:10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}}th{{background:#edf4fa}}h1,h2{{color:#134d70}}.scroll{{overflow-x:auto}}li{{margin-bottom:8px}}</style>
<h1>기억 후처리 수정 검증</h1>
<p>before/after는 같은 36개 원문·추출 기억·근거 위치를 사용하고 질문 해석·검색·답변은 실제 모델로 다시 실행했다.
live는 추출부터 새로 실행했다. 개인 DB에는 접근하지 않았다. 질문 기준일은 실행 날짜와 무관하게 2026-10-13으로 고정했다.</p>
<p>정답 설명은 모델에 전달하지 않았다. 이 사례들은 개발·회귀 데이터로 사용됐으며 독립 평가가 아니다.
판정은 원문과 답변을 대조한 에이전트 검토이며 독립된 사람의 재검토는 아니다. correction-2는 모순 정답이 모호하여 점수에서 제외한다.
답변 생성 여부와 의미 정확도를 구분한다. 추출 오류는 별도 열에 남기며 답변이 맞아도 저장된 추출이 고쳐졌다는 뜻은 아니다.</p>
<ul>{"".join("<li>" + esc(f) + "</li>" for f in findings)}</ul>
<h2>실행·판정·비용</h2><div class="scroll"><table><tr><th>조건</th><th>사례</th><th>실행 실패</th><th>의미 판정</th><th>생성 호출</th><th>생성 토큰</th><th>중앙값 초</th><th>p95 초</th></tr>{comparison}</table></div>
<p>frozen 시간에는 재생한 기억의 임베딩 호출이 포함되지만 추출 호출은 없다. live에는 추출부터 전체 경로가 포함된다.
diagnostic에는 기본 앱 답변과 세 조건의 답변·검증이 모두 포함된다. p95는 nearest-rank다. 토큰은 서버 usage이며 임베딩과 금액 환산은 제외한다.
로컬 서버 비용의 금전적 추정은 하지 않았다. 재시도는 자동으로 추가하지 않았으며 실패 출력도 보존했다.
development_saved_only는 별도로 보존된 개발 실행의 비용이다. 중단 당시 아직 저장되지 않은 호출은 빠져 있으므로 개발 총비용의 하한이다. 최종 비교의 비용·정확도와 합치지 않았다.</p>
<h2>수정 전후·새 추출·방해 기록</h2><div class="scroll"><table><tr><th>사례</th><th>조건</th><th>기준</th><th>답변</th><th>판정</th><th>추출 문제</th><th>비고</th></tr>{table}</table></div>
<h2>12개 사례의 정보 손실 비교</h2><p>세 조건은 동일한 답변·검증 프롬프트다. selected는 현재 검색 결과, all_memories는 사례의 모든 기억과 원문 근거, source는 원문 전체다.
검증 true는 의미 정답 판정이 아니다. 검증 후 판정은 false일 때 보류하는 조건으로 분석한 결과다.
기억의 인용 근거에도 원문이 포함되므로 이 비교만으로 추출 손실의 원인을 확정할 수 없다.</p>
<div class="scroll"><table><tr><th>사례</th><th>조건</th><th>생성 답변</th><th>모델 검증</th><th>원문 대조 판정</th><th>검증 후 판정</th><th>해석</th></tr>{diagnostic_rows}</table></div>
<p><a href="comparison.csv">비교 CSV</a> · <a href="information_loss.csv">정보 손실 비교 CSV</a> · <a href="summary.json">지표 JSON</a> · <a href="review.json">의미 검토</a> · <a href="diagnostics.jsonl">단계별 진단 JSONL</a></p></html>"""
    (args.output / "report.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
