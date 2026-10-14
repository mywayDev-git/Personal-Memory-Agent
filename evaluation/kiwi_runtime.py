"""Synthetic-only common memory path and instrumented local model gateway."""

import json
import re
import sqlite3
import time
from unittest.mock import patch

import numpy as np

from pma.models import ANSWER_SCHEMA, LocalModels
from scripts.memory_agent import llm_client

from .kiwi_contract import ANSWER_PROMPT


class Meter:
    def __init__(self, models):
        self.models = models
        self.stage = "unknown"
        self.calls = []

    def __enter__(self):
        original = llm_client.post_json

        def request(session, endpoint, body, timeout):
            started = time.perf_counter()
            row = dict(
                stage=self.stage,
                endpoint=endpoint.rsplit("/", 1)[-1],
                status="error",
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
            )
            try:
                result = original(session, endpoint, body, timeout)
                row.update(
                    status="ok",
                    **{
                        k: result.get("usage", {}).get(k)
                        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                    },
                )
                # Keep raw generations for inspection, including failed schema validation.
                if "choices" in result:
                    row["raw_response"] = result["choices"]
                return result
            finally:
                row["seconds"] = time.perf_counter() - started
                self.calls.append(row)

        self.patches = [
            patch("scripts.memory_agent.llm_client.post_json", request),
            patch("pma.models.post_json", request),
        ]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *args):
        for p in reversed(self.patches):
            p.stop()


class MemoryDB:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE events(id TEXT PRIMARY KEY,payload TEXT,vector BLOB,dim INTEGER)"
        )
        self.db.execute("CREATE TABLE relations(payload TEXT)")

    def close(self):
        self.db.close()

    def publish(self, result, vectors):
        with self.db:
            for event, vector in zip(result["events"], vectors, strict=True):
                self.db.execute(
                    "INSERT INTO events VALUES(?,?,?,?)",
                    (
                        event["id"],
                        json.dumps(event, ensure_ascii=False),
                        np.asarray(vector, dtype="<f4").tobytes(),
                        len(vector),
                    ),
                )
            self.db.executemany(
                "INSERT INTO relations VALUES(?)",
                [(json.dumps(r, ensure_ascii=False),) for r in result["relations"]],
            )

    def search(self, question, vector):
        rows = self.db.execute("SELECT id,payload,vector,dim FROM events ORDER BY id").fetchall()
        if not rows:
            return []
        events = [json.loads(r[1]) for r in rows]
        matrix = np.array([np.frombuffer(r[2], dtype="<f4", count=r[3]) for r in rows])
        terms = re.findall(r"[가-힣A-Za-z0-9]+", question)
        dense = sorted(range(len(rows)), key=lambda i: (-float(matrix[i] @ vector), rows[i][0]))[
            :20
        ]
        keyword = sorted(
            range(len(rows)),
            key=lambda i: (-sum(t in events[i]["content"] for t in terms), rows[i][0]),
        )[:20]
        ranks = {}
        for order in (dense, keyword):
            for rank, i in enumerate(order, 1):
                ranks[i] = ranks.get(i, 0) + 1 / (60 + rank)
        picked = sorted(ranks, key=lambda i: (-ranks[i], rows[i][0]))[:8]
        return [events[i] for i in picked]

    def relations(self, ids):
        return [
            r
            for (payload,) in self.db.execute("SELECT payload FROM relations")
            if (r := json.loads(payload)) and f"e{r['source']}" in ids and f"e{r['target']}" in ids
        ]


def answer(models: LocalModels, db, question, meter):
    meter.stage = "query_embedding"
    vector = models.embed([question])[0]
    retrieved = db.search(question, vector)
    if not retrieved:
        return dict(status="insufficient_evidence", items=[]), retrieved
    meter.stage = "answer"
    response = models.structured(
        ANSWER_PROMPT,
        dict(
            question=question,
            evidence=retrieved,
            relations=db.relations({r["id"] for r in retrieved}),
        ),
        ANSWER_SCHEMA,
    )
    ids = {e["id"] for e in retrieved}
    if any(c not in ids for item in response["items"] for c in item["citations"]):
        raise ValueError("INVALID_CITATION")
    if (response["status"] == "answered") != bool(response["items"]):
        raise ValueError("INVALID_ANSWER_STATE")
    return response, retrieved
