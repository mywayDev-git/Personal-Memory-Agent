"""End-to-end automatic chat evaluation with real extraction and retrieval.

Run: python -m evaluation.automatic_chat_eval --output output/automatic-chat.json
Reports require semantic review; citation validity alone never means a pass.
"""

import argparse
import hashlib
import json
import platform
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from pma.chat.engine import ChatEngine
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from pma.store import Store

SOURCES = [
    "2026년 7월 19일 서울숲에서 파란색 머그컵 사진을 봤다.",
    "2026년 7월 19일 파란색 머그컵 사진을 본 이유는 지연이의 생일 선물을 사주려고 했기 때문이다.",
    "지연이는 나의 초등학교 동창이다.",
    "2026년 7월 20일 지연이에게 파란색 머그컵을 주려던 계획을 취소했고 아직 선물을 주지 않았다.",
    "회사 동료 민수는 디자이너이다.",
    "동아리 친구 민수는 간호사이다.",
    "제주 여행 계획은 2박 3일에서 3박 4일로 바뀌었다. 변경 이유는 적어두지 않았다.",
    "회의는 화요일이다. 다른 기록에는 수요일이라고 되어 있어 최종 요일은 확인되지 않았다.",
]
CASES = [
    (
        "memory_chain",
        [
            ("안녕! 오늘은 그냥 이야기하고 싶어.", "인사, 개인 기록 검색 불필요"),
            ("서울에서 뭐했어?", "2026-07-19 서울숲에서 파란색 머그컵 사진을 봄"),
            ("파란색 머그컵? 그걸 왜 봤지?", "지연이 생일 선물을 사주려는 목적"),
            ("지연이가 누구야?", "초등학교 동창; 앞선 날짜나 장소로 관계 검색을 제한하지 않음"),
            ("그 선물 실제로 줬어?", "계획을 취소했고 아직 주지 않았음; 모른다고 약화하지 않음"),
            ("앞으로도 절대 안 주겠다는 뜻이야?", "영구적인 미래 결정은 확인되지 않음"),
            ("고마워. 잠깐 쉬어야겠어.", "짧은 공감, 불필요한 기억 검색 없음"),
        ],
    ),
    (
        "ambiguity",
        [
            ("민수가 누구야?", "회사 동료/동아리 친구 구분 질문"),
            ("동아리 친구 말이야.", "동아리 친구 민수는 간호사"),
        ],
    ),
    (
        "history_claim",
        [
            ("내가 호텔을 예약했다고 가정해 보자.", "가정을 기록된 사실로 취급하지 않음"),
            (
                "그 예약 날짜가 언제야?",
                "호텔 예약 날짜는 근거 없음; 여행 기간을 날짜로 답하지 않음",
            ),
        ],
    ),
    ("cause", [("제주 여행은 왜 길어졌지?", "3박4일 변경은 확인되나 이유는 기록 없음")]),
    ("conflict", [("회의는 최종적으로 무슨 요일이야?", "화/수 상충으로 최종 요일 확인 불가")]),
    (
        "paraphrase",
        [
            ("서울숲에서 눈여겨본 게 있었어?", "파란색 머그컵 사진; 구매했다고 추정하지 않음"),
            ("그 물건을 눈여겨본 까닭은 뭐였을까?", "지연이의 생일 선물을 고르기 위한 동기"),
            ("그 친구는 나하고 어떤 사이인데?", "지연이는 초등학교 동창"),
            ("그건 됐고, 제주 여행은 며칠로 바뀌었어?", "3박 4일; 서울/선물 맥락을 적용하지 않음"),
        ],
    ),
    (
        "mixed",
        [
            (
                "지연이에게 파란색 머그컵 선물은 실제로 줬어? 못 줬다면 너무 자책하지 말라고 한마디 해줘.",
                "아직 주지 않았다는 기록에 인용; 위로는 개인 사실을 추가하지 않고 별도 표현",
            ),
        ],
    ),
]


