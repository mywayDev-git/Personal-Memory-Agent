"""An explicitly opened, isolated copy of the product UI for manual questions."""
import argparse
import json
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".local/user-testing"
SEED = ROOT / ".local/latency-goal/source-completion-gpu-confirmation/gpu/synthetic-seed.db"
COMMON = ("compact_ids", "source_facts", "intermediate", "bounded_expansions",
          "source_dates", "context_shortcut", "compact_json", "compact_review")


def prepare_database(directory):
    """Only this fixed, source-checked synthetic template may be copied."""
    directory = Path(directory).resolve()
    if not directory.is_relative_to(WORK.resolve()) or directory == WORK.resolve():
        raise ValueError("테스트 전용 폴더가 아닙니다.")
    fixture = json.loads((ROOT / "evaluation/source_completion_cases.json").read_text(encoding="utf-8"))
    expected = sorted(row[1] for row in fixture["splits"]["confirmation"]["documents"])
    if not SEED.is_file():
        raise ValueError("합성 DB가 없습니다. 기존 측정 자료를 확인해 주세요.")
    with sqlite3.connect(SEED.as_uri() + "?mode=ro", uri=True) as source:
        texts = sorted(row[0] for row in source.execute("SELECT text FROM revisions"))
        if texts != expected:
            raise ValueError("합성 원문이 고정 자료와 다릅니다. 복사를 중단했습니다.")
        if source.execute("SELECT count(*) FROM jobs WHERE status != 'succeeded'").fetchone()[0]:
            raise ValueError("합성 DB에 미완료 작업이 있습니다.")
        metadata = json.loads((ROOT / ".local/latency-goal/source-completion-gpu-confirmation/gpu/results.json")
                              .read_text(encoding="utf-8"))
        key = "bge-m3:" + metadata["hashes"]["embedding"] + ":1024"
        if {r[0] for r in source.execute("SELECT DISTINCT model_key FROM embeddings")} != {key}:
            raise ValueError("합성 DB의 임베딩 모델이 다릅니다. 자동 재계산하지 않습니다.")
        directory.mkdir(parents=True, exist_ok=False)
        with sqlite3.connect(directory / "memory.db") as target:
            source.backup(target)
    return directory / "memory.db"


class SeparateCookie:
    """Keep the regular application's host cookie intact across local ports."""
    def __init__(self, app, port):
        self.app = app
        self.name = f"pma_manual_test_{port}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        scope = dict(scope)
        headers = []
        for key, value in scope["headers"]:
            if key.lower() == b"cookie":
                cookies = []
                for pair in value.split(b";"):
                    name, sep, content = pair.strip().partition(b"=")
                    if name == b"pma_session":
                        continue
                    if name == self.name:
                        name = b"pma_session"
                    cookies.append(name + sep + content)
                value = b"; ".join(cookies)
            headers.append((key, value))
        scope["headers"] = headers

        async def isolated_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = [(key, self.name + value[len(b"pma_session"):]
                    if key.lower() == b"set-cookie" and value.startswith(b"pma_session=") else value)
                    for key, value in message["headers"]]
            await send(message)
        await self.app(scope, receive, isolated_send)


def make_app(directory, port, profile, *, models=None, run_worker=True, generation_port=8081, embedding_port=8082):
    if profile not in {"baseline", "candidate"}:
        raise ValueError("알 수 없는 비교 경로입니다.")
    from config.settings import Settings
    from pma.settings import AppSettings
    from pma.web import create_app, STATIC
    from evaluation.latency_variants import configured
    from fastapi.responses import HTMLResponse
    from fastapi.routing import APIRoute
    metadata = json.loads((ROOT / ".local/latency-goal/source-completion-gpu-confirmation/gpu/results.json")
                          .read_text(encoding="utf-8"))
    options = COMMON + (("scoped_identity", "source_completion") if profile == "candidate" else ())
    settings = configured(AppSettings(data_dir=Path(directory), port=port,
        embedding_revision=metadata["hashes"]["embedding"], answer_validation=True,
        embedding_endpoint=f"http://127.0.0.1:{embedding_port}/v1/embeddings",
        evaluation_enabled=False, evaluation_details=False,
        llm=Settings(model="qwen3", timeout=300,
                     endpoint=f"http://127.0.0.1:{generation_port}/v1/chat/completions")), options)
    settings.validate()
    app = create_app(settings, models=models, run_worker=run_worker)
    label = "추가 속도 후보 · 실험" if profile == "candidate" else "품질 수정 기준"
    text = (STATIC / "index.html").read_text(encoding="utf-8")
    text = text.replace("<title>", "<title>[합성 테스트] ", 1).replace(
        '나만의 로컬 서재', '합성 테스트 DB', 1).replace(
        '지나간 경험을, 오늘의 단서로.', f'합성 기록 테스트 · {label} · 개인 DB 미연결', 1)

    async def index():
        return HTMLResponse(text)
    app.router.routes.insert(0, APIRoute("/", index, methods=["GET"]))
    return app, SeparateCookie(app, port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--profile", choices=("baseline", "candidate"), default="baseline")
    parser.add_argument("--generation-port", type=int, default=8081)
    parser.add_argument("--embedding-port", type=int, default=8082)
    args = parser.parse_args()
    prepare_database(args.directory)
    # Model startup is owned by the explicit console action, never this UI worker.
    import os
    metadata = json.loads((ROOT / ".local/latency-goal/source-completion-gpu-confirmation/gpu/results.json")
                          .read_text(encoding="utf-8"))
    os.environ["PMA_GENERATION_REVISION"] = metadata["hashes"]["generation"]
    app, isolated = make_app(args.directory, args.port, args.profile,
        generation_port=args.generation_port, embedding_port=args.embedding_port)
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(isolated, host="127.0.0.1", port=args.port,
        access_log=False, log_level="warning"))

    def control():
        while not server.started and not server.should_exit:
            time.sleep(.1)
        if server.started:
            ready = {"url": app.state.settings.origin + "/#token=" + app.state.bootstrap_token}
            (args.directory / "ready.json").write_text(json.dumps(ready), encoding="utf-8")
        while not server.should_exit:
            if (args.directory / "stop.request").exists() or args.directory.with_suffix(".stop").exists():
                server.should_exit = True
            time.sleep(.25)
    threading.Thread(target=control, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
