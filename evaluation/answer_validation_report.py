"""Report adjudicated accuracy separately from model validation and execution status."""

import argparse
import csv
import hashlib
import html
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

LABELS = {
    "correct",
    "incorrect",
    "appropriate_abstention",
    "over_abstention",
    "needs_review",
    "excluded",
}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, default=Path("output/answer-validation-v1"))
    parser.add_argument("--tag", default="final-1")
    args = parser.parse_args()
    root = args.root
    reviews_path = root / "review.json"
    reviews = json.loads(reviews_path.read_text(encoding="utf-8")) if reviews_path.exists() else {}
    replacement_path = root / "replacements.json"
    replacements = (
        json.loads(replacement_path.read_text(encoding="utf-8"))
        if replacement_path.exists()
        else {}
    )
    files = sorted(p for p in (root / args.tag).glob("*/*--*.json") if p.parent.name != "prepare")
    groups = defaultdict(list)
    rows = []
    blocks = []
    cases = {}
    for p in (root / args.tag).glob("*/cases.json"):
        cases.update({c["id"]: c for c in json.loads(p.read_text(encoding="utf-8"))})
    with (root / "diagnostics.jsonl").open("w", encoding="utf-8") as out:
        for matrix_path in files:
            matrix_key = str(matrix_path.relative_to(root)).replace("\\", "/")
            path = root / replacements.get(matrix_key, matrix_key)
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("INVALID_REPLACEMENT_PATH")
            data = json.loads(path.read_text(encoding="utf-8"))
            if path != matrix_path:
                original = json.loads(matrix_path.read_text(encoding="utf-8"))
                if (data["case"], data["condition"]) != (original["case"], original["condition"]):
                    raise ValueError("REPLACEMENT_CASE_MISMATCH")
            key = str(path.relative_to(root)).replace("\\", "/")
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            review = reviews.get(key, {})
            if review and review.get("sha256") != sha:
                raise ValueError(f"Stale adjudication: {key}")
            label = review.get("label", "needs_review")
            if label not in LABELS:
                raise ValueError(label)
            if data["case"] == "correction-2":
                label = "excluded"
            calls = [c for c in data.get("calls", []) if c["endpoint"] == "completions"]
            traces = data.get("diagnostics", [])
            repair = any(t["stage"] in {"repair_start", "answer_repair"} for t in traces)
            row = dict(
                phase=path.parent.name,
                condition=data["condition"],
                case=data["case"],
                cohort=(
                    "distractors8"
                    if data["case"].startswith("distractor-")
                    else "repeat_questions2"
                    if data["case"].startswith("av-repeat-")
                    else "new24"
                    if data["case"].startswith("av-")
                    else "legacy36"
                ),
                category=cases[data["case"]].get("category", "unknown"),
                split=cases[data["case"]].get("split", "regression"),
                execution=data["status"],
                judgment=label,
                reason=review.get("reason", "원문 대조 필요"),
                calls=len(calls),
                requests=len(data.get("calls", [])),
                embedding_calls=sum(c["endpoint"] == "embeddings" for c in data.get("calls", [])),
                validation_errors=sum(
                    t["stage"] in {"verification_error", "answer_error"} for t in traces
                ),
                tokens=sum(c.get("total_tokens") or 0 for c in calls),
                seconds=data["seconds"],
                repair=int(repair),
                file=key,
                matrix_file=matrix_key,
                sha256=sha,
            )
            rows.append(row)
            groups[(row["phase"], row["condition"])].append(row)
            out.write(json.dumps(dict(**row, result=data), ensure_ascii=False) + "\n")
            case = cases[data["case"]]
            answer = (
                "\n".join(i["text"] for i in data.get("response", {}).get("items", []))
                or "[빈 답변]"
            )
            source = "\n".join(
                f"[문서 기준시각: {r.get('reference_time') or '없음'}]\n{r['text']}"
                for r in case["records"]
            )
            blocks.append(
                f"<details><summary>{html.escape(key)} — {label}</summary><pre>{html.escape(source)}</pre>"
                f"<p>{html.escape(case['questions'][0]['text'])}</p><pre>{html.escape(answer)}</pre>"
                f"<p>사전 정답 조건: {html.escape(case.get('expected', ''))}</p>"
                f"<p>금지 추론: {html.escape(case.get('forbidden', '사전 정답 조건 참조'))}</p>"
                f"<p>판정: {html.escape(row['reason'])}</p><pre>{html.escape(json.dumps(traces, ensure_ascii=False, indent=2))}</pre></details>"
            )
    if not rows:
        raise ValueError("No runs")
    with (root / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summaries = []
    for (phase, condition), values in groups.items():
        counts = Counter(v["judgment"] for v in values)
        times = sorted(v["seconds"] for v in values)
        summaries.append(
            dict(
                phase=phase,
                condition=condition,
                total=len(values),
                scored=len(values) - counts["excluded"],
                judgments=dict(counts),
                acceptable=counts["correct"] + counts["appropriate_abstention"],
                failures=sum(v["execution"] != "complete" for v in values),
                calls=sum(v["calls"] for v in values),
                requests=sum(v["requests"] for v in values),
                embedding_calls=sum(v["embedding_calls"] for v in values),
                validation_errors=sum(v["validation_errors"] for v in values),
                tokens=sum(v["tokens"] for v in values),
                repairs=sum(v["repair"] for v in values),
                median_seconds=statistics.median(times),
                p95_seconds=times[math.ceil(len(times) * 0.95) - 1],
            )
        )
    (root / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    category_rows = []
    categories = defaultdict(list)
    for row in rows:
        categories[(row["phase"], row["condition"], row["category"], row["split"])].append(row)
    for (phase, condition, category, split), values in categories.items():
        counts = Counter(v["judgment"] for v in values)
        category_rows.append(
            dict(
                phase=phase,
                condition=condition,
                category=category,
                split=split,
                total=len(values),
                **{label: counts[label] for label in sorted(LABELS)},
            )
        )
    with (root / "condition_summary.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(category_rows[0]))
        writer.writeheader()
        writer.writerows(category_rows)
    cohorts = defaultdict(list)
    for row in rows:
        cohorts[(row["phase"], row["condition"], row["cohort"], row["split"])].append(row)
    cohort_rows = []
    for (phase, condition, cohort, split), values in cohorts.items():
        counts = Counter(v["judgment"] for v in values)
        cohort_rows.append(
            dict(
                phase=phase,
                condition=condition,
                cohort=cohort,
                split=split,
                scored=len(values) - counts["excluded"],
                acceptable=counts["correct"] + counts["appropriate_abstention"],
                **{label: counts[label] for label in sorted(LABELS)},
            )
        )
    with (root / "cohort_summary.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(cohort_rows[0]))
        writer.writeheader()
        writer.writerows(cohort_rows)
    metrics = "".join(
        f"<tr><td>{s['phase']}/{s['condition']}</td><td>{s['acceptable']}/{s['scored']}</td><td>{html.escape(str(s['judgments']))}</td><td>{s['calls']}</td><td>{s['tokens']:,}</td><td>{s['repairs']}</td><td>{s['median_seconds']:.2f} / {s['p95_seconds']:.2f}</td></tr>"
        for s in summaries
    )
    page = (
        """<!doctype html><html lang="ko"><meta charset="utf-8"><title>답변·검증 비교 실험</title>
<style>body{max-width:1300px;margin:40px auto;font:16px/1.6 system-ui;padding:0 24px;color:#172134;background:#f6f8fc}table{border-collapse:collapse;background:white;width:100%}td,th{border:1px solid #ccd4df;padding:10px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef1f7;padding:16px}details{background:white;margin:12px 0;padding:14px}summary{cursor:pointer}h1{font-size:28px}</style>
<h1>답변·검증 개선 비교 실험</h1><p><strong>__ADOPTION_DECISION__</strong></p><p>baseline=기존 방식 · answer=답변 개선 · review=답변 개선+상세 검증 · repair=검증 실패 시 최대 1회 수정·재검증.</p><p>같은 추출·검색 근거를 사용하는 네 조건과 전체 앱 경로를 비교합니다. 정확도는 원문과 대조한 별도 판정이며 검증 통과율이나 답변 생성률이 아닙니다. 판정은 에이전트 검토이며 독립된 사람의 평가가 아닙니다.</p>
<p>추출·검색·정정 연결은 이번 변경 범위 밖입니다. correction-2는 점수 제외, correction-1은 기존 정답 유지 및 질문 모호성 표시. 검토 필요 결과는 성공으로 계산하지 않습니다. 비용은 호출·토큰·실행시간으로 표시하며 로컬 실행 비용을 금액으로 환산하지 않습니다. 고정 근거 조건은 질문 해석·검색 비용을 제외합니다. 전체 앱 조건은 이를 포함하고 live는 추출 비용도 포함합니다.</p>
<table><thead><tr><th>조건</th><th>정답+적절한 보류</th><th>판정 분포</th><th>생성 호출</th><th>생성 토큰</th><th>수정 시도</th><th>시간 중앙값 / p95 (초)</th></tr></thead><tbody>"""
        + metrics
        + "</tbody></table>"
    )
    completed = sum(r["execution"] == "complete" for r in rows)
    progress = f"<p>평가 행 {len(rows)} / {len(cases) * 6 + 16} · 실행 완료 {completed} · 원문 대조 미완료 {sum(r['reason'] == '원문 대조 필요' for r in rows)}</p>"
    page = page.replace("<table><thead>", progress + "<table><thead>", 1)
    legacy = [r for r in cohort_rows if r["phase"] == "fixed" and r["cohort"] == "legacy36"]
    page += "<h2>기존 고정 회귀 35개 별도 비교</h2><table><tr><th>조건</th><th>정답+적절한 보류</th><th>오답</th><th>과도한 보류</th><th>검토 필요</th></tr>"
    for r in legacy:
        page += f"<tr><td>{r['condition']}</td><td>{r['acceptable']}/{r['scored']}</td><td>{r['incorrect']}</td><td>{r['over_abstention']}</td><td>{r['needs_review']}</td></tr>"
    page += "</table>"
    findings = root / "findings.json"
    if findings.exists():
        page += (
            "<h2>결론과 남은 실패</h2><ul>"
            + "".join(
                "<li>" + html.escape(x) + "</li>"
                for x in json.loads(findings.read_text(encoding="utf-8"))
            )
            + "</ul>"
        )
    page += "<h2>사례와 단계별 진단</h2>" + "".join(blocks) + "</html>"
    decision_path = root / "decision.json"
    decision = (
        json.loads(decision_path.read_text(encoding="utf-8")) if decision_path.exists() else {}
    )
    message = (
        decision.get("message", "채택 미확정: 원문 대조 평가가 필요합니다.")
        if decision.get("tag") == args.tag
        else "채택 미확정: 이 실행의 판정이 필요합니다."
    )
    page = page.replace("__ADOPTION_DECISION__", html.escape(message))
    (root / "report.html").write_text(page, encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
