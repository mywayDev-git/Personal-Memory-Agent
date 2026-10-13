import json
import sqlite3

from evaluation.focused_audit import TracedService, copy_database
from evaluation.focused_cases import GROUPS, cases, schedule
from pma.service import Service


def test_approved_matrix_and_source_support():
    data = json.loads(open("data/life_diagnostics.json", encoding="utf-8").read())
    sources = {r["id"] for r in data["records"]}
    assert len(cases()) == 36 and len({c["id"] for c in cases()}) == 36
    assert len(schedule()) == len(set(schedule())) == 80
    selected = {s for group in GROUPS.values() for s in group}
    assert len(selected) == 42 and selected <= sources
    for case in cases():
        assert set(case["required_sources"]) <= set(GROUPS[case["group"]])


def test_backup_is_independent_and_preserves_vectors(tmp_path):
    source, target = tmp_path / "source.db", tmp_path / "copy.db"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE sample (id INTEGER, vector BLOB)")
        db.execute("INSERT INTO sample VALUES(1,?)", (b"\x00\x01\xff",))
        db.commit()
        copy_database(source, target)
        with sqlite3.connect(target) as copied:
            assert copied.execute("SELECT vector FROM sample").fetchone()[0] == b"\x00\x01\xff"
            copied.execute("DELETE FROM sample")
        assert db.execute("SELECT count(*) FROM sample").fetchone()[0] == 1


def test_tracing_does_not_change_answer(store, settings, models):
    service = Service(store, models, settings)
    store.create("담당자를 정했다.", None)
    service.run_one()
    baseline = service.answer("담당자는?", today="2026-10-13")
    traced = TracedService(store, models, settings)
    actual = traced.answer("담당자는?", today="2026-10-13")
    assert actual == baseline
    assert traced.search_trace["eligible_ids"]
    assert traced.search_trace["search_result"]["results"] == actual["results"]
