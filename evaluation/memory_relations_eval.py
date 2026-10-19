"""Opt-in real Qwen relationship benchmark, using synthetic temporary records only."""

import argparse
import json
import statistics
from pathlib import Path
from tempfile import TemporaryDirectory

from pma.memory.manager import MemoryCaptureManager
from pma.memory.repository import MemoryRepository
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store

CASES = [
    (
        "semantic_duplicate",
        "나는 간결한 설명을 선호한다.",
        "나는 설명이 짧고 간결한 것을 선호한다.",
    ),
    (
        "contradiction",
        "2026년 1월 1일 민수에게 선물을 주었다.",
        "2026년 1월 1일 민수에게 선물을 주지 않았다.",
    ),
    ("temporal_update", "2020년에는 부산에 살았다.", "2026년 현재는 서울에 살고 있다."),
    ("complementary", "프로젝트에 캐시를 도입하기로 결정했다.", "캐시 구현 담당자는 민수다."),
    ("unrelated", "2026년 1월 1일 민수를 만났다.", "2026년 1월 2일 영희를 만났다."),
    (
        "correction",
        "제주도에 민수와 갔다.",
        "이전 기록을 정정한다. 제주도에 간 사람은 민수가 아니라 영희다.",
    ),
    ("supporting", "민수가 회의에 참석했다.", "회의 출석부에도 민수가 참석했다고 기록되어 있다."),
    ("exact_duplicate", "나는 커피를 좋아한다.", "나는 커피를 좋아한다."),
]


def evaluate():
    results = []
    with TemporaryDirectory(prefix="memory-relations-") as root:
        for index, (expected, old, new) in enumerate(CASES):
            settings = AppSettings(data_dir=Path(root) / str(index))
            store = Store(settings.data_dir / "memory.db")
            repo = MemoryRepository(store)
            candidate = repo.propose("local-account", content=old)
            repo.commit("local-account", candidate["candidate_id"], approved=True, request_id="old")
            manager = MemoryCaptureManager(store, Service(store, LocalModels(settings), settings))
            candidate = repo.propose("local-account", content=new)
            review = manager.review("local-account", candidate["candidate_id"])
            actual = review["comparisons"][0]["relation"] if review["comparisons"] else None
            result = dict(
                expected=expected, actual=actual, passed=actual == expected, review=review
            )
            results.append(result)
            print(
                json.dumps({k: v for k, v in result.items() if k != "review"}, ensure_ascii=False),
                flush=True,
            )
    times = [r["review"]["seconds"] for r in results]
    return dict(
        cases=results,
        passed=sum(r["passed"] for r in results),
        total=len(results),
        mean_seconds=statistics.mean(times),
        p95_seconds=sorted(times)[-1],
        p95_method="nearest rank; eight synthetic samples",
        model_http_calls=sum(len(r["review"]["model_http_calls"]) for r in results),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate()
    args.output.parent.mkdir(exist_ok=True, parents=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
