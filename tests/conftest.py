import copy
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pma.settings import AppSettings
from pma.store import Store
from pma.web import create_app


def memory(text="담당자를 정했다."):
    return {
        "local_id": "m1",
        "memory_type": "decision",
        "content": text,
        "subject": {"kind": "self", "value": "사용자", "value_type": "string"},
        "predicate": "정했다",
        "object": {"kind": "literal", "value": "담당자", "value_type": "string"},
        "target": None,
        "time": {
            "raw": None,
            "start": None,
            "end": None,
            "precision": "unknown",
            "certainty": "uncertain",
        },
        "assertion_polarity": "affirmed",
        "polarity": "neutral",
        "content_certainty": "explicit",
        "evidence": [{"quote": text}],
    }


class FakeModels:
    def __init__(self):
        self.failure = None
        self.after_answer = None
        self.invalid_citation = False
        self.empty = False
        self.intent = "recall"

    def extract(self, text, context):
        if self.failure:
            raise self.failure
        return {"memories": [] if self.empty else [memory(text)]}, {
            "model": "fake",
            "latency_seconds": 0,
        }

    def embed(self, texts):
        return np.asarray([[1, 0, 0] for _ in texts], dtype=np.float32)

    def understand(self, question, today):
        return {"intent": self.intent, "date_from": None, "date_to": None}

    def answer(self, question, evidence):
        result = {
            "status": "answered",
            "items": [
                {
                    "text": "담당자를 정했습니다.",
                    "citations": ["unknown" if self.invalid_citation else evidence[0]["id"]],
                }
            ],
        }
        if self.after_answer:
            self.after_answer()
        return copy.deepcopy(result)

    def health(self):
        return {"generation": "ready", "embedding": "ready"}


@pytest.fixture
def settings(tmp_path):
    return replace(
        AppSettings(), data_dir=tmp_path, embedding_dimensions=3, embedding_revision="a" * 64
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "memory.db")


@pytest.fixture
def models():
    return FakeModels()


@pytest.fixture
def client(settings, models):
    app = create_app(settings, models, run_worker=False)
    with TestClient(app, base_url=settings.origin) as c:
        c.headers["Origin"] = settings.origin
        response = c.post("/api/v1/session", json={"token": app.state.bootstrap_token})
        assert response.status_code == 200
        c.headers["X-CSRF-Token"] = response.json()["csrf"]
        yield c
