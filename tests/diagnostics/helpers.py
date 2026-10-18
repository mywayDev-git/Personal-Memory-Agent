"""Synthetic, deterministic search inputs; no model server or real user data."""

from copy import deepcopy

import numpy as np

from pma.service import Service


def row(index=0, *, text=None, relation="other", when="2026-10-03", **fact_changes):
    text = text or f"synthetic {index:02d}"
    event_time = dict(start=when, end=None, certainty="explicit" if when else "uncertain")
    memory = dict(
        content=text,
        subject=None,
        predicate="test",
        object=None,
        target=None,
        memory_type="event",
        assertion_polarity="affirmed",
    )
    fact = dict(
        actor="self",
        recipient=None,
        counterparty=None,
        relation=relation,
        state="observed",
        object_key="test",
        event_time=event_time,
        distance_m=[],
        colors=[],
        review_reasons=[],
    )
    fact.update(fact_changes)
    return dict(
        id=f"memory-{index:02d}",
        record_id=f"record-{index:02d}",
        version=1,
        text=text,
        memory=memory,
        fact=fact,
        evidence=[dict(quote=text)],
        vector=np.array([1, 0, 0], dtype="<f4").tobytes(),
        reference_time=None,
        created_at="2026-10-17T00:00:00Z",
    )


class SnapshotStore:
    """Count store calls; SQL counting is covered separately using the real Store."""

    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.calls = []

    def snapshot(self, key):
        self.calls.append(("snapshot", key))
        return 7, deepcopy(self.rows)

    def links(self, *, memory_ids):
        self.calls.append(("links", sorted(memory_ids)))
        return []

    def assert_generation(self, generation):
        self.calls.append(("assert_generation", generation))
        assert generation == 7


class Models:
    def __init__(self, *, selected=None, error=None, verified=True):
        self.calls = []
        self.selected, self.error, self.verified = selected, error, verified

    def understand(self, question, today):
        self.calls.append(("understand", question, today))
        if self.error == "understand":
            raise ValueError("PRIVATE MODEL ERROR")
        return dict(intent="recall", date_from=None, date_to=None)

    def embed(self, texts):
        self.calls.append(("embed", list(texts)))
        return np.array([[1, 0, 0] for _ in texts], dtype=np.float32)

    def select(self, question, evidence):
        self.calls.append(("select", [r["id"] for r in evidence]))
        if self.error == "select":
            raise ValueError("INVALID_SELECTION_RESPONSE")
        return self.selected if self.selected is not None else [r["id"] for r in evidence]

    def answer(self, question, evidence):
        self.calls.append(("answer", [r["id"] for r in evidence]))
        if self.error == "answer":
            raise ValueError("INVALID_ANSWER")
        return dict(
            status="answered", items=[dict(text="합성 답변", citations=[evidence[0]["id"]])]
        )

    def verify(self, question, evidence, items):
        self.calls.append(("verify", [r["id"] for r in evidence]))
        return self.verified


def run(settings, rows, *, question="synthetic", filters=None, sink=None, **model_options):
    store, models = SnapshotStore(rows), Models(**model_options)
    response = Service(store, models, settings, diagnostic_sink=sink).answer(
        question, filters, today="2026-10-17"
    )
    return response, models.calls, store.calls
