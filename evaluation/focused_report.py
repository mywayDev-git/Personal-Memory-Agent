"""Render manually reviewed, immutable run artifacts; never auto-grade semantics."""

import argparse
import hashlib
import html
import json
import statistics
from collections import Counter
from pathlib import Path

from evaluation.focused_cases import schedule


def render(directory):
    def load(name):
        return json.loads((directory / name).read_text(encoding="utf-8"))

    oracle, reviews = load("oracle.json"), load("reviews.json")
    expected = {f"{env}-{qid}" for env, qid in schedule()}
    assert {r["run_id"] for r in reviews} == expected and len(reviews) == 80
    runs = {}
    for review in reviews:
        path = directory / "runs" / (review["run_id"] + ".json")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == review["run_sha256"]
        runs[review["run_id"]] = json.loads(path.read_text(encoding="utf-8"))
    groups = {}
    for env in sorted({r["environment"] for r in reviews}):
        rs = [r for r in reviews if r["environment"] == env]
        ts = sorted(runs[r["run_id"]]["elapsed_seconds"] for r in rs)
        groups[env] = dict(
            counts=dict(Counter(r["verdict"] for r in rs)),
            median_seconds=statistics.median(ts),
            p95_seconds=ts[min(len(ts) - 1, int(len(ts) * 0.95))],
        )
    summary = dict(
        planned=80,
        executed=len(runs),
        missing=[],
        execution_errors=sum("execution_error" in r for r in runs.values()),
        questions_reviewed=len({r["question_id"] for r in reviews}),
        runs_reviewed=len(reviews),
        reviewer="Codex source-and-trace review; human review pending",
        verdicts=dict(Counter(r["verdict"] for r in reviews)),
        environments=groups,
        failure_stages=dict(
            Counter(r["primary_stage"] for r in reviews if r["verdict"] != "correct")
        ),
        input_not_ready_runs=[k for k, r in runs.items() if r["input_not_ready"]],
        coincidental_abstentions=[r["run_id"] for r in reviews if r["coincidental_abstention"]],
    )
    answered = [r for r in runs.values() if r.get("response", {}).get("items")]
    summary["citation_existence"] = {
        "answered_runs": len(answered),
        "valid": sum(r["automatic_checks"]["citation_ids_exist"] for r in answered),
        "note": "ID existence is not claim support or answer accuracy",
    }
    comparisons = []

    def answer_signature(r):
        a = r["response"]
        return (a["status"], [i["text"] for i in a.get("items", [])], a.get("clarification"))

    for before, after, ids in [
        ("gift_before", "gift_after", ["G1", "G2"]),
        ("run_before", "run_after", ["R3", "R4"]),
    ]:
        for q in ids:
            comparisons.append(
                dict(
                    question_id=q,
                    before=before,
                    after=after,
                    answer_unchanged=answer_signature(runs[f"{before}-{q}"])
                    == answer_signature(runs[f"{after}-{q}"]),
                )
            )
    summary["addition_checks"] = comparisons
    (directory / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    esc = html.escape
    labels = {"correct": "정답", "partial": "부분 정답·미답", "incorrect": "오답"}
    out = [
        '<!doctype html><html lang="ko"><meta charset="utf-8"><title>기억 답변 정확성 검증</title><style>body{font:16px/1.65 system-ui;max-width:1200px;margin:40px auto;padding:0 24px;color:#253040;background:#f6f7fa}h1,h2{color:#152745}table{border-collapse:collapse;width:100%;background:white;margin:20px 0}td,th{border:1px solid #d6dce4;padding:10px;text-align:left;vertical-align:top}details{background:white;padding:16px;margin:12px 0;border:1px solid #d6dce4;border-radius:8px}summary{cursor:pointer;font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}blockquote{border-left:3px solid #90a4ba;padding-left:16px;margin-left:0}.incorrect{color:#a42121}.partial{color:#875b09}.correct{color:#176c48}input{padding:12px;width:90%;margin:12px 0}small{color:#526375}a{color:#1958a2}</style><h1>원문 6묶음 · 36질문 답변 검증</h1>'
    ]
    out.append(
        "<p>80/80회 실행 · 36/36질문 의미 검토 · 원문/추출/벡터 재생성 없음 · API 및 검색 코드 변경 없음</p>"
    )
    out.append(
        "<p>판정은 Codex가 원문·응답·추적 결과를 대조한 검토입니다. 사람의 최종 검수는 대기 상태입니다. 부분 정답에는 필요한 내용을 답하지 못한 과도한 판단 보류가 포함됩니다.</p>"
    )
    out.append(
        "<p><b>"
        + esc(" · ".join(labels[k] + " " + str(v) + "회" for k, v in summary["verdicts"].items()))
        + "</b></p>"
    )
    out.append(
        "<p>숫자는 서로 다른 36질문의 환경별 반복을 포함합니다. 일반적인 서비스 정확도로 확대 해석하지 않습니다. D6·P6의 4회는 답변 보류 결과만 맞았으며 내부 처리 오류가 있어 안정적인 성공으로 보지 않습니다.</p>"
    )
    out.append(
        "<h2>환경별 결과</h2><table><tr><th>환경</th><th>정답 / 부분·미답 / 오답</th><th>중앙값 / p95</th></tr>"
    )
    for env, v in groups.items():
        out.append(
            f"<tr><td>{esc(env)}</td><td>{v['counts'].get('correct', 0)} / {v['counts'].get('partial', 0)} / {v['counts'].get('incorrect', 0)}</td><td>{v['median_seconds']:.2f}s / {v['p95_seconds']:.2f}s</td></tr>"
        )
    out.append(
        "</table><h2>다음 수정 우선순위</h2><ol><li>질문에서 인물과 일반 단어를 구분: 먹은→먹, 같이→같, 잡은→잡, 환불은→환불 등 잘못된 actor 조건을 제거해야 합니다.</li><li>파생 사실 조건을 점검: object의 9km 누락, 좋다/사고 싶다 관계 미인식, 동행자가 object에 있을 때 전체 DB에서만 배제되는 문제입니다.</li><li>검색의 최종 후보 구성을 개선: 부산 활동은 9위·12위에서 잘리고, 8만원 구매는 선택 모델이 버리는 경우가 있습니다.</li><li>전제 정정·복합 질문·정정 이력을 별도로 처리: 틀린 전제를 필터로 강제하지 않고, 확실한 부분과 불확실한 부분을 함께 답해야 합니다.</li><li>인용의 실제 뒷받침 여부를 검증: 유선 구매 인용으로 무선 희망을 답해도 모델 검증이 통과했습니다. 인용 ID 존재 검사만으로는 부족합니다.</li></ol>"
    )
    out.append(
        "<p>추가 전후 4쌍은 모두 답변이 유지됐습니다. 그러나 G1·R4는 추가 전부터 미답이었으므로 안정성 통과가 정확성 통과를 뜻하지 않습니다. 전체 DB에서는 G3·D3 등이 악화됐습니다.</p>"
    )
    out.append(
        '<h2>질문별 비교</h2><input id="filter" placeholder="질문 ID, 질문, 오류 원인 검색" aria-label="검증 결과 검색">'
    )
    lookup = {r["run_id"]: r for r in reviews}
    for c in oracle["cases"]:
        out.append(
            f'<details class="case"><summary>{esc(c["id"])} · {esc(c["question"])}</summary><p><b>기대:</b> {esc(c["expected"])}</p><p><b>금지:</b> {esc(c["forbidden"])}</p>'
        )
        if c.get("oracle_note"):
            out.append("<p><b>질문 명세 주의:</b> " + esc(c["oracle_note"]) + "</p>")
        for env, q in schedule():
            if q != c["id"]:
                continue
            key = f"{env}-{q}"
            r = runs[key]
            v = lookup[key]
            a = r.get("response", {})
            texts = [i["text"] for i in a.get("items", [])]
            text = "\n".join(texts) or a.get("clarification") or "근거 부족으로 답변 보류"
            out.append(
                f'<h3 class="{v["verdict"]}">{esc(env)} · {labels[v["verdict"]]} · {r["elapsed_seconds"]:.2f}초</h3><blockquote>{esc(text)}</blockquote><p>{esc(v["note"])}</p><p><small>최초 진단 단계: {esc(v["primary_stage"] or "해당 없음")} · 검색 원문: {esc(", ".join(r["automatic_checks"]["retrieved_sources"]))}</small></p><a href="runs/{key}.json">답변·필터·후보 원본 JSON</a>'
            )
        out.append("<details><summary>기대 근거 원문</summary>")
        for source in oracle["sources"]:
            if source["id"] in c["required_sources"]:
                out.append(
                    "<p><b>"
                    + esc(source["id"])
                    + "</b> · 기준 시각 "
                    + esc(source["reference_time"])
                    + "</p><blockquote>"
                    + esc(source["text"])
                    + "</blockquote>"
                )
        out.append("</details></details>")
    out.append(
        '<h2>재현 자료</h2><p><a href="summary.json">집계 JSON</a> · <a href="reviews.json">80회 의미 검토</a> · <a href="oracle.json">사전 기대 결과·42개 원문</a> · <a href="manifest.json">실행 구성</a> · <a href="copy_integrity.json">복사 무결성</a> · <a href="executed-code.zip">실행 코드 보존본</a></p><script>document.getElementById("filter").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll(".case").forEach(x=>x.hidden=!x.textContent.toLowerCase().includes(q));});</script></html>'
    )
    (directory / "report.html").write_text("".join(out), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    render(parser.parse_args().directory)
