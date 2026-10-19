import json
from pathlib import Path

import pytest

from evaluation.latency_seed import export_seed, restore_seed


def test_public_seed_restores_exact_ids_facts_and_vectors(tmp_path):
    document = json.loads(Path("evaluation/response_latency_seed.json").read_text(encoding="utf-8"))
    path = tmp_path / "seed.db"
    restore_seed(document, path)
    assert export_seed(path) == document
    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        restore_seed(document, path)


def test_seed_export_rejects_extra_application_rows(tmp_path):
    document = json.loads(Path("evaluation/response_latency_seed.json").read_text(encoding="utf-8"))
    path = tmp_path / "seed.db"
    store = restore_seed(document, path)
    with store.connect(True) as db:
        db.execute("INSERT INTO chat_sessions(id,title,state,created_at,updated_at) VALUES('x','private','active','x','x')")
    with pytest.raises(ValueError, match="NON_FIXTURE_ROWS"):
        export_seed(path)


def test_seed_restore_rejects_changed_source_before_creating_database(tmp_path):
    document = json.loads(Path("evaluation/response_latency_seed.json").read_text(encoding="utf-8"))
    source = document["tables"]["revisions"]
    source["rows"][0][source["columns"].index("text")] = "different source"
    path = tmp_path / "invalid.db"
    with pytest.raises(ValueError, match="NOT_THE_SYNTHETIC_SEED"):
        restore_seed(document, path)
    assert not path.exists()
