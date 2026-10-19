"""Real HTTP search/chat verification against an isolated synthetic app DB."""

import argparse
import json
import os
import shutil
import threading
import time
from pathlib import Path

import requests
import uvicorn

from config.settings import Settings
from evaluation.performance_benchmark import QUESTION
from pma.search_explain import _native_matcher
from pma.settings import AppSettings
from pma.store import Store
from pma.web import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.seed, args.output / "memory.db")
    with Store(args.output / "memory.db").connect() as db:
        revision = (
            db.execute("SELECT model_key FROM embeddings LIMIT 1").fetchone()[0].split(":")[-2]
        )
    settings = AppSettings(
        data_dir=args.output,
        port=18765,
        embedding_revision=revision,
        answer_validation=True,
        llm=Settings(model="qwen3"),
    )
    app = create_app(settings, run_worker=False)
    os.environ["PMA_KEYWORD_BACKEND"] = "cpp"
    native = _native_matcher()
    assert native is not None
    import pma.search_explain as module

    original = module._native_matcher
    calls = []

    def invoke(rows, terms, vocabulary, normalize):
        result = native(rows, terms, vocabulary, normalize)
        calls.append(dict(rows=len(rows)))
        return result

    module._native_matcher = lambda: invoke
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=18765, access_log=False, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    output = dict(synthetic_only=True, backend="cpp", runs=[])
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Synthetic HTTP app did not start")
            time.sleep(0.05)
        with requests.Session() as client:
            client.trust_env = False
            client.headers["origin"] = settings.origin
            response = client.post(
                settings.origin + "/api/v1/session",
                json={"token": app.state.bootstrap_token},
                timeout=10,
            )
            response.raise_for_status()
            client.headers["x-csrf-token"] = response.json()["csrf"]
            for scenario in ("search", "memory_chat"):
                before = len(calls)
                start = time.perf_counter()
                payload = dict(question=QUESTION, today="2026-10-19")
                if scenario == "search":
                    url = settings.origin + "/api/v1/search"
                else:
                    session = client.post(
                        settings.origin + "/api/v1/chat/sessions", json={}, timeout=10
                    )
                    session.raise_for_status()
                    sid = session.json()["id"]
                    url = settings.origin + f"/api/v1/chat/sessions/{sid}/messages"
                    payload.update(request_id="native-http-probe", mode="memory")
                response = client.post(url, json=payload, timeout=330)
                response.raise_for_status()
                result = response.json()
                row = dict(
                    scenario=scenario,
                    http_status=response.status_code,
                    status=result["status"],
                    seconds=time.perf_counter() - start,
                    native_calls=len(calls) - before,
                    rows=sum(c["rows"] for c in calls[before:]),
                )
                if scenario == "memory_chat":
                    row.update(
                        validation=result.get("validation"),
                        citations=sum(
                            len(item.get("citations", [])) for item in result.get("items", [])
                        ),
                        expected_book=any(
                            "책" in item.get("text", "") for item in result.get("items", [])
                        ),
                    )
                assert row["native_calls"] > 0
                output["runs"].append(row)
    finally:
        server.should_exit = True
        thread.join(15)
        module._native_matcher = original
    (args.output / "verification.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output))


if __name__ == "__main__":
    main()
