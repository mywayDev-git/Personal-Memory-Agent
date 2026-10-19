"""Disposable UI fixture: real HTTP/auth/storage, deterministic model responses."""

from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from pma.chat.store import ChatStore
from pma.memory.conflict_resolver import DIMENSIONS
from pma.memory.repository import MemoryRepository
from pma.settings import AppSettings
from pma.web import create_app


class Models:
    def health(self):
        return {"generation": True, "embedding": True}

    def structured(self, prompt, data, schema, **kwargs):
        if "records" in data:
            return {
                "comparisons": [
                    dict(
                        memory_id=r["memory_id"],
                        relation="complementary",
                        candidate_quote=data["candidate"]["content"],
                        existing_quote=r["content"],
                        reason="합성 평가 모델",
                        **{k: True for k in DIMENSIONS},
                    )
                    for r in data["records"]
                ]
            }
        return {
            "items": [{"message_id": m["message_id"], "quote": m["text"]} for m in data["messages"]]
        }


def fixture(directory):
    app = create_app(
        AppSettings(data_dir=Path(directory), port=8879), models=Models(), run_worker=False
    )
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            chat = ChatStore(app.state.store)
            repo = MemoryRepository(app.state.store)
            c = repo.propose("local-account", content="인덱싱 재시도 평가 기억")
            repo.commit("local-account", c["candidate_id"], approved=True, request_id="failed-seed")
            app.state.store.fail(app.state.store.claim(), "MODEL_UNAVAILABLE")
            for mode in ("general", "memory", "hybrid"):
                sid = chat.create_empty()["id"]
                text = f"{mode} 평가: 앞으로 한국어로 간결하게 설명해줘."
                mid, _ = chat.begin(sid, "seed", text, mode=mode)
                chat.finish(
                    sid,
                    mid,
                    {
                        "status": "answered",
                        "items": [
                            {
                                "text": "캐시를 도입하는 것을 제안합니다. 아직 구현하지 않았습니다.",
                                "citations": [],
                            }
                        ],
                    },
                    [],
                )
            print("UI_URL=http://127.0.0.1:8879/#token=" + app.state.bootstrap_token, flush=True)
            yield

    app.router.lifespan_context = lifespan
    return app


if __name__ == "__main__":
    with TemporaryDirectory(prefix="memory-ui-") as root:
        uvicorn.run(fixture(root), host="127.0.0.1", port=8879, log_level="warning")
