"""기억 추출 정확도 평가 스크립트.

사용법 (extract_memory.py, gold_diaries.json 과 같은 폴더에서):
    python eval_extract.py
    python eval_extract.py qwen3:4b-instruct   # 모델 이름을 바꿔서 비교할 때
"""
import json
import sys
import time
from pathlib import Path

import extract_memory as em

HERE = Path(__file__).parent
FIELDS = ["people", "emotion", "problem", "plan", "result"]
TEXT_FIELDS = ["emotion", "problem", "plan", "result"]


def text_ok(text: str, kws: list) -> bool:
    text = text.strip()
    if not kws:
        return text == ""
    return any(k in text for k in kws)


def people_ok(out: list, gold: list) -> bool:
    out = [o.strip() for o in out if o.strip()]
    found_all = all(any(g in o or o in g for o in out) for g in gold)
    extra = [o for o in out if not any(g in o or o in g for g in gold)]
    return found_all and not extra


def main():
    if len(sys.argv) > 1:
        em.MODEL = sys.argv[1]
    data = json.loads((HERE / "gold_diaries.json").read_text(encoding="utf-8"))

    score = {f: 0 for f in FIELDS}
    halluc = {f: 0 for f in TEXT_FIELDS}
    parse_fail = 0
    retries_total = 0
    total_sec = 0.0
    rows = []

    print(f"모델: {em.MODEL}, 일기 {len(data)}개 평가 시작\n")
    for g in data:
        t = time.time()
        m, retried = em.extract(g["diary"], "2026-10-05")
        sec = time.time() - t
        total_sec += sec
        retries_total += retried

        if m is None:
            parse_fail += 1
            print(f"[{g['id']}] 실패 (형식 깨짐)  {sec:.1f}초")
            rows.append({"id": g["id"], "output": None})
            continue

        outs = {
            "people": m.people,
            "emotion": m.emotion,
            "problem": m.problem,
            "plan": (m.decision + " " + m.next_action).strip(),
            "result": m.result,
        }
        wrong = []
        for f in FIELDS:
            ok = people_ok(outs[f], g[f]) if f == "people" else text_ok(outs[f], g[f])
            if ok:
                score[f] += 1
            else:
                wrong.append(f)
            if f in TEXT_FIELDS and not g[f] and outs[f].strip():
                halluc[f] += 1

        mark = "OK " if not wrong else "틀림"
        print(f"[{g['id']}] {mark} {sec:.1f}초  {g['diary']}")
        for f in wrong:
            print(f"     - {f}: 정답 {g[f]} / 모델 {outs[f]}")
        rows.append({"id": g["id"], "output": m.model_dump(), "wrong": wrong})

    n = len(data)
    print("\n===== 요약 =====")
    print(f"형식 실패: {parse_fail}/{n}   재시도 총 {retries_total}회   평균 {total_sec / n:.1f}초")
    for f in FIELDS:
        print(f"{f:8s} 정확도 {score[f]}/{n} ({score[f] / n * 100:.0f}%)")
    print("지어낸 값(정답은 빈 칸인데 채움): " + ", ".join(f"{f} {halluc[f]}" for f in TEXT_FIELDS))

    out_name = "results_" + em.MODEL.replace(":", "_").replace("/", "_") + ".json"
    (HERE / out_name).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n상세 결과 저장: {out_name}")


if __name__ == "__main__":
    main()