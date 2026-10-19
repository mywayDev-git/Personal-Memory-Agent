"""Export/restore the exact public synthetic seed, without copying SQLite free pages."""

import argparse
import base64
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from evaluation.response_latency import DOCUMENTS
from pma.store import Store

TABLES = ("metadata", "records", "revisions", "jobs", "memories", "evidence", "embeddings", "facts")


def export_seed(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        texts = [r[0] for r in db.execute("SELECT text FROM revisions")]
        if sorted(texts) != sorted(row[1] for row in DOCUMENTS):
            raise ValueError("NOT_THE_SYNTHETIC_SEED")
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for name in names:
            if name not in TABLES and name != "chat_schema_migrations":
                # Names come from SQLite, never from the export document.
                if db.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]:
                    raise ValueError("SEED_CONTAINS_NON_FIXTURE_ROWS")
        result = {"schema_version": 1, "synthetic_only": True, "tables": {}}
        for name in TABLES:
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({name})")]
            rows = [list(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY 1")]
            if name == "embeddings":
                for row in rows:
                    row[columns.index("vector")] = base64.b64encode(row[columns.index("vector")]).decode("ascii")
            result["tables"][name] = {"columns": columns, "rows": rows}
        return result


def restore_seed(document, path):
    if path.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    if document.get("schema_version") != 1 or document.get("synthetic_only") is not True or set(document["tables"]) != set(TABLES):
        raise ValueError("INVALID_SEED_FORMAT")
    source = document["tables"]["revisions"]
    if sorted(row[source["columns"].index("text")] for row in source["rows"]) != sorted(row[1] for row in DOCUMENTS):
        raise ValueError("NOT_THE_SYNTHETIC_SEED")
    store = Store(path)
    with store.connect(True) as db:
        db.execute("DELETE FROM metadata")
        for name in TABLES:
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({name})")]
            table = document["tables"][name]
            if table["columns"] != columns:
                raise ValueError("INCOMPATIBLE_SEED_COLUMNS")
            rows = [list(row) for row in table["rows"]]
            if name == "embeddings":
                for row in rows:
                    row[columns.index("vector")] = base64.b64decode(row[columns.index("vector")], validate=True)
            placeholders = ",".join("?" for _ in columns)
            db.executemany(f"INSERT INTO {name} VALUES({placeholders})", rows)
    store.checkpoint()
    return store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["export", "restore"])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must not exist")
    if args.mode == "export":
        args.output.write_text(json.dumps(export_seed(args.source), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        restore_seed(json.loads(args.source.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