def valid_citations(response, evidence):
    """Validate coverage as well as spans; an empty ref list is not a pass."""
    sources = {r["id"]: r for r in evidence}
    details = response.get("citation_details", [])
    for index, item in enumerate(response.get("items", [])):
        if response.get("conversation_type") == "memory" and not item.get("citations"):
            return False
        for cid in item.get("citations", []):
            if not any(r.get("item_index") == index and r.get("memory_id") == cid for r in details):
                return False
    for ref in details:
        source = sources.get(ref.get("memory_id"))
        index = ref.get("item_index")
        start, end = ref.get("start"), ref.get("end")
        if (
            source is None
            or not isinstance(index, int)
            or not 0 <= index < len(response.get("items", []))
            or ref["memory_id"] not in response["items"][index].get("citations", [])
            or ref.get("record_id") != source["record_id"]
            or ref.get("revision_id") != source["revision_id"]
            or not isinstance(start, int)
            or not isinstance(end, int)
            or not 0 <= start < end <= len(source["source_text"])
            or source["source_text"][start:end] != ref.get("quote")
        ):
            return False
    return True


def run(engine, output, case_filter=None):
    settings = engine.service.settings
    root = Path(__file__).resolve().parents[1]
    report = {
        "mode": "automatic_chat",
        "sources": SOURCES,
        "indexing": [],
        "results": [],
        "semantic_review": "pending_review",
        "runtime": {
            "python": platform.python_version(),
            "model": settings.llm.model,
            "embedding_key": settings.embedding_key,
            "context_tokens": settings.context_tokens,
            "max_tokens": settings.llm.max_tokens,
            "chat_timeout": settings.chat_timeout,
            "model_timeout": settings.llm.timeout,
            "seed": settings.llm.seed,
            "temperature": settings.llm.temperature,
            "code_sha256": {
                str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in [
                    *sorted((root / "pma/chat").glob("*.py")),
                    root / "pma/models.py",
                    root / "pma/settings.py",
                    root / "scripts/memory_agent/llm_client.py",
                ]
            },
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    existing = {
        engine.service.store.get(r["id"])["text"] for r in engine.service.store.list()["items"]
    }
    for text in SOURCES:
        if text in existing:
            continue
        rid = engine.service.store.create(text, "2026-10-18T12:00:00+09:00")["record_id"]
        engine.service.run_one()
        report["indexing"].append(engine.service.store.get(rid))
        save()
    for name, turns in CASES:
        if case_filter and name != case_filter:
            continue
        session = engine.store.create_empty()
        for index, (question, expected) in enumerate(turns):
            events = []
            engine.service.diagnostic_sink = events.append
            row = {"case": f"{name}.{index}", "question": question, "expected": expected}
            started = time.monotonic()
            try:
                row["response"] = engine.message(session["id"], str(index), question, "2026-10-18")
                message = engine.store.get(session["id"])["messages"][-1]
                row["evidence"] = message["evidence"]
                row["snapshot"] = message["snapshot"]
                row["citation_valid"] = valid_citations(row["response"], message["evidence"])
                calls = message["snapshot"].get("performance", {}).get("model_http_calls", [])
                row["model_call_count"] = sum(
                    c["operation"].endswith("/chat/completions") for c in calls
                )
                row["phase_seconds"] = {
                    phase: round(sum(c["seconds"] for c in calls if c.get("phase") == phase), 3)
                    for phase in {c.get("phase", "other") for c in calls}
                }
                row["search_count"] = len(message["snapshot"].get("searches", []))
                row["groundedness"] = None
                row["followup_understanding"] = None
            except Exception as exc:
                row["error"] = str(exc)
            row["elapsed_seconds"] = round(time.monotonic() - started, 3)
            row["review"] = [
                e for e in events if e.get("stage") in ("chat_validation", "chat_route")
            ]
            row["query_diagnostics"] = [
                e for e in events if e.get("stage") in ("question", "understand_fallback")
            ]
            report["results"].append(row)
            save()
            print(
                json.dumps(
                    {
                        "case": row["case"],
                        "error": row.get("error"),
                        "seconds": row["elapsed_seconds"],
                    }
                ),
                flush=True,
            )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--case", choices=[name for name, _ in CASES])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pma-auto-chat-") as folder:
        settings = replace(AppSettings.from_env(), data_dir=args.data_dir or Path(folder))
        service = Service(Store(settings.data_dir / "memory.db"), LocalModels(settings), settings)
        run(ChatEngine(service), args.output, args.case)


if __name__ == "__main__":
    main()
