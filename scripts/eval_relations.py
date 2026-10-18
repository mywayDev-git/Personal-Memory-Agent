"""실제 모델의 관계 추출을 소수 고정 사례로 확인합니다. 전체 정확도 평가는 아닙니다."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

CASES = [
    dict(
        id="companion",
        text="어제 민수와 도서관에서 데이터베이스 과제를 마쳤다. 다음 주 금요일에 지현과 캡스톤 발표를 준비하기로 했다.",
        expected=[
            dict(
                words=["민수", "과제"], actor="사용자", obj="과제", kind="event", date="2026-10-13"
            ),
            dict(
                words=["지현", "발표"], actor="사용자", obj="발표", kind="plan", date="2026-10-23"
            ),
        ],
    ),
    dict(
        id="transfer",
        text="어제 지현이 나에게 책을 줬다. 나는 민수에게 펜을 줬다. 나는 수진에게서 공책을 받았다.",
        expected=[
            dict(
                words=["지현", "나에게", "책"], actor="지현", obj="책", verb="주", date="2026-10-13"
            ),
            dict(words=["민수", "펜"], actor="사용자", obj="펜", verb="주", date=None),
            dict(words=["수진", "공책"], actor="사용자", obj="공책", verb="받", date=None),
        ],
    ),
    dict(
        id="varied",
        text="유나는 도윤의 누나이다. 새봄연구실은 한빛대학교에 소속되어 있다. 나는 태호에게 선물을 주지 않았다. 내일 서연과 공원에서 산책할 예정이다.",
        expected=[
            dict(words=["유나", "도윤"], actor="유나", obj="도윤"),
            dict(words=["새봄연구실", "한빛대학교"], actor="새봄연구실", obj="한빛대학교"),
            dict(words=["태호", "선물"], actor="사용자", obj="선물", polarity="negated"),
            dict(words=["서연", "산책"], actor="사용자", kind="plan", date="2026-10-15"),
        ],
    ),
]


def checks(case, result):
    memories = result["memories"]
    report = {"기억_개수": len(memories) == len(case["expected"])}
    for index, expected in enumerate(case["expected"]):
        # Exact objects disambiguate 책 versus 공책; content matching alone does not.
        rows = [m for m in memories if all(w in m["content"] for w in expected["words"])]
        if case["id"] == "transfer":
            rows = [m for m in rows if m["object"]["value"] == expected["obj"]]
        key = f"사건{index + 1}"
        report[key + "_보존"] = bool(rows)
        report[key + "_주체"] = any(m["subject"]["value"] == expected["actor"] for m in rows)
        if "obj" in expected:
            report[key + "_대상"] = any(expected["obj"] in str(m["object"]["value"]) for m in rows)
        if "kind" in expected:
            report[key + "_유형"] = any(m["memory_type"] == expected["kind"] for m in rows)
        if "date" in expected:
            report[key + "_날짜"] = any(m["time"]["start"] == expected["date"] for m in rows)
        if "polarity" in expected:
            report[key + "_부정"] = any(
                m["assertion_polarity"] == expected["polarity"] for m in rows
            )
        if "verb" in expected:
            verbs = ("주", "줬", "선물", "전달") if expected["verb"] == "주" else ("받", "수령")
            report[key + "_방향"] = any(m["predicate"].startswith(verbs) for m in rows)
        if case["id"] == "varied" and index == 3:
            report[key + "_동행인을대상으로혼동하지않음"] = bool(rows) and all(
                m["object"]["value"] != "서연" for m in rows
            )
    if case["id"] == "companion":
        report["잘못된_동행대상_없음"] = all(
            not m["target"]
            or not any(w in m["target"]["predicate"] for w in ("동반", "함께", "동행"))
            or m["target"]["object"]["value"] not in ("도서관", "다음 주 금요일")
            for m in memories
        )
        report["동행관계_보존"] = all(
            any(
                m["target"]
                and {m["target"]["subject"]["value"], m["target"]["object"]["value"]}
                == {"사용자", name}
                and any(w in m["target"]["predicate"] for w in ("동반", "동행", "함께", "같이"))
                for m in memories
            )
            for name in ("민수", "지현")
        )
    if case["id"] == "transfer":
        # Fixed expected roles, independent of the production relation validator.
        actors = {"책": ("지현", "사용자"), "펜": ("사용자", "민수"), "공책": ("수진", "사용자")}
        valid_targets = True
        for memory in memories:
            target = memory["target"]
            if not target:
                continue
            obj = memory["object"]["value"]
            if obj not in actors or all(
                target[k] == memory[k] for k in ("subject", "predicate", "object")
            ):
                valid_targets = False
                continue
            giver, receiver = actors[obj]
            verb = target["predicate"]
            if verb in ("주다", "줬다", "주었다", "줌"):
                valid_targets &= (
                    target["subject"]["value"] == giver and target["object"]["value"] == obj
                )
            elif verb in ("받다", "받았다", "받음"):
                valid_targets &= (
                    target["subject"]["value"] == receiver and target["object"]["value"] == obj
                )
            else:
                valid_targets = False  # Needs manual review for an unlisted relation.
        report["추가관계_방향과중복"] = valid_targets
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=[c["id"] for c in CASES])
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.insert(0, str(root))
    import requests

    from config.settings import Settings, paths
    from scripts.memory_agent.pipeline import process_text
    from scripts.memory_agent.provenance import sentences
    from scripts.memory_agent.validator import load_schema

    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "evaluation_type": "fresh_model_inference",
        "reference_time": "2026-10-14T14:36:00+09:00",
        "repository": str(root),
        "cases": [],
        "limitations": "소수 합성 사례 검사이며 일반 정확도가 아닙니다.",
    }
    report["source_hashes"] = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root / "scripts/memory_agent").glob("*.py"))
    }

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    settings = Settings(model="Qwen3-8B-Q4_K_M", timeout=1800, max_tokens=3072)
    report["settings"] = vars(settings)
    for case in CASES:
        if args.case and args.case != case["id"]:
            continue
        row = dict(id=case["id"], source=case["text"], status="running", responses=[])
        report["cases"].append(row)
        save()
        print("시작: " + case["id"], flush=True)
        started = time.monotonic()

        class Recorder(requests.Session):
            def post(self, url, **kwargs):
                response = super().post(url, **kwargs)
                row["responses"].append(
                    {"request": kwargs.get("json"), "response": response.json()}
                )
                save()
                return response

        try:
            with Recorder() as session:
                session.trust_env = False
                units = sentences(case["text"])
                result, metadata = process_text(
                    case["text"],
                    dict(
                        source_id="relation-" + case["id"],
                        reference_time=report["reference_time"],
                        language="ko",
                    ),
                    prompt=paths.prompt.read_text(encoding="utf-8"),
                    output_schema=load_schema(paths.output_schema),
                    final_schema=load_schema(paths.final_schema),
                    session=session,
                    settings=settings,
                    source_units=units,
                    target_ids=[u["id"] for u in units],
                )
            row.update(status="ok", result=result, metadata=metadata, checks=checks(case, result))
        except Exception as exc:
            row.update(status="error", error=str(exc))
        row["seconds"] = round(time.monotonic() - started, 2)
        save()
        print(
            json.dumps({k: row[k] for k in ("id", "status", "seconds")}, ensure_ascii=False),
            flush=True,
        )
    return int(any(row["status"] != "ok" for row in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
