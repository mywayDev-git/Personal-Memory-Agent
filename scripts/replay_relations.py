"""저장된 실제 응답으로 후처리를 재검증합니다. 생성 요청이 다르면 거부합니다."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ReplaySession:
    def __init__(self, responses):
        self.responses = responses
        self.used = 0

    def post(self, url, **kwargs):
        if self.used >= len(self.responses):
            raise ValueError("저장 응답 부족: 실제 모델의 추가 호출이 필요합니다.")
        recorded = self.responses[self.used]
        if kwargs["json"] != recorded["request"]:
            raise ValueError("생성 요청 변경: 저장 응답을 재사용할 수 없습니다.")
        self.used += 1

        class Response:
            status_code = 200

            def json(self):
                return recorded["response"]

        return Response()


def replay(report, allow_obsolete_repairs=False):
    from config.settings import Settings, paths
    from scripts.eval_relations import CASES, checks
    from scripts.memory_agent.pipeline import process_text
    from scripts.memory_agent.provenance import sentences
    from scripts.memory_agent.validator import load_schema

    results = []
    for row in report["cases"]:
        session = ReplaySession(row["responses"])
        units = sentences(row["source"])
        try:
            result, metadata = process_text(
                row["source"],
                dict(
                    source_id="relation-" + row["id"],
                    reference_time=report["reference_time"],
                    language="ko",
                ),
                prompt=paths.prompt.read_text(encoding="utf-8"),
                output_schema=load_schema(paths.output_schema),
                final_schema=load_schema(paths.final_schema),
                session=session,
                settings=Settings(**report["settings"]),
                source_units=units,
                target_ids=[u["id"] for u in units],
            )
            unused = row["responses"][session.used :]
            if unused and not (
                allow_obsolete_repairs
                and all(
                    "관계 검사에서 오류가 발견됐다" in r["request"]["messages"][0]["content"]
                    for r in unused
                )
            ):
                raise ValueError("사용하지 않은 응답 존재: 호출 흐름 변경을 확인하세요.")
            metadata.pop("latency_seconds", None)
            results.append(
                dict(
                    id=row["id"],
                    status="ok",
                    source=row["source"],
                    result=result,
                    metadata=metadata,
                    unused_recorded_relation_repairs=len(unused),
                    checks=checks(next(c for c in CASES if c["id"] == row["id"]), result),
                )
            )
        except Exception as exc:
            results.append(dict(id=row["id"], status="error", error=str(exc)))
    return dict(
        evaluation_type="recorded_model_output_replay",
        cases=results,
        source_hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "scripts/memory_agent").glob("*.py"))
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-obsolete-repairs",
        action="store_true",
        help="후처리 보정으로 불필요해진 과거 관계 재추출 응답의 개수를 명시하고 제외",
    )
    args = parser.parse_args()
    report = replay(json.loads(args.input.read_text(encoding="utf-8")), args.allow_obsolete_repairs)
    report["recording_path"] = str(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            [
                dict(id=r["id"], status=r["status"], checks=r.get("checks"), error=r.get("error"))
                for r in report["cases"]
            ],
            ensure_ascii=False,
        )
    )
    return int(any(r["status"] != "ok" for r in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
