"""Real-model topic-return and clarification-choice evaluation on synthetic records.

Reuse a data directory populated by automatic_chat_eval. Expected outcomes are
kept outside model inputs; citation checks do not constitute semantic approval.
"""

import argparse
import hashlib
import json
import os
import time
from dataclasses import replace
from pathlib import Path

from evaluation.automatic_chat_eval import valid_citations
from pma.chat.engine import ChatEngine
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", type=int, choices=[0, 1, 2], action="append")
    args = parser.parse_args()
    settings = replace(AppSettings.from_env(), data_dir=args.data_dir)
    engine = ChatEngine(
        Service(Store(settings.data_dir / "memory.db"), LocalModels(settings), settings)
    )
    root = Path(__file__).resolve().parents[1]
    report = {
        "semantic_review": "pending_source_review",
        "results": [],
        "runtime": {
            "model": settings.llm.model,
            "generation_revision": os.getenv("PMA_GENERATION_REVISION", "unconfigured"),
            "embedding_key": settings.embedding_key,
            "code_sha256": {
                str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((root / "pma/chat").glob("*.py"))
            },
        },
    }
    scenarios = [
        [
            ("지연이는 누구야?", None, "초등학교 동창"),
            ("제주 여행은 며칠로 바뀌었어?", None, "3박 4일"),
            ("그 사람은 나와 어떤 사이였지?", 0, "지연이, 초등학교 동창; 여행 조건 제외"),
        ],
        [
            ("민수는 누구야?", None, "회사와 동아리 민수 구별 필요"),
            ("동아리 민수", 0, "간호사; 선택 응답을 이전 질문과 연결"),
        ],
        [
            ("민수는 누구야?", None, "회사와 동아리 민수 구별 필요"),
            ("동아리 친구 민수", 0, "간호사; 후보 버튼과 같은 입력"),
        ],
    ]
    for group, turns in enumerate(scenarios):
        if args.scenario is not None and group not in args.scenario:
            continue
        sid = engine.store.create_empty()["id"]
        ids = []
        for index, (question, anchor, expected) in enumerate(turns):
            events = []
            engine.service.diagnostic_sink = events.append
            row = {"scenario": group, "turn": index, "question": question, "expected": expected}
            start = time.monotonic()
            try:
                result = engine.message(
                    sid,
                    str(index),
                    question,
                    "2026-10-18",
                    ids[anchor] if anchor is not None else None,
                )
                ids.append(result["message_id"])
                saved = engine.store.get(sid)["messages"][-1]
                row.update(
                    response=result,
                    evidence=saved["evidence"],
                    citation_valid=valid_citations(result, saved["evidence"]),
                    context_message_id=saved["context_message_id"],
                )
            except Exception as exc:
                row["error"] = str(exc)
                ids.append(None)
            row["seconds"] = round(time.monotonic() - start, 3)
            row["review"] = [
                e for e in events if e.get("stage") in ("chat_route", "chat_validation")
            ]
            report["results"].append(row)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                json.dumps({k: row.get(k) for k in ("scenario", "turn", "error", "seconds")}),
                flush=True,
            )


if __name__ == "__main__":
    main()
