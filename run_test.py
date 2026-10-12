"""test.json 대량 테스트: 일기 40편을 연달아 돌려서 꼬임(편 사이 오염)과 오류를 찾는다.

필요한 파일(같은 폴더): pma_extract.py, timeparse.py, test.json
실행 순서
  1) python run_test.py              # 정방향 (약 12~15분)
  2) python run_test.py --reverse    # 역방향
  3) python run_test.py --compare    # 두 결과를 비교 (순서에 따라 달라지는 편 찾기)
옵션
  --limit N   앞의 N편만 (빠른 점검용, 예: --limit 10)
  --file F    다른 테스트 파일 사용 (기본 test.json)

확인하는 것
  - 형식 실패(재시도 후에도 JSON이 깨짐)
  - 사건 날짜가 정답(expect_start/end)과 같은지
  - 사람/장소가 일기 원문에 실제로 있는지 (없으면 앞 편 내용이 샌 것일 수 있음)
  - 정방향/역방향 결과가 같은지
"""
import argparse
import json
import time

RESULT = {"fwd": "results_test_fwd.json", "rev": "results_test_rev.json"}


def not_in_diary(unit: dict, diary: str) -> list[str]:
    """원문에 없는 사람/장소 값."""
    bad = [p for p in unit["people"] if p.strip() and p.strip() not in diary]
    place = unit["place"].strip()
    if place and place not in diary:
        bad.append(place)
    return bad


def run(path: str, reverse: bool, limit: int | None):
    import pma_extract  # Ollama가 필요하므로 --compare에서는 불러오지 않는다

    rows = json.load(open(path, encoding="utf-8"))
    if limit:
        rows = rows[:limit]
    if reverse:
        rows = list(reversed(rows))

    out, times = [], []
    n_fail = n_retry = n_bad_date = n_checked = n_foreign = 0
    for r in rows:
        t = time.time()
        unit, retried = pma_extract.extract_unit(r["diary"], r["written_at"])
        sec = time.time() - t
        times.append(sec)
        rec = {"id": r["id"], "tag": r.get("tag", ""), "retried": retried, "sec": round(sec, 1)}
        notes = []
        if unit is None:
            n_fail += 1
            rec["failed"] = True
            notes.append("형식 실패")
        else:
            u = unit.model_dump()
            rec["failed"] = False
            rec["unit"] = u
            if retried:
                n_retry += 1
            if "expect_start" in r:
                n_checked += 1
                got = (u["event_start"], u["event_end"])
                want = (r["expect_start"], r["expect_end"])
                if got != want:
                    n_bad_date += 1
                    notes.append(f"날짜 불일치 {got[0]}~{got[1]} (정답 {want[0]}~{want[1]}, 표현 '{u['event_expr']}')")
            foreign = not_in_diary(u, r["diary"])
            if foreign:
                n_foreign += 1
                notes.append(f"원문에 없는 값 {foreign}")
        out.append(rec)
        print(f"[{r['id']:>2}] {sec:5.1f}초 재시도 {retried} {r.get('tag', ''):<12}", "; ".join(notes) or "OK")

    print("\n=== 요약 ===")
    print(f"편수 {len(rows)} / 형식 실패 {n_fail} / 재시도 걸린 편 {n_retry}")
    print(f"날짜 정답 확인 {n_checked}편 중 불일치 {n_bad_date}")
    print(f"원문에 없는 사람·장소가 나온 편 {n_foreign}  (0이어야 정상, 많으면 편 사이 오염 의심)")
    print(f"평균 {sum(times) / len(times):.1f}초 / 편 (첫 편은 모델 로딩 포함)")
    name = RESULT["rev" if reverse else "fwd"]
    json.dump(out, open(name, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"저장: {name}")


def compare():
    a = {x["id"]: x for x in json.load(open(RESULT["fwd"], encoding="utf-8"))}
    b = {x["id"]: x for x in json.load(open(RESULT["rev"], encoding="utf-8"))}
    diff = suspicious = 0
    for i in sorted(a):
        if i not in b:
            continue
        ua, ub = a[i].get("unit"), b[i].get("unit")
        if ua == ub:
            continue
        diff += 1
        random_possible = a[i]["retried"] or b[i]["retried"]
        if not random_possible:
            suspicious += 1
        keys = [k for k in (ua or {}) if (ub or {}).get(k) != ua.get(k)] if ua and ub else ["(한쪽 실패)"]
        why = "재시도 있음(무작위 차이일 수 있음)" if random_possible else "재시도 없음 -> 순서 영향 의심"
        print(f"[{i}] 정방향/역방향 결과가 다름: 칸 {keys} - {why}")
    print(f"\n다른 편 {diff} / 순서 영향 의심 {suspicious}")
    if suspicious == 0:
        print("재시도 없이 달라진 편이 없으므로 순서 영향은 보이지 않음")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--file", default="test.json")
    args = ap.parse_args()
    if args.compare:
        compare()
    else:
        run(args.file, args.reverse, args.limit)