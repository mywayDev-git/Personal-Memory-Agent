import json
from types import SimpleNamespace

import pytest

from evaluation import review_bank


def test_cancel_boundary_preserves_completed_synthetic_reviews_without_another_call(tmp_path, monkeypatch):
    calls, boundaries = [], []
    monkeypatch.setattr(review_bank, "accepted", lambda *args: True)
    monkeypatch.setattr(review_bank, "review_spans_supported", lambda *args, **kwargs: True)
    def review(*args):
        calls.append(args)
        return {"synthetic_review": True}
    def boundary():
        boundaries.append(True)
        if len(boundaries) == 2:
            raise KeyboardInterrupt("cancelled experiment")
    path = tmp_path / "quality.json"
    with pytest.raises(KeyboardInterrupt):
        review_bank.evaluate(SimpleNamespace(review=review), path, before_call=boundary)
    assert len(calls) == 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == 1 and saved[0]["pair"] == 0
    assert saved[0]["review"] == {"synthetic_review": True}
