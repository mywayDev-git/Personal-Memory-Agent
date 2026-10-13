# check_order.py  (gold_diaries.json, pma_extract.py와 같은 폴더)
import json
import legacy_pma_extract as pma_extract

gold = json.load(open("gold_diaries.json", encoding="utf-8"))[:10]

def run(order):
    out = {}
    for g in order:
        u, retried = pma_extract.extract_unit(g["diary"], "2026-10-10")
        out[g["id"]] = (u.model_dump() if u else None, retried)
    return out

fwd = run(gold)
rev = run(list(reversed(gold)))

for g in gold:
    a, b = fwd[g["id"]], rev[g["id"]]
    if a[0] != b[0]:
        note = "재시도 있음(무작위 가능)" if a[1] or b[1] else "재시도 없음 → 순서 영향 의심"
        print(f"[{g['id']}] 결과가 다름 - {note}")
print("비교 끝")
