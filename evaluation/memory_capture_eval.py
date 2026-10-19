"""Opt-in local-model evaluation using synthetic records in a temporary DB.

Run: python -m evaluation.memory_capture_eval --embedding-revision MODEL_SHA256
No existing personal database or evaluation result is opened or overwritten.
"""

import argparse
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from pma.chat.engine import ChatEngine
from pma.memory.api import OWNER
from pma.memory.repository import MemoryRepository
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store
from scripts.memory_agent.llm_client import request_budget

from .memory_resources import observe_http, snapshot


def evaluate(revision):
    output = {"cases": [], "indexing": [], "model_calls": 0, "search_calls": 0}
    with TemporaryDirectory(prefix="memory-capture-eval-") as directory:
        settings = AppSettings(data_dir=Path(directory), embedding_revision=revision)
        store = Store(settings.data_dir / "memory.db")
        model = LocalModels(settings)
        for name in ("extract", "embed", "understand", "structured"):
            original = getattr(model, name)

            def counted(*args, _original=original, **kwargs):
                output["model_calls"] += 1
                return _original(*args, **kwargs)

            setattr(model, name, counted)
        service = Service(store, model, settings)
        repo = MemoryRepository(store)

        def index(label):
            started = time.perf_counter()
            service.run_one()
            statuses = store.list()["items"]
            entry = {
                "case": label,
                "seconds": time.perf_counter() - started,
                "statuses": [r["status"] for r in statuses],
            }
            output["indexing"].append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)

        def search(label, question, expected, absent):
            started = time.perf_counter()
            result = service.search(question)
            output["search_calls"] += 1
            texts = "\n".join(r["content"] for r in result["results"])
            entry = {
                "case": label,
                "seconds": time.perf_counter() - started,
                "passed": expected in texts and absent not in texts,
                "results": result["results"],
            }
            output["cases"].append(entry)
            print(
                json.dumps({"case": label, "passed": entry["passed"]}, ensure_ascii=False),
                flush=True,
            )

        existing = store.create("2026년 7월 19일 제주도에 민수와 갔다.", None)
        index("baseline")
        search("baseline_recall", "제주도에 누구와 갔어?", "민수", "영희")
        correction = repo.correct(
            OWNER, "record:" + existing["record_id"], "2026년 7월 19일 제주도에 영희와 갔다.", 1
        )
        corrected = repo.commit(
            OWNER,
            correction["candidate_id"],
            approved=True,
            request_id="correction",
            resolution="correct",
        )
        index("correction")
        search("corrected_recall", "제주도에 누구와 갔어?", "영희", "민수")
        for kind, source, text in [
            ("preference", "user_message", "앞으로 코드는 한국어로 자세히 설명해줘."),
            (
                "proposal",
                "assistant_message",
                "프로젝트에서 캐시를 도입하는 것이 좋습니다. 아직 구현하지 않았습니다.",
            ),
            (
                "project_decision",
                "user_message",
                "프로젝트에 캐시 도입을 결정했어. 아직 구현하지 않았다.",
            ),
        ]:
            c = repo.propose(OWNER, content=text, source_type=source)
            saved = repo.commit(
                OWNER, c["candidate_id"], approved=True, request_id=kind, resolution="add_confirmed"
            )
            index(kind)
            output["cases"].append(
                {
                    "case": kind,
                    "passed": saved["memory_type"] == kind,
                    "memory": repo.get(OWNER, saved["memory_id"]),
                }
            )
        engine = ChatEngine(service)
        session = engine.store.create_empty()
        response = engine.message(
            session["id"], "style", "Explain a Python for loop.", mode="general"
        )
        output["style_response"] = response
        repo.delete(OWNER, corrected["memory_id"], 2)
        _, rows = store.snapshot(settings.embedding_key)
        output["cases"].append(
            {
                "case": "delete_excluded",
                "passed": all(r["record_id"] != existing["record_id"] for r in rows),
            }
        )
        output["ram_vram"] = "not measured"
        output["model_calls_definition"] = (
            "gateway method invocations; tokenization/retries may add HTTP requests"
        )
        store.checkpoint()
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedding-revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    target = Path(args.output)
    if target.exists():
        parser.error("output already exists; choose a fresh path")
    before = snapshot()
    with request_budget(1200) as budget, observe_http() as all_calls:
        result = evaluate(args.embedding_revision)
    result["model_http_calls"] = budget.calls
    result["all_model_http_calls"] = all_calls
    result["resources"] = {
        "before": before,
        "after": snapshot(),
        "scope": "evaluation Python process RSS and whole GPU usage; warm shared servers",
    }
    result.pop("ram_vram", None)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
